"""
UPH WMS 배송파일 자동 다운로드 매크로 (Selenium 기반)

[동작 순서]
1. 이지어드민(디버깅모드 크롬, 이미 로그인된 세션에 연결)에서
   주문/배송 -> 확장주문검색2(template=DS00) 진입
2. 검색조건 설정: 발주일 = 오늘 ± 7일, 상태 = 송장+배송, 다운로드항목 = UPH현황
3. 검색(F2) -> 다운로드(F6)
4. 팝업 4단계 순차 처리
   ① 다운로드 변경 안내 -> 다운로드 신청
   ② 개인정보 파기 안내 -> 확인
   ③ SweetAlert 다운로드 안내 -> "확인했습니다" 입력 -> 확인
   ④ 다운로드 접수 안내 -> 바로가기 (새 창으로 다운로드관리자 열림)
5. 다운로드관리자(template=BL30) 새 창에서 검색(F2) 반복 클릭하며 진척도 폴링
6. 100% 완료되면 파일 링크 클릭 -> 로컬(감시폴더)에 실제 파일 다운로드
7. 새 창 닫고 원래 창(확장주문검색2)으로 복귀

주의: 다운로드가 실제로 감시폴더에 떨어지려면, 이 스크립트가 붙는 디버그 크롬의
chrome://settings/downloads 에서 다운로드 위치가 미리 감시폴더로 지정되어 있어야 함.

⚠️ 2026-08-06부터: "내 요청" 행 판별을 다운로드관리자 목록의 맨 위 행으로 단순화함
(find_my_request_row 참고). 이 방식은 로그인 계정이 이 매크로 전용(다른 직원/다른 화면과
비공유)일 때만 안전하다 — 계정을 같이 쓰는 동안에는 다른 사람 요청이 위에 낄 수 있어 엉뚱한
행을 잘못 집을 위험이 있음. 전용 계정 전환 전이라면 이 부분을 실제 운영에 쓰지 말 것.

필요 패키지: selenium (Chrome/chromedriver는 시스템에 설치되어 있어야 함)
"""

import sys
import os
import io
import time
import traceback
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
    ElementClickInterceptedException, UnexpectedAlertPresentException, NoAlertPresentException,
    WebDriverException
)

# ── stdout UTF-8 강제 설정 (Windows cp949 환경 한글 깨짐 방지) ──
# ⚠️ 콘솔 없는 exe(통합 시스템) 안에서는 sys.stdout이 None이라 .buffer 접근이
#    import 시점에 AttributeError로 죽는다 — 매크로가 아예 안 뜬다 (자가진단으로 발견).
def _force_utf8(name):
    stream = getattr(sys, name, None)
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        setattr(sys, name, io.TextIOWrapper(
            buf, encoding="utf-8", errors="replace", line_buffering=True))


_force_utf8("stdout")
_force_utf8("stderr")

IS_GUI = (not sys.stdin) or (not sys.stdin.isatty())

# ─────────────────────────────────────────
#  ★ 설정 영역
# ─────────────────────────────────────────
WAIT_TIMEOUT   = 15    # 요소/팝업 대기 시간(초)
CLICK_DELAY    = 0.4   # 클릭 사이 딜레이(초)
# 발주일 검색 범위: 시작(과거) / 종료(미래) 오프셋을 따로 둠.
# 미래 방향은 발주일이 미래일 수 없으므로 0으로 고정 — 예전엔 ±7일(최대 15일치)을 매번
# 통째로 재조회해서 리포트 생성 자체가 느려지는 주된 원인이었음.
# 과거 방향(START_OFFSET_DAYS)은 "미배송 상태로 실제로 며칠까지 밀릴 수 있는지"에 맞춰
# 조정 필요 — 너무 좁히면 오래된 미배송 건의 상태 변화를 놓칠 수 있음.
START_OFFSET_DAYS = -4   # 발주일 시작 = 오늘 - N일 (평시 1~2일, 행사기간 3~4일 지연 감안 — 특이사항은 별도 확인 or 추후 조정)
END_OFFSET_DAYS   = 0    # 발주일 끝 = 오늘 (미래로 잡을 이유 없음)

# ── 오래된 미배송 잔여 재확인(reconciliation) 설정 ──
# 평소 회차는 발주일 -4일~오늘만 보기 때문에, 그보다 더 오래전에 발주됐는데 아직 '송장'
# 상태로 잡혀있던 주문이 나중에 실제로 배송 처리돼도 그 변화를 영영 알 수 없는 문제가 있었음
# (2026-08-05, 대시보드 '총 잔여'가 WMS 실제 '송장' 건수보다 계속 부풀려지는 버그로 발견 —
#  발주일 -4일 밖으로 밀려난 주문은 이후 상태가 바뀌어도 재조회 대상에서 빠지기 때문).
# 그래서 주기적으로 훨씬 넓은(오래된) 발주일 범위를 한 번씩 추가로 훑어서 상태 변화를 반영한다.
RECON_START_OFFSET_DAYS = -21                       # 재확인 조회 시작 = 오늘 - 21일
                                                     # (평시 1~2일, 행사기간 3~4일 지연 대비 넉넉한 3주 여유.
                                                     #  -60일은 다운로드량이 너무 많아 한 회차가 지나치게
                                                     #  오래 걸려서 -21일로 축소함, 2026-08-05)
RECON_END_OFFSET_DAYS = START_OFFSET_DAYS - 1       # 평소 조회 범위 바로 앞까지 (겹치지 않게)
RECON_INTERVAL_SEC = 6 * 60 * 60                    # 6시간마다 한 번씩 재확인 회차 실행

POLL_INTERVAL_SEC = 5   # 다운로드관리자 진척도 재확인 주기(초)
LOOP_INTERVAL_SEC = 90  # 한 회차 끝나고 다음 회차 시작까지 대기 시간(초)
# 행사 기간에는 물량이 많아 다운로드 준비가 오래 걸릴 수 있어 최대 시도 횟수 제한을 두지 않음
# (100%가 될 때까지 무한정 폴링. 상태창 로그로 계속 진행상황을 확인할 수 있음)
SWAL_CONFIRM_TEXT = "확인했습니다"

# 이 파일이 없으면 '최초 실행'으로 판단해 상태=송장만 다운로드하여 기준선을 잡고,
# 성공하면 이 파일을 만들어 다음 실행부터는 자동으로 송장+배송을 받도록 함.
# (사람이 매번 --baseline 옵션을 기억해서 붙일 필요 없게 자동 판단)
# 허브 exe 안에서는 __file__이 임시 폴더라 플래그가 매번 사라진다
# (= 매 실행이 최초 실행으로 취급됨). 허브가 지정해준 경로를 우선 쓴다.
BASELINE_FLAG_FILE = os.getenv("UPH_BASELINE_FLAG") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "baseline_done.flag"
)

# ── 확장주문검색2 페이지 셀렉터 ──
MENU_LINK_TEXT          = "확장주문검색2"
START_DATE_INPUT        = "#start_date"
END_DATE_INPUT          = "#end_date"
STATUS_SELECT           = "select[name='status_sel']"
STATUS_OPTION_TEXT_NORMAL   = "송장+배송"  # 평소 실행: 대기중+완료 둘 다 받아서 diffing
STATUS_OPTION_TEXT_BASELINE = "송장"       # 최초 1회(기준선 설정): 아직 배송 안 된 대기 물량만
DOWNLOAD_FIELD_SELECT   = "#download_field"
DOWNLOAD_FIELD_TEXT     = "UPH현황"
SEARCH_BUTTON           = "#search"                # div#search (table_search_button)
DOWNLOAD_BUTTON         = "#download"               # span#download

# ── 팝업 셀렉터 ──
POPUP_DOWNLOAD_INFO      = "#pop_download_info"
BTN_DOWNLOAD_INFO_APPLY  = "#btn_download_info1"    # 다운로드 신청
POPUP_PERSONAL_INFO      = "#pop_personal_information"
BTN_PERSONAL_CONFIRM     = ".btn_cnf"               # 확인
SWAL_INPUT               = "#swal2-input"
SWAL_CONFIRM_BTN         = ".swal2-confirm"
POPUP_DOWNLOAD_COMPLETE  = "#pop_download_complete"
BTN_DOWNLOAD_COMPLETE_GO = "#btn_download_complete1"  # 바로가기
BTN_DOWNLOAD_CLOSE       = "#btn_download_close"      # 팝업 우상단 닫기(X)

# ── 다운로드관리자 페이지 셀렉터 ──
DLMGR_SEARCH_BUTTON     = "button#search"
DLMGR_GRID_ROWS         = "table#grid1 tbody tr.jqgrow[role='row']"   # jqgfirstrow(더미 행) 제외, 실제 데이터 행만
DLMGR_STATUS_CELL       = "td[aria-describedby$='_status']"
DLMGR_PERCENT_CELL      = "td[aria-describedby$='_work_percent']"
DLMGR_FILE_LINK         = "a.txt-link.black"

# debug_dump_row_columns() 실행 결과로 확인된 실제 컬럼 키 (2026-07-27 확인)
DLMGR_REQTIME_CELL      = "td[aria-describedby$='_crdate']"     # 요청시간 컬럼
DLMGR_PAGE_CELL         = "td[aria-describedby$='_template']"   # 페이지 컬럼

# '내 요청' 판별 기준
# ⚠️ 전제조건: 이 다운로드관리자 계정은 이 매크로 전용이어야 한다 (다른 직원/다른 화면과
# 공유 금지). 전용 계정이라면 목록에 이 매크로가 넣은 요청만 쌓이고, 매크로는 순차적으로
# (한 요청 완료 후 다음 요청) 돌기 때문에 "목록 맨 위 = 방금 내가 넣은 요청"이 항상 성립한다.
# 그래서 요청 클릭시각과 정교하게 시각을 맞춰볼 필요 없이 맨 위 행을 그대로 쓴다.
# 계정을 공유하는 동안에는 이 방식을 쓰면 안 된다 — 다른 사람 요청이 위에 낄 수 있음.
#
# (예전엔 페이지명+요청시각(±허용오차)으로 정교하게 매칭했는데, 서버-PC 시계 오차 등으로
#  매칭 조건이 애초에 안 맞으면 몇 번을 재시도해도 절대 못 찾아 무한정 도는 문제가 있었음
#  — 2026-08-06, 291회차 넘게 멈춰있던 사고로 발견. 전용 계정 + 맨 위 행 전제로 이 문제
#  자체를 구조적으로 없앤다.)
EXPECTED_PAGE_TEXT       = "확장주문검색2"   # 맨 위 행이 정말 이 페이지 요청인지 확인하는 최소 안전장치
# 목록에 행 자체가 안 뜨거나, 맨 위 행의 페이지명이 기대와 다른 경우(아직 갱신 전 등)의 재시도 한도.
# 행을 찾은 뒤 100%가 될 때까지 기다리는 단계는 대용량 리포트 생성 시간을 감안해 여전히 무제한.
ROW_SEARCH_MAX_ATTEMPTS  = 24   # POLL_INTERVAL_SEC=5초 기준 2분


# ─────────────────────────────────────────
#  헬퍼 함수
# ─────────────────────────────────────────
LOG_FILE = os.getenv("UPH_MACRO_LOG_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "uph_download_macro.log"
)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def check_and_handle_native_alert(driver):
    """브라우저 native alert/confirm 처리 (matching_macro.py와 동일 패턴)"""
    try:
        alert = driver.switch_to.alert
        alert_text = alert.text
        log(f"    [ALERT] '{alert_text[:60]}' -> 확인 클릭")
        alert.accept()
        time.sleep(CLICK_DELAY)
        return True
    except NoAlertPresentException:
        return False
    except Exception as e:
        log(f"    [WARN] 알림창 처리 중 오류: {e}")
        try:
            driver.switch_to.alert.accept()
        except Exception:
            pass
        return True


def safe_click(driver, selector, timeout=WAIT_TIMEOUT, by=By.CSS_SELECTOR):
    """요소가 나타날 때까지 기다렸다가 JS 클릭 (가려짐/hover 필요 요소도 안전하게 클릭)"""
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        driver.execute_script("arguments[0].click();", el)
        time.sleep(CLICK_DELAY)
        return True
    except TimeoutException:
        log(f"    [ERR] 요소를 찾지 못함(타임아웃): {selector}")
        return False
    except UnexpectedAlertPresentException:
        check_and_handle_native_alert(driver)
        return safe_click(driver, selector, timeout, by)


def set_input_value(driver, selector, value, timeout=WAIT_TIMEOUT):
    """datepicker 등 입력창 값 설정: 클릭 -> 전체선택 -> 삭제 -> 입력 -> ESC(달력 닫기)"""
    el = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    el.click()
    time.sleep(0.15)
    el.send_keys(webdriver.common.keys.Keys.CONTROL, "a")
    el.send_keys(webdriver.common.keys.Keys.DELETE)
    el.send_keys(value)
    el.send_keys(webdriver.common.keys.Keys.ESCAPE)
    time.sleep(CLICK_DELAY)


def wait_visible(driver, selector, timeout=WAIT_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
    )


def wait_gone(driver, selector, timeout=WAIT_TIMEOUT):
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, selector))
        )
    except TimeoutException:
        pass


def debug_dump_row_columns(driver, max_rows=3):
    """[1회성 디버그 도구] 다운로드관리자 목록의 실제 컬럼 aria-describedby 키를 확인용.
    실사이트에서 이 함수만 따로 호출해서 로그를 확인한 뒤,
    DLMGR_REQTIME_CELL / DLMGR_PAGE_CELL 상수를 실제 키 이름으로 교체할 것.
    (본 매크로 정식 실행 전 반드시 1회 실행 권장 — 아직 실사이트 미검증 상태)
    """
    rows = driver.find_elements(By.CSS_SELECTOR, DLMGR_GRID_ROWS)
    log(f"[DEBUG] 총 {len(rows)}행 감지, 상위 {min(max_rows, len(rows))}행의 컬럼 구조를 출력합니다.")
    for i, row in enumerate(rows[:max_rows]):
        cells = row.find_elements(By.TAG_NAME, "td")
        for cell in cells:
            key = cell.get_attribute("aria-describedby") or "(없음)"
            text = cell.text.strip().replace("\n", " ")
            log(f"    [{i}행] key={key} text='{text}'")


# ─────────────────────────────────────────
#  단계별 함수
# ─────────────────────────────────────────
def _try_click_link_text(driver, text, timeout=WAIT_TIMEOUT):
    """LINK_TEXT로 요소를 찾아 JS 클릭. 못 찾으면 예외 없이 False 반환."""
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.LINK_TEXT, text))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        driver.execute_script("arguments[0].click();", el)
        return True
    except TimeoutException:
        return False


def goto_extended_order_search(driver):
    """
    확장주문검색2는 처음 로그인 시 뜨는 홈 대시보드(제목 '이지WMS')에는 없고,
    상단 '주문/배송' 메뉴를 먼저 클릭해서 주문관리 화면으로 들어가야
    좌측 사이드바에 '확장주문검색2'가 나타남. 그래서 2단계로 진입한다.
    (이미 주문관리 화면에 있는 상태라면 1단계 없이 바로 찾아지므로 그 경우도 처리)
    """
    log("① 확장주문검색2 메뉴 진입 시도 (사이드바에 이미 있는지 먼저 확인)")
    if _try_click_link_text(driver, MENU_LINK_TEXT, timeout=3):
        log("    사이드바에서 바로 클릭됨")
        time.sleep(1.0)
        return

    log("    사이드바에 없음 -> 상단 '주문/배송' 메뉴 먼저 클릭")
    if not _try_click_link_text(driver, "주문/배송", timeout=WAIT_TIMEOUT):
        log("    [ERR] 상단 '주문/배송' 메뉴도 찾지 못했습니다.")
        raise TimeoutException("'주문/배송' 상단 메뉴 진입 실패")
    time.sleep(1.5)

    if not _try_click_link_text(driver, MENU_LINK_TEXT, timeout=WAIT_TIMEOUT):
        log("    [ERR] '확장주문검색2' 메뉴 링크를 찾지 못했습니다.")
        raise TimeoutException("'확장주문검색2' 진입 실패")
    time.sleep(1.0)


def set_search_conditions(driver, baseline=False, start_offset_days=None, end_offset_days=None):
    status_text = STATUS_OPTION_TEXT_BASELINE if baseline else STATUS_OPTION_TEXT_NORMAL
    start_offset = START_OFFSET_DAYS if start_offset_days is None else start_offset_days
    end_offset = END_OFFSET_DAYS if end_offset_days is None else end_offset_days
    log(f"② 검색조건 설정 (발주일 {start_offset}일~{end_offset}일 / 상태={status_text} / 다운로드항목=UPH현황)")
    today = datetime.now()
    start_str = (today + timedelta(days=start_offset)).strftime("%Y-%m-%d")
    end_str = (today + timedelta(days=end_offset)).strftime("%Y-%m-%d")

    set_input_value(driver, START_DATE_INPUT, start_str)
    set_input_value(driver, END_DATE_INPUT, end_str)

    status_el = WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, STATUS_SELECT))
    )
    Select(status_el).select_by_visible_text(status_text)

    dl_field_el = WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, DOWNLOAD_FIELD_SELECT))
    )
    Select(dl_field_el).select_by_visible_text(DOWNLOAD_FIELD_TEXT)

    log(f"    발주일: {start_str} ~ {end_str}")


def click_search(driver):
    log("③ 검색(F2) 클릭")
    safe_click(driver, SEARCH_BUTTON)
    time.sleep(1.5)  # 검색 결과 렌더링 대기


def clear_stray_popups(driver):
    """이전 회차가 팝업 처리 도중 오류로 끊긴 경우, 화면에 남아있는 팝업을 정리한다.
    각 팝업이 실제로 떠있는지 아주 짧게(2초)만 확인하고, 없으면 바로 다음으로 넘어간다
    (평소엔 아무것도 안 걸리므로 매 회차 앞에 붙여놔도 정상 케이스엔 거의 지연이 없다).
    맨 마지막 단계(다운로드 접수 안내)부터 역순으로 확인해야, 여러 팝업이 동시에
    남아있어도 실제 떠있는 것부터 순서대로 닫힌다.
    """
    cleared = []

    # 다운로드 접수 안내가 남아있으면 -> 닫기(X)만 누르고 새로 시작 (바로가기는 다시 안 누름)
    try:
        WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.CSS_SELECTOR, POPUP_DOWNLOAD_COMPLETE)))
        safe_click(driver, BTN_DOWNLOAD_CLOSE, timeout=3)
        cleared.append("다운로드 접수 안내")
    except TimeoutException:
        pass

    # SweetAlert 입력창이 남아있으면 -> 문구 입력하고 확인 눌러서 마저 진행시킴
    try:
        swal_input = WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.CSS_SELECTOR, SWAL_INPUT)))
        swal_input.clear()
        swal_input.send_keys(SWAL_CONFIRM_TEXT)
        time.sleep(0.3)
        safe_click(driver, SWAL_CONFIRM_BTN, timeout=3)
        cleared.append("SweetAlert(확인했습니다)")
    except TimeoutException:
        pass

    # 개인정보 파기 안내가 남아있으면 -> 확인
    try:
        WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.CSS_SELECTOR, POPUP_PERSONAL_INFO)))
        safe_click(driver, BTN_PERSONAL_CONFIRM, timeout=3)
        cleared.append("개인정보 파기 안내")
    except TimeoutException:
        pass

    # 다운로드 변경 안내가 남아있으면 -> 다운로드 신청
    try:
        WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.CSS_SELECTOR, POPUP_DOWNLOAD_INFO)))
        safe_click(driver, BTN_DOWNLOAD_INFO_APPLY, timeout=3)
        cleared.append("다운로드 변경 안내")
    except TimeoutException:
        pass

    # 이전 회차에서 열렸던 다운로드관리자 창이 안 닫히고 남아있을 수도 있으니,
    # 지금 붙어있는 창(main_handle) 말고 다른 창이 있으면 전부 닫아버림
    try:
        main_handle = driver.current_window_handle
        extra_handles = [h for h in driver.window_handles if h != main_handle]
        for h in extra_handles:
            driver.switch_to.window(h)
            driver.close()
            cleared.append("잔여 다운로드관리자 창")
        driver.switch_to.window(main_handle)
    except Exception as e:
        log(f"    [WARN] 잔여 창 정리 중 오류(무시): {e}")

    if cleared:
        log(f"    [정리] 이전 회차 잔여 팝업/창 정리: {', '.join(cleared)}")
        time.sleep(1.0)
    return cleared


def click_download_and_handle_popups(driver):
    log("④ 다운로드(F6) 클릭")
    safe_click(driver, DOWNLOAD_BUTTON)

    request_click_time = None  # 팝업3(SweetAlert 확인) 직후 실제 요청 등록 시점 근처로 잡음
    try:
        # 팝업1: 다운로드 변경 안내
        log("    팝업1 '다운로드 변경 안내' 대기")
        wait_visible(driver, POPUP_DOWNLOAD_INFO)
        safe_click(driver, BTN_DOWNLOAD_INFO_APPLY)

        # 팝업2: 개인정보 파기 안내
        log("    팝업2 '개인정보 파기 안내' 대기")
        wait_visible(driver, POPUP_PERSONAL_INFO)
        safe_click(driver, BTN_PERSONAL_CONFIRM)

        # 팝업3: SweetAlert 다운로드 안내 (문구 입력 필요)
        log("    팝업3 SweetAlert '다운로드 안내' 대기 -> 문구 입력")
        swal_input = wait_visible(driver, SWAL_INPUT)
        swal_input.clear()
        swal_input.send_keys(SWAL_CONFIRM_TEXT)
        time.sleep(0.3)
        safe_click(driver, SWAL_CONFIRM_BTN)
        # 여기가 실제 서버 요청 등록에 가장 가까운 시점 (이 직후 '접수 안내' 팝업이 뜸)
        request_click_time = datetime.now()
    except Exception as e:
        # 팝업 4단계 중간에 끊기면 다음 회차 시작 시 clear_stray_popups()가 정리를 시도하긴 하지만,
        # 정확히 어느 팝업에서 끊겼는지 지금 바로 로그에 남겨둬야 나중에 원인 추적이 쉬움
        log(f"    [ERR] 팝업 처리 도중 실패 (다음 회차 시작 시 자동 정리 시도됨): {e}")
        raise

    # 팝업4: 다운로드 접수 안내 -> 바로가기 (새 창 열림)
    log("    팝업4 '다운로드 접수 안내' 대기 -> 바로가기 클릭")
    wait_visible(driver, POPUP_DOWNLOAD_COMPLETE)
    handles_before = set(driver.window_handles)
    safe_click(driver, BTN_DOWNLOAD_COMPLETE_GO)

    # 새 창 핸들 확보
    new_handle = None
    for _ in range(20):
        handles_after = set(driver.window_handles)
        diff = handles_after - handles_before
        if diff:
            new_handle = diff.pop()
            break
        time.sleep(0.3)

    if not new_handle:
        log("    [ERR] 다운로드관리자 새 창을 감지하지 못했습니다.")
        return None, None

    log(f"    새 창 감지됨: {new_handle}")

    # 이 시점엔 아직 원래 창(확장주문검색2)에 포커스가 있음 (switch_to.window를 안 했으므로).
    # 남아있는 '다운로드 접수 안내' 팝업을 닫아둔다.
    # (안 닫으면 다음 회차 실행 때 이 팝업이 그대로 남아 다운로드 버튼 클릭을 방해함)
    try:
        safe_click(driver, BTN_DOWNLOAD_CLOSE, timeout=3)
        log("    원래 창의 '다운로드 접수 안내' 팝업 닫음")
    except Exception as e:
        log(f"    [WARN] 팝업 닫기 실패(무시하고 진행): {e}")

    return new_handle, request_click_time


def find_my_request_row(rows):
    """'내 요청'으로 추정되는 행 하나를 확정. 반환: (target_row, 요청시간_문자열) 또는 (None, None).

    ⚠️ 이 함수는 다운로드관리자 계정이 이 매크로 전용(다른 사람과 비공유)이라는 전제 하에
    동작한다 — 목록이 최신순 정렬이라고 보고 그냥 맨 위 행을 쓴다. 페이지명만 최소한으로
    확인해서, 아직 목록이 갱신되기 전이거나(요청이 화면에 반영되기 직전) 뭔가 예상과 다르면
    None을 반환해 재시도하게 한다."""
    if not rows:
        return None, None
    top_row = rows[0]
    try:
        page_text = top_row.find_element(By.CSS_SELECTOR, DLMGR_PAGE_CELL).text.strip()
        reqtime_text = top_row.find_element(By.CSS_SELECTOR, DLMGR_REQTIME_CELL).text.strip()
    except (NoSuchElementException, StaleElementReferenceException):
        return None, None
    if page_text != EXPECTED_PAGE_TEXT:
        log(f"    [WARN] 맨 위 행의 페이지가 '{EXPECTED_PAGE_TEXT}'가 아니라 '{page_text}' — "
            f"아직 목록 갱신 전이거나 이 계정에 다른 요청이 섞였을 수 있음")
        return None, None
    return top_row, reqtime_text


def poll_download_manager(driver, new_handle, request_click_time):
    log("⑤ 다운로드관리자 새 창에서 진척도 폴링 시작 (완료될 때까지 무한 대기)")
    log(f"    내 요청 클릭시각: {request_click_time:%Y-%m-%d %H:%M:%S} — "
        f"전용 계정 전제로 목록 맨 위 행을 내 요청으로 간주 (페이지 조건: '{EXPECTED_PAGE_TEXT}')")
    driver.switch_to.window(new_handle)
    time.sleep(1.0)
    poll_start = time.time()

    locked_reqtime_text = None  # 한 번 식별된 뒤로는 이 값으로 매 회차 재조회 (행 순서가 바뀌어도 안 흔들리게)
    attempt = 0
    consecutive_error = 0  # 서버가 이 요청을 '오류'로 반환하면 완료로 안 바뀌는 영구 실패다 — 무한 대기 방지
    while True:
        attempt += 1
        safe_click(driver, DLMGR_SEARCH_BUTTON)
        time.sleep(1.0)

        try:
            rows = driver.find_elements(By.CSS_SELECTOR, DLMGR_GRID_ROWS)
        except StaleElementReferenceException:
            rows = []

        if not rows:
            log(f"    [{attempt}회차] 아직 목록 없음, {POLL_INTERVAL_SEC}초 후 재시도")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        if locked_reqtime_text is None:
            target_row, matched_reqtime = find_my_request_row(rows)
            if target_row is None:
                if attempt >= ROW_SEARCH_MAX_ATTEMPTS:
                    raise TimeoutException(
                        f"내 요청 행을 {ROW_SEARCH_MAX_ATTEMPTS}회 시도({attempt * POLL_INTERVAL_SEC}초)"
                        f"해도 못 찾음 — 맨 위 행의 페이지명이 계속 '{EXPECTED_PAGE_TEXT}'가 아니었음. "
                        f"이 계정을 다른 화면/사람과 같이 쓰고 있지 않은지 확인 필요."
                    )
                log(f"    [{attempt}회차] 내 요청으로 추정되는 행을 아직 못 찾음, "
                    f"{POLL_INTERVAL_SEC}초 후 재시도")
                time.sleep(POLL_INTERVAL_SEC)
                continue
            locked_reqtime_text = matched_reqtime
            log(f"    내 요청 행 식별됨 (요청시간={locked_reqtime_text})")
        else:
            # 정상 상황이라면 맨 위 행이 계속 내 요청이어야 하지만(전용 계정 + 순차 실행),
            # 혹시 몰라 요청시간 문자열로 한 번 더 확인하고, 안 맞으면 전체 목록에서 재탐색한다.
            target_row = None
            try:
                top_reqtime = rows[0].find_element(By.CSS_SELECTOR, DLMGR_REQTIME_CELL).text.strip()
                if top_reqtime == locked_reqtime_text:
                    target_row = rows[0]
            except (NoSuchElementException, StaleElementReferenceException):
                pass

            if target_row is None:
                for row in rows:
                    try:
                        reqtime_text = row.find_element(By.CSS_SELECTOR, DLMGR_REQTIME_CELL).text.strip()
                        if reqtime_text == locked_reqtime_text:
                            target_row = row
                            log(f"    [WARN] 내 요청 행이 맨 위가 아니었음(요청시간={locked_reqtime_text}) "
                                f"— 이 계정에 다른 요청이 섞였을 가능성, 확인 필요")
                            break
                    except (NoSuchElementException, StaleElementReferenceException):
                        continue

            if target_row is None:
                log(f"    [{attempt}회차] 식별했던 행(요청시간={locked_reqtime_text})을 목록에서 "
                    f"못 찾음(목록 보관기간 초과 등), {POLL_INTERVAL_SEC}초 후 재시도")
                time.sleep(POLL_INTERVAL_SEC)
                continue

        try:
            status_text = target_row.find_element(By.CSS_SELECTOR, DLMGR_STATUS_CELL).text.strip()
            percent_text = target_row.find_element(By.CSS_SELECTOR, DLMGR_PERCENT_CELL).text.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            log(f"    [{attempt}회차] 상태/진척도 셀을 못 읽음, {POLL_INTERVAL_SEC}초 후 재시도")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        elapsed = time.time() - poll_start
        log(f"    [{attempt}회차, {elapsed:.0f}초 경과] 요청시간={locked_reqtime_text} "
            f"상태={status_text} 진척도={percent_text}")

        # '오류'는 '아직 처리중'과 달리 그대로 둬도 '완료'로 바뀌지 않는 영구 실패 상태다.
        # 예전엔 이 상태를 못 알아채고 while True가 이걸 몇 시간이고 계속 재조회했다
        # (실제로 요청 하나를 9시간 넘게 폴링한 사고가 있었음, 2026-08-26~27). 2회
        # 연속으로 확인되면(혹시 모를 순간적인 표시 오류 방지) 바로 실패로 포기한다.
        if status_text == "오류":
            consecutive_error += 1
            if consecutive_error >= 2:
                log(f"    ❌ 서버가 이 요청을 '오류' 상태로 반환했습니다 "
                    f"(요청시간={locked_reqtime_text}, {elapsed:.0f}초 경과) — "
                    "재시도해도 회복되지 않는 상태라 포기하고 다음 회차로 넘어갑니다.")
                return False
        else:
            consecutive_error = 0

        if status_text == "완료" and "100" in percent_text:
            log(f"    ✅ 다운로드 준비 완료(100%) 확인 (서버 생성 대기시간: {elapsed:.0f}초)")
            try:
                link = target_row.find_element(By.CSS_SELECTOR, DLMGR_FILE_LINK)
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
                driver.execute_script("arguments[0].click();", link)
                log("    파일 링크 클릭 -> 다운로드 시작")
                time.sleep(3.0)  # 다운로드 시작 대기
                return True
            except NoSuchElementException:
                log("    [ERR] 100%인데 다운로드 링크(a.txt-link.black)를 찾지 못함")
                return False

        time.sleep(POLL_INTERVAL_SEC)


# ─────────────────────────────────────────
#  실행 진입점
# ─────────────────────────────────────────
def run_download_macro(driver, baseline=False, start_offset_days=None, end_offset_days=None):
    main_handle = driver.current_window_handle
    t0 = time.time()

    # 이전 회차가 팝업 처리 도중 오류로 끊긴 경우를 대비한 안전장치 — 매 회차 맨 앞에서 확인
    clear_stray_popups(driver)

    goto_extended_order_search(driver)
    set_search_conditions(driver, baseline=baseline,
                           start_offset_days=start_offset_days, end_offset_days=end_offset_days)
    click_search(driver)

    new_handle, request_click_time = click_download_and_handle_popups(driver)
    if not new_handle:
        return False
    t1 = time.time()

    success = poll_download_manager(driver, new_handle, request_click_time)
    t2 = time.time()

    # 새 창 닫고 원래 창으로 복귀
    try:
        driver.close()
    except Exception:
        pass
    driver.switch_to.window(main_handle)

    log(f"    [TIMING] 검색~다운로드신청: {t1-t0:.1f}초 / 서버 생성 대기(폴링): {t2-t1:.1f}초 / 전체: {t2-t0:.1f}초")

    return success

# 창/세션이 완전히 죽었을 때 나는 에러들의 특징적인 문구 — 이 중 하나라도 걸리면
# "재시도하면 알아서 될 문제"가 아니라 "재연결이 필요한 상황"으로 판단한다.
DEAD_SESSION_SIGNATURES = [
    "no such window",
    "target window already closed",
    "web view not found",
    "invalid session id",
    "chrome not reachable",
    "disconnected: not connected to devtools",
    "session deleted",
]


def _is_dead_session_error(e):
    msg = str(e).lower()
    return any(sig in msg for sig in DEAD_SESSION_SIGNATURES)


# goto_extended_order_search()가 상단 메뉴/사이드바 메뉴를 못 찾아서 던지는 TimeoutException의
# 메시지. 브라우저/세션은 멀쩡히 붙어있는데(그래서 DEAD_SESSION_SIGNATURES엔 안 걸림) 이지어드민
# 로그인 세션만 만료돼서 로그인 화면으로 넘어간 경우도 정확히 같은 증상(메뉴를 못 찾음)으로
# 나타난다. DOM을 직접 못 들여다봐서(로그인 화면 구조를 코드로 확신할 수 없음) "로그인 화면이다"
# 라고 단정하진 않되, 같은 메뉴 진입 실패가 반복되면 로그인 만료 가능성을 명시적으로 안내한다
# — 예전엔 이 경우도 그냥 [ERR] ... 오류 발생으로만 찍혀서 "재시도해도 왜 계속 안 되는지"가
# 안 보였다(일반 오류와 구분이 안 됨).
MENU_NAV_FAILURE_SIGNATURES = [
    "'주문/배송' 상단 메뉴 진입 실패",
    "'확장주문검색2' 진입 실패",
]


def _is_menu_nav_failure(e):
    msg = str(e)
    return any(sig in msg for sig in MENU_NAV_FAILURE_SIGNATURES)


def _watch_folder():
    """watchdog이 감시하는 폴더. watchdog_agent와 같은 규칙으로 결정한다."""
    env = os.getenv("UPH_WATCH_FOLDER")
    if env:
        return env
    try:
        from hub import paths
        if paths.IS_FROZEN:
            return os.path.join(paths.APP_DIR, "WMS_다운로드")
    except ImportError:
        pass
    return r"C:\ENCLU\WMS_다운로드"


def _connect_driver():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=options)

    # ⚠️ 다운로드 저장 위치를 코드로 강제한다.
    #    예전에는 크롬 프로필 설정에만 의존했다. 새 PC에서는 디버그 프로필이 새로
    #    만들어져 기본값(%USERPROFILE%\Downloads)으로 저장되는데, watchdog은
    #    WMS_다운로드 폴더만 본다. 그러면 매크로는 계속 받고 에이전트는 아무것도
    #    못 읽는데 두 프로세스 다 살아있어서 겉으로는 정상으로 보인다
    #    ("다운로드 폴더엔 파일이 쌓이는데 DB는 그대로" — 실제로 겪은 실패 모드).
    folder = _watch_folder()
    try:
        os.makedirs(folder, exist_ok=True)
        driver.execute_cdp_cmd("Page.setDownloadBehavior",
                               {"behavior": "allow", "downloadPath": folder})
        log(f"[OK] 크롬 다운로드 위치를 감시 폴더로 지정: {folder}")
    except Exception as e:
        # CDP가 막혀도 매크로 자체는 돌아가야 한다 — 대신 어긋날 수 있음을 알린다.
        log(f"[WARN] 다운로드 위치를 자동 지정하지 못했습니다: {type(e).__name__}: {e}")
        log(f"       크롬 설정(chrome://settings/downloads)에서 직접 {folder} 로 맞춰주세요.")
    return driver


def run_forever():
    """브라우저에 한 번만 연결하고, 이후로는 계속 반복 실행 (제어판 등에서 계속 켜두는 용도).
    baseline 여부는 매 회차마다 플래그 파일 존재로 자동 판단하므로, 최초 1회는 자동으로
    '기준선 설정'(상태=송장만)으로 처리되고 이후 회차부터는 평소 모드(송장+배송)로 진행된다.

    이 매크로는 URL로 새로 접속하는 코드가 없다 (보안코드가 매번 바뀌어 로그인 자동화가
    안 되므로, 사람이 미리 로그인해둔 디버그 크롬 탭을 계속 재사용하는 구조). 그래서 탭/창이
    죽었을 때 할 수 있는 자동 복구는 "디버그 크롬에 다시 연결해서 살아있는 창을 찾는 것"까지이고,
    디버그 크롬 자체가 완전히 꺼져있으면 사람이 다시 켜고 로그인해줘야 한다.
    """
    driver = _connect_driver()
    log(f"브라우저 연결됨: {driver.title}")

    consecutive_reconnect_failures = 0
    consecutive_menu_nav_failures = 0
    round_no = 0
    last_recon_time = 0   # 아직 한 번도 재확인 안 함 -> 기준선 설정 끝나면 곧바로 1회 실행됨
    while True:
        round_no += 1
        baseline_mode = not os.path.exists(BASELINE_FLAG_FILE)
        is_recon_round = (not baseline_mode) and (time.time() - last_recon_time >= RECON_INTERVAL_SEC)

        if is_recon_round:
            log(f"===== {round_no}회차 시작 (오래된 잔여 재확인 모드: 발주일 "
                f"{RECON_START_OFFSET_DAYS}~{RECON_END_OFFSET_DAYS}일) =====")
        else:
            log(f"===== {round_no}회차 시작 {'(기준선 설정 모드)' if baseline_mode else ''} =====")

        try:
            if is_recon_round:
                success = run_download_macro(driver, baseline=False,
                                              start_offset_days=RECON_START_OFFSET_DAYS,
                                              end_offset_days=RECON_END_OFFSET_DAYS)
            else:
                success = run_download_macro(driver, baseline=baseline_mode)
            consecutive_reconnect_failures = 0
            consecutive_menu_nav_failures = 0
            if success:
                log("[DONE] 다운로드 매크로 정상 완료")
                if baseline_mode:
                    with open(BASELINE_FLAG_FILE, "w", encoding="utf-8") as f:
                        f.write(datetime.now().isoformat())
                    log(f"기준선 설정 완료 표시 파일 생성: {BASELINE_FLAG_FILE}")
            else:
                log("[FAIL] 다운로드 매크로 비정상 종료")
            if is_recon_round:
                # 성공/실패 여부와 무관하게 시각을 갱신 — 실패했다고 90초마다 무겁게 재시도하지 않고
                # 다음 정규 주기(RECON_INTERVAL_SEC)에 다시 시도한다.
                last_recon_time = time.time()
        except Exception as e:
            if is_recon_round:
                last_recon_time = time.time()
            if _is_dead_session_error(e):
                # 창/세션이 죽은 케이스는 스택트레이스 도배 없이 짧게만 남긴다 (반복 발생 시 로그가
                # 순식간에 수백 줄씩 불어나는 걸 방지).
                log(f"[ERR] {round_no}회차: 브라우저 창/세션이 끊긴 것으로 보입니다 ({type(e).__name__})")
                log("    [복구시도] 디버그 크롬에 재연결을 시도합니다...")
                try:
                    driver.quit()
                except Exception:
                    pass
                try:
                    driver = _connect_driver()
                    log(f"    [복구성공] 재연결됨: {driver.title}")
                    consecutive_reconnect_failures = 0
                except Exception as reconnect_err:
                    consecutive_reconnect_failures += 1
                    log(f"    [복구실패] 재연결도 실패했습니다 ({consecutive_reconnect_failures}회 연속): {reconnect_err}")
                    log("    ⚠️ 디버그 크롬이 꺼져있거나 이지어드민 탭이 완전히 닫힌 것으로 보입니다.")
                    log('    ⚠️ 다음 명령으로 디버그 크롬을 다시 켜고 이지어드민에 로그인해주세요:')
                    log('        chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\chrome-debug-profile"')
            elif _is_menu_nav_failure(e):
                consecutive_menu_nav_failures += 1
                log(f"[ERR] {round_no}회차: 메뉴 진입에 실패했습니다 ({consecutive_menu_nav_failures}회 연속): {e}")
                if consecutive_menu_nav_failures >= 2:
                    log("    ⚠️ 브라우저는 붙어있는데 같은 지점에서 계속 실패하고 있습니다 — "
                        "이지어드민 로그인 세션이 만료되어 로그인 화면으로 넘어갔을 가능성이 있습니다.")
                    log("    ⚠️ 디버그 크롬 창을 직접 확인해서, 로그인 화면이면 다시 로그인해주세요.")
                else:
                    log(traceback.format_exc())
            else:
                consecutive_menu_nav_failures = 0
                log(f"[ERR] {round_no}회차 오류 발생: {e}")
                log(traceback.format_exc())

        log(f"{LOOP_INTERVAL_SEC}초 대기 후 다음 회차 진행...")
        time.sleep(LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    print("=" * 50)
    print("  UPH WMS 배송파일 자동 다운로드 매크로 (상시 반복 모드)")
    print("=" * 50)
    print()

    if not IS_GUI:
        print("사용 방법:")
        print("  1. Chrome을 디버깅 모드로 먼저 실행하세요:")
        print('     chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\chrome-debug-profile"')
        print("  2. 그 Chrome에서 이지어드민 로그인 후 이 스크립트를 실행하세요")
        print("  3. 이후로는 종료할 때까지 자동으로 계속 반복 실행됩니다.")
        print()

    try:
        run_forever()
    except KeyboardInterrupt:
        log("사용자 요청으로 종료됨")
    except Exception as e:
        log(f"[ERR] 치명적 오류: {e}")
        traceback.print_exc()