"""
상품 매칭 자동화 매크로 (Selenium 기반)

[동작 순서]
1. "판매자옵션코드" 라벨 다음에 나오는 span.search_options 들을 순서대로 클릭
2. 검색 결과 테이블(#grid2)에서 grid2_options 값이 클릭한 span 텍스트와
   일치하는 행을 찾아 더블클릭
3. 더블클릭 직후 grid3 테이블의 행 개수가 실제로 늘어났는지 확인하여
   추가 누락을 검증 (늘지 않았으면 팝업 확인 -> 재더블클릭 시도)
4. 더블클릭 직후(또는 검색 결과를 못 찾았을 때) 확인 팝업이 떠 있으면
   확인 버튼을 클릭하고 같은 옵션을 다시 시도 (정상 흐름으로 취급)
5. Ctrl+X로 검색창 초기화 후 다음 옵션 코드로 반복
6. 모든 옵션 코드 처리 완료 후 F9 클릭 전:
   a) auto_count_flag 체크박스 체크
   b) grid3 전체 스캔 -> [샘플] 포함 행의 is_gift 체크
7. 매칭 버튼(.matching_action / F9) 클릭
8. 다음 매칭 건으로 넘어가서 반복
"""

import sys
import io
import time
import traceback
from collections import Counter
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
    ElementNotInteractableException, ElementClickInterceptedException,
    UnexpectedAlertPresentException, NoAlertPresentException
)

# ── stdout UTF-8 강제 설정 (Windows cp949 환경에서 한글/이모지 깨짐 방지) ──
# ⚠️ 콘솔 없는 exe(통합 시스템) 안에서는 sys.stdout이 None이라 .buffer 접근이
#    AttributeError로 죽는다. 그것도 import 시점에 죽어서 매크로가 아예 안 뜬다.
#    (자가진단으로 실제 발견) 그래서 있을 때만 감싼다.
def _force_utf8(name):
    stream = getattr(sys, name, None)
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        setattr(sys, name, io.TextIOWrapper(
            buf, encoding="utf-8", errors="replace", line_buffering=True))


_force_utf8("stdout")
_force_utf8("stderr")

# GUI(subprocess)로 실행 중인지 판단 (stdin이 tty가 아니면 GUI 모드)
IS_GUI = (not sys.stdin) or (not sys.stdin.isatty())

# ─────────────────────────────────────────
#  ★ 설정 영역
# ─────────────────────────────────────────

WAIT_TIMEOUT        = 10    # 검색 결과 대기 시간 (초)
CLICK_DELAY         = 0.4   # 클릭 사이 딜레이 (초)
RESULT_SETTLE_DELAY = 0.6   # 검색 결과 발견 후 더블클릭 전 추가 대기 시간 (초)
MAX_MATCHING_ROUNDS = 0     # 매칭 반복 최대 횟수 (0 = 무한 반복)

OPTION_SPAN_SELECTOR          = "span.search_options"
LABEL_TEXT                    = "판매자옵션코드"
RESULT_TABLE_ID               = "grid2"
RESULT_ROW_SELECTOR           = f"table#{RESULT_TABLE_ID} tbody tr[role='row']"
RESULT_OPTIONS_CELL_SELECTOR  = "td[aria-describedby='grid2_options']"
# ⚠ 'grid3_name'과 동일한 명명 규칙으로 추정한 값 — 실제 사이트에서 컬럼 키 확인 후 다르면 교체 필요.
RESULT_NAME_CELL_SELECTOR     = "td[aria-describedby='grid2_name']"
SEEDING_KEYWORD                = "[시딩]"  # 상품명에 이게 붙어있으면 본품이 아니라 시딩 품목 -> 매칭 대상에서 제외
MATCHING_BTN_SELECTOR         = "button.matching_action, .btn.btn-primary.matching_action"
POPUP_CONTAINER_SELECTOR      = ".ui-dialog:not([style*='display: none']), .modal.show, .swal2-popup"
POPUP_CONFIRM_BTN_TEXT_CANDIDATES = ["확인", "OK", "예"]
AUTO_COUNT_FLAG_SELECTOR      = "#auto_count_flag, input[name='auto_count_flag']"
GIFT_TABLE_ID                 = "grid3"
GIFT_TABLE_ROW_SELECTOR       = f"table#{GIFT_TABLE_ID} tbody tr[role='row']"
GIFT_NAME_CELL_SELECTOR       = "td[aria-describedby='grid3_name']"
GIFT_KEYWORD                  = "[샘플]"
GIFT_CHECKBOX_SELECTOR        = "input[name='is_gift'], input.is_gift, td[aria-describedby='grid3_is_gift'] input"
ASTERISK_TEXT                 = "*"
MATCHING_QTY_CELL_SELECTOR    = "td[aria-describedby='grid3_matching_qty']"
MATCHING_QTY_INPUT_SELECTOR   = "td[aria-describedby='grid3_matching_qty'] input.matching_qty"
GIFT_OPTIONS_CELL_SELECTOR    = "td[aria-describedby='grid3_options']"  # grid3에 실제 매칭된 옵션코드 (내용 검증용)

# ── 재시작(reset) 관련 — 검증 실패 시 삭제 대신 팝업을 통째로 닫고 처음부터 다시 여는 방식 ──
MODAL_CLOSE_BTN_SELECTOR      = "button.btn.btn-default[data-dismiss='modal']"
GRID1_INQUIRY_BTN_SELECTOR    = "table#grid1 span.matching[rowid='0']"  # grid1 리스트 맨 위 행의 '조회' 버튼
LOAD_NEXT_MATCHING_CHECKBOX_ID = "load_next_matching"

# ─────────────────────────────────────────
#  헬퍼 함수
# ─────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    try:
        print(f"[{ts}] {msg}", flush=True)
    except Exception:
        pass


def safe_find_elements(driver, selector):
    try:
        return driver.find_elements(By.CSS_SELECTOR, selector)
    except UnexpectedAlertPresentException:
        check_and_handle_native_alert(driver)
        try:
            return driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            return []


def check_and_handle_native_alert(driver):
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


def safe_click(driver, element):
    try:
        element.click()
        return True
    except UnexpectedAlertPresentException:
        return True
    except (ElementNotInteractableException, ElementClickInterceptedException):
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except UnexpectedAlertPresentException:
            return True
        except Exception:
            return False


def safe_double_click(driver, element, actions):
    try:
        actions.double_click(element).perform()
        return True
    except UnexpectedAlertPresentException:
        return True
    except Exception:
        try:
            driver.execute_script("""
                var el = arguments[0];
                var evt = new MouseEvent('dblclick', {bubbles:true, cancelable:true, view:window});
                el.dispatchEvent(evt);
            """, element)
            return True
        except UnexpectedAlertPresentException:
            return True
        except Exception:
            return False


def get_option_spans(driver):
    check_and_handle_native_alert(driver)
    all_spans = safe_find_elements(driver, OPTION_SPAN_SELECTOR)
    if not all_spans:
        return []
    label_index = None
    for idx, span in enumerate(all_spans):
        try:
            if span.text.strip() == LABEL_TEXT:
                label_index = idx
                break
        except StaleElementReferenceException:
            continue
    if label_index is None:
        return []
    return all_spans[label_index + 1:]


def find_matching_result_row(driver, target_text, timeout=WAIT_TIMEOUT):
    """옵션코드가 target_text와 일치하는 행을 찾되, 상품명에 '[시딩]'이 붙은 시딩 품목 행은
    본품이 아니므로 건너뛴다 (2026-08-04: 같은 옵션코드가 본품/시딩 양쪽에 다 있는 경우
    시딩이 먼저 매칭되는 사고가 있어서 추가된 안전장치)."""
    check_and_handle_native_alert(driver)
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: len(safe_find_elements(d, RESULT_ROW_SELECTOR)) > 0
        )
    except TimeoutException:
        return None
    except UnexpectedAlertPresentException:
        check_and_handle_native_alert(driver)
        return None
    rows = safe_find_elements(driver, RESULT_ROW_SELECTOR)
    skipped_seeding = 0
    for row in rows:
        try:
            cell = row.find_element(By.CSS_SELECTOR, RESULT_OPTIONS_CELL_SELECTOR)
            if cell.text.strip() != target_text.strip():
                continue
            try:
                name_cell = row.find_element(By.CSS_SELECTOR, RESULT_NAME_CELL_SELECTOR)
                if SEEDING_KEYWORD in name_cell.text:
                    skipped_seeding += 1
                    continue  # 시딩 품목 -> 본품이 따로 있을 수 있으니 다음 행에서 계속 찾음
            except NoSuchElementException:
                pass  # 상품명 셀을 못 찾으면 필터링 없이 진행 (선택자 이름이 다를 수 있음)
            return row
        except (NoSuchElementException, StaleElementReferenceException):
            continue
        except UnexpectedAlertPresentException:
            check_and_handle_native_alert(driver)
            continue
    if skipped_seeding:
        log(f"    [WARN] '{target_text}' 검색결과 중 시딩 품목 {skipped_seeding}건은 건너뛰었고, 본품 행을 못 찾음")
    return None


def wait_until_row_stable(driver, target_text, settle_delay=RESULT_SETTLE_DELAY):
    time.sleep(settle_delay)
    row = find_matching_result_row(driver, target_text, timeout=3)
    if row is None:
        return None
    time.sleep(0.15)
    return find_matching_result_row(driver, target_text, timeout=3)


def find_matching_button(driver, _retried=False):
    check_and_handle_native_alert(driver)
    buttons = safe_find_elements(driver, MATCHING_BTN_SELECTOR)
    for btn in buttons:
        if btn.is_displayed():
            return btn

    # 못 찾은 첫 시도라면, 창이 작아서 반응형 레이아웃으로 버튼이 숨었을 가능성이 있다.
    # 최대화하고 딱 한 번만 다시 찾아본다(계속 없으면 무한루프 방지를 위해 포기).
    if not _retried:
        log("  [WARN] 매칭 버튼을 못 찾음 — 창을 최대화하고 한 번 더 확인합니다")
        try:
            driver.maximize_window()
            time.sleep(0.5)
        except Exception as e:
            log(f"  [WARN] 창 최대화 재시도 실패: {e}")
        return find_matching_button(driver, _retried=True)
    return None


def clear_search_input(driver):
    check_and_handle_native_alert(driver)
    actions = ActionChains(driver)
    try:
        actions.key_down(Keys.CONTROL).send_keys('x').key_up(Keys.CONTROL).perform()
    except UnexpectedAlertPresentException:
        check_and_handle_native_alert(driver)
        return
    time.sleep(0.15)
    log("  Ctrl+X -> 검색 초기화")


def check_and_handle_popup(driver, timeout=1.5, max_retries=20):
    found_any = False
    for attempt in range(max_retries):
        if check_and_handle_native_alert(driver):
            found_any = True
            time.sleep(0.3)
            continue
        try:
            popup = WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, POPUP_CONTAINER_SELECTOR))
            )
        except TimeoutException:
            if found_any:
                log("    [OK] 모든 팝업이 사라졌습니다")
            return found_any
        found_any = True
        log(f"    [POPUP] 팝업 감지 ({attempt + 1}번째) -> 확인 버튼 클릭 시도")
        closed = False
        for text in POPUP_CONFIRM_BTN_TEXT_CANDIDATES:
            try:
                xpath = (f".//button[contains(normalize-space(text()), '{text}')] | "
                         f".//a[contains(normalize-space(text()), '{text}')]")
                btn = popup.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    safe_click(driver, btn)
                    log(f"    [OK] 팝업 확인 버튼('{text}') 클릭")
                    time.sleep(0.3)
                    closed = True
                    break
            except NoSuchElementException:
                continue
        if not closed:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, ".swal2-confirm")
                if btn.is_displayed():
                    safe_click(driver, btn)
                    log("    [OK] 팝업 swal2-confirm 클릭")
                    time.sleep(0.3)
                    closed = True
            except NoSuchElementException:
                pass
        if not closed:
            log(f"    [WARN] 팝업 확인 버튼 못 찾음 ({attempt + 1}/{max_retries})")
            time.sleep(0.5)
    log(f"    [WARN] {max_retries}회 시도 후에도 팝업 존재 -> 루프 종료")
    return found_any


def get_grid3_row_count(driver):
    return len(safe_find_elements(driver, GIFT_TABLE_ROW_SELECTOR))


def wait_for_grid3_row_increase(driver, before_count, expected_index, timeout=4.0):
    check_and_handle_native_alert(driver)
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = safe_find_elements(driver, GIFT_TABLE_ROW_SELECTOR)
        if len(rows) > before_count:
            return True, rows
        time.sleep(0.1)
    rows = safe_find_elements(driver, GIFT_TABLE_ROW_SELECTOR)
    return False, rows


def set_matching_qty(driver, row_index, qty):
    target_rowid = str(row_index + 1)
    try:
        qty_input = driver.find_element(
            By.CSS_SELECTOR, f"input.matching_qty[rowid='{target_rowid}']"
        )
        log(f"    (rowid={target_rowid} input 탐색 성공)")
    except NoSuchElementException:
        rows = safe_find_elements(driver, GIFT_TABLE_ROW_SELECTOR)
        if row_index >= len(rows):
            log(f"    [WARN] grid3 {row_index+1}번째 행 없음 -> 수량 변경 스킵")
            return False
        try:
            qty_input = rows[row_index].find_element(By.CSS_SELECTOR, MATCHING_QTY_INPUT_SELECTOR)
        except NoSuchElementException as e:
            log(f"    [WARN] 수량 input 못 찾음: {e}")
            return False
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", qty_input)
        time.sleep(0.1)
        qty_input.click()
        qty_input.send_keys(Keys.CONTROL, 'a')
        qty_input.send_keys(Keys.DELETE)
        qty_input.send_keys(str(qty))
        qty_input.send_keys(Keys.TAB)
        log(f"    [OK] grid3 {row_index+1}번째 행 매칭 수량 -> {qty} 입력 완료")
        time.sleep(0.2)
        return True
    except Exception as e:
        log(f"    [WARN] 수량 입력 실패: {e}")
        return False


def check_all_gift_rows_in_grid3(driver):
    check_and_handle_native_alert(driver)
    rows = safe_find_elements(driver, GIFT_TABLE_ROW_SELECTOR)
    if not rows:
        log("  grid3 행 없음 (스킵)")
        return
    log(f"  grid3 전체 {len(rows)}행 스캔 중... ('{GIFT_KEYWORD}' 포함 여부 확인)")
    checked_count = 0
    for idx, row in enumerate(rows):
        try:
            name_cell = row.find_element(By.CSS_SELECTOR, GIFT_NAME_CELL_SELECTOR)
            name_text = name_cell.text.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            continue
        if GIFT_KEYWORD not in name_text:
            continue
        log(f"    [GIFT] grid3 {idx+1}번째 행 감지: '{name_text}'")
        try:
            checkbox = row.find_element(By.CSS_SELECTOR, GIFT_CHECKBOX_SELECTOR)
        except NoSuchElementException:
            log(f"    [WARN] {idx+1}번째 행 is_gift 체크박스 못 찾음")
            continue
        try:
            if not checkbox.is_selected():
                driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
                time.sleep(0.1)
                if safe_click(driver, checkbox):
                    checked_count += 1
                    log(f"    [OK] {idx+1}번째 행 is_gift 체크 완료")
            else:
                log(f"    {idx+1}번째 행 is_gift 이미 체크됨")
        except Exception as e:
            log(f"    [ERR] {idx+1}번째 행 is_gift 체크 실패: {e}")
    log(f"  grid3 스캔 완료 (신규 체크: {checked_count}건)")


def check_auto_count_flag(driver):
    check_and_handle_native_alert(driver)
    try:
        checkbox = driver.find_element(By.CSS_SELECTOR, AUTO_COUNT_FLAG_SELECTOR)
    except NoSuchElementException:
        log("  [WARN] auto_count_flag 체크박스 못 찾음")
        return False
    try:
        if not checkbox.is_selected():
            driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
            time.sleep(0.15)
            if safe_click(driver, checkbox):
                log("  [OK] auto_count_flag 체크 완료")
            return True
        else:
            log("  auto_count_flag 이미 체크됨")
            return True
    except Exception as e:
        log(f"  [ERR] auto_count_flag 체크 실패: {e}")
        return False


# ─────────────────────────────────────────
#  재시작(reset) — 검증 실패 시 삭제 대신 팝업을 통째로 닫고 처음부터 다시 여는 방식
#  (2026-08-04: grid3 삭제 버튼으로 잘못된 행만 지우는 것보다, 아예 닫고 다시 열어서
#   완전히 새 상태로 시작하는 게 더 안전하다고 판단 — 애매하게 반쯤 걸친 상태가 안 남음)
# ─────────────────────────────────────────

def close_matching_modal(driver):
    check_and_handle_native_alert(driver)
    try:
        btn = driver.find_element(By.CSS_SELECTOR, MODAL_CLOSE_BTN_SELECTOR)
    except NoSuchElementException:
        log("  [WARN] '닫기' 버튼을 못 찾음")
        return False
    if not safe_click(driver, btn):
        log("  [WARN] '닫기' 버튼 클릭 실패")
        return False
    log("  [OK] '닫기' 클릭 완료")
    time.sleep(CLICK_DELAY)
    check_and_handle_native_alert(driver)
    return True


def ensure_load_next_matching_checked(driver):
    """'연속매칭' 체크박스가 켜져 있는지 확인하고, 안 켜져 있으면 켠다.
    이미 켜져 있는데 실수로 다시 클릭하면 꺼져버리므로 반드시 is_selected()로 먼저 확인한다."""
    try:
        checkbox = driver.find_element(By.ID, LOAD_NEXT_MATCHING_CHECKBOX_ID)
    except NoSuchElementException:
        log("  [WARN] '연속매칭' 체크박스를 못 찾음")
        return False
    try:
        if checkbox.is_selected():
            log("  '연속매칭' 이미 체크되어 있음")
            return True
        driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
        time.sleep(0.15)
        if safe_click(driver, checkbox):
            log("  [OK] '연속매칭' 체크 완료")
            return True
        log("  [WARN] '연속매칭' 체크 클릭 실패")
        return False
    except Exception as e:
        log(f"  [ERR] '연속매칭' 체크 확인 중 오류: {e}")
        return False


def open_matching_session(driver, timeout=WAIT_TIMEOUT):
    """grid1 리스트 맨 위(rowid=0) '조회' 버튼을 눌러 매칭 팝업을 열고, '연속매칭'을 체크한다.
    맨 처음 시작할 때와, 재시작할 때 둘 다 이 함수 하나로 처리한다."""
    check_and_handle_native_alert(driver)
    try:
        btn = driver.find_element(By.CSS_SELECTOR, GRID1_INQUIRY_BTN_SELECTOR)
    except NoSuchElementException:
        log("  [WARN] grid1 맨 위 행의 '조회' 버튼을 못 찾음 (리스트에 남은 매칭 건이 없을 수 있음)")
        return False
    if not safe_click(driver, btn):
        log("  [WARN] '조회' 버튼 클릭 실패")
        return False
    log("  [OK] '조회' 클릭 완료 -> 매칭 팝업 로드 대기 중...")

    try:
        WebDriverWait(driver, timeout).until(
            lambda d: len(safe_find_elements(d, OPTION_SPAN_SELECTOR)) > 0
                      or d.find_elements(By.ID, LOAD_NEXT_MATCHING_CHECKBOX_ID)
        )
    except TimeoutException:
        log("  [WARN] 매칭 팝업이 예상 시간 안에 안 뜸")
        return False

    time.sleep(CLICK_DELAY)
    return ensure_load_next_matching_checked(driver)


def restart_matching_session(driver):
    """검증 실패 시: '닫기' -> grid1 맨 위 '조회' -> '연속매칭' 확인, 순서로 완전히 새로 시작한다."""
    log("  🔁 재시작 진행: 닫기 -> 조회 -> 연속매칭 확인")
    if not close_matching_modal(driver):
        return False
    time.sleep(CLICK_DELAY)
    if not open_matching_session(driver):
        return False
    log("  ✅ 재시작 완료 — 매칭 매크로 재개")
    return True


# ─────────────────────────────────────────
#  검증 — 위(옵션코드 span) vs 아래(grid3에 실제 매칭된 행) 개수 비교
#  (2026-08-04: WMS 화면이 흔들리면서 엉뚱한 행이 매칭되는 사고 방지용 안전장치.
#   grid3에 어떤 옵션코드로 매칭됐는지 보여주는 컬럼을 아직 몰라서 일단 개수 기준으로만 검증함.
#   개수만 맞다고 내용까지 100% 정확하다는 보장은 아니지만, 최소한 "일부 옵션이 아예
#   안 들어갔거나 중복으로 더 들어간" 사고는 확실히 잡아낸다.)
# ─────────────────────────────────────────

def _is_qty_span(driver, span, span_text):
    """'*' 바로 다음에 오는 숫자 span인지 (수량 변경 신호이지 옵션코드가 아님)."""
    if not span_text.isdigit():
        return False
    try:
        prev_text = driver.execute_script("""
            var el = arguments[0];
            var prev = el.previousSibling;
            if (prev && prev.nodeType === 3) return prev.textContent.trim();
            return '';
        """, span)
        return prev_text == ASTERISK_TEXT
    except Exception:
        return False


def count_real_option_spans(driver, spans):
    """spans 중에서 실제로 매칭 클릭 대상인 것(수량 변경 '*' span 제외)의 텍스트 목록."""
    codes = []
    for span in spans:
        try:
            text = span.text.strip()
        except StaleElementReferenceException:
            continue
        if not text:
            continue
        if _is_qty_span(driver, span, text):
            continue
        codes.append(text)
    return codes


def get_grid3_option_codes(driver):
    """grid3에 현재 매칭돼 있는 옵션코드 목록 (grid3_options 컬럼 기준)."""
    codes = []
    rows = safe_find_elements(driver, GIFT_TABLE_ROW_SELECTOR)
    for row in rows:
        try:
            cell = row.find_element(By.CSS_SELECTOR, GIFT_OPTIONS_CELL_SELECTOR)
            codes.append(cell.text.strip())
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return codes


# ─────────────────────────────────────────
#  옵션 코드 처리 루프
# ─────────────────────────────────────────

def process_one_matching_item(driver):
    actions = ActionChains(driver)
    processed_count = 0
    initial_grid3_codes = get_grid3_option_codes(driver)

    while True:
        spans = get_option_spans(driver)

        if not spans:
            log("  [DONE] 옵션 코드 없음 -> 매칭 버튼 단계로")
            return "success"

        if processed_count >= len(spans):
            log(f"  [DONE] 옵션 코드 {len(spans)}개 전부 처리 완료")

            # ── 검증: 위(처리해야 했던 옵션코드) vs 아래(grid3에 새로 들어간 옵션코드) 내용 비교 ──
            # 개수만 맞다고 넘어가지 않고, 실제로 "어떤 코드"가 들어갔는지까지 비교한다
            # (순서가 흔들려도 상관없게 멀티셋 비교; 같은 코드가 여러 번 나올 수 있어서 Counter 사용)
            expected_codes = count_real_option_spans(driver, spans)
            current_grid3_codes = get_grid3_option_codes(driver)
            # 이번 매칭 건 시작 시점 이후로 새로 추가된 코드만 비교 대상 (Counter 차감)
            new_codes = list((Counter(current_grid3_codes) - Counter(initial_grid3_codes)).elements())

            if Counter(new_codes) != Counter(expected_codes):
                missing = list((Counter(expected_codes) - Counter(new_codes)).elements())
                extra = list((Counter(new_codes) - Counter(expected_codes)).elements())
                log(f"  [❌ 검증 실패] 처리해야 할 옵션코드: {expected_codes}")
                log(f"                grid3에 실제 새로 들어간 옵션코드: {new_codes}")
                if missing:
                    log(f"                누락된 코드: {missing}")
                if extra:
                    log(f"                엉뚱하게 더 들어간 코드: {extra}")
                return "mismatch"
            log(f"  [✅ 검증 통과] {expected_codes} 전부 정확히 매칭됨")
            return "success"

        log(f"  전체 옵션: {len(spans)}개 / 처리됨: {processed_count}개")

        span = spans[processed_count]
        try:
            span_text = span.text.strip()
        except StaleElementReferenceException:
            log("  [WARN] span 갱신됨 -> 재시도")
            time.sleep(0.5)
            continue

        # ── * 감지 -> 수량 변경 ──
        if _is_qty_span(driver, span, span_text):
            qty_value = int(span_text)
            if processed_count > 0:
                target_row_index = get_grid3_row_count(driver) - 1
                log(f"  [QTY] '*' 감지 -> grid3 {target_row_index+1}번째 행 수량을 {qty_value}로 변경")
                set_matching_qty(driver, target_row_index, qty_value)
            else:
                log("  [WARN] 수량 span 감지됐으나 직전 옵션 없음 -> 스킵")
            processed_count += 1
            continue

        log(f"    [{processed_count+1}/{len(spans)}] '{span_text}' 클릭 중...")

        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", span)
            time.sleep(0.3)
            clicked = safe_click(driver, span)
            if not clicked:
                log("  [WARN] span 클릭 실패 -> 재시도")
                time.sleep(0.8)
                continue
            time.sleep(CLICK_DELAY)
        except StaleElementReferenceException:
            log("  [WARN] 클릭 시 span 갱신됨 -> 재시도")
            time.sleep(0.5)
            continue

        # ── 검색 결과 탐색 (최대 3회 재시도) ──
        log(f"    검색 결과 대기 중...")
        matched_row = find_matching_result_row(driver, span_text)

        search_retry = 0
        max_search_retries = 3

        while matched_row is None and search_retry < max_search_retries:
            search_retry += 1
            popup_handled = check_and_handle_popup(driver)
            if popup_handled:
                log(f"    [POPUP] 팝업 처리 후 재검색")
                time.sleep(CLICK_DELAY)
                matched_row = find_matching_result_row(driver, span_text)
                continue

            log(f"    [WARN] '{span_text}' 검색 결과 없음 (재시도 {search_retry}/{max_search_retries}) -> span 재클릭")
            try:
                fresh_spans = get_option_spans(driver)
                if processed_count < len(fresh_spans):
                    driver.execute_script("arguments[0].scrollIntoView(true);", fresh_spans[processed_count])
                    time.sleep(0.2)
                    safe_click(driver, fresh_spans[processed_count])
                    time.sleep(CLICK_DELAY + 0.3 * search_retry)
            except Exception as e:
                log(f"    [WARN] 재클릭 오류: {e}")
            matched_row = find_matching_result_row(driver, span_text, timeout=WAIT_TIMEOUT)

        if matched_row is None:
            log(f"    [MISS] '{span_text}' {max_search_retries}회 재시도 후에도 결과 없음 -> 누락 가능성! 수동 확인 필요")
            clear_search_input(driver)
            time.sleep(CLICK_DELAY)
            processed_count += 1
            continue

        log(f"    일치하는 행 발견 -> 안정화 대기 중...")
        stable_row = wait_until_row_stable(driver, span_text)

        if stable_row is None:
            popup_handled = check_and_handle_popup(driver)
            if popup_handled:
                log(f"    [POPUP] 팝업 처리 후 재시도")
                time.sleep(CLICK_DELAY)
                continue
            log(f"    [WARN] 안정화 실패 -> 스킵")
            clear_search_input(driver)
            time.sleep(CLICK_DELAY)
            processed_count += 1
            continue

        # ── 더블클릭 ──
        check_and_handle_native_alert(driver)
        grid3_count_before = get_grid3_row_count(driver)

        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", stable_row)
            time.sleep(0.15)
            dbl_ok = safe_double_click(driver, stable_row, actions)
            if not dbl_ok:
                log(f"    [WARN] 더블클릭 실패 -> 스킵")
                clear_search_input(driver)
                time.sleep(CLICK_DELAY)
                processed_count += 1
                continue
            log(f"    더블클릭 완료")
        except UnexpectedAlertPresentException:
            log(f"    더블클릭 완료 (alert 발생)")
        except StaleElementReferenceException:
            log(f"    [WARN] 더블클릭 시 행 갱신됨 -> 재시도")
            time.sleep(0.3)
            continue
        except Exception as e:
            log(f"    [WARN] 더블클릭 오류({e}) -> 스킵")
            clear_search_input(driver)
            time.sleep(CLICK_DELAY)
            processed_count += 1
            continue

        # ── 더블클릭 직후 alert 처리 ──
        native_alert_handled = check_and_handle_native_alert(driver)
        if native_alert_handled:
            log(f"    (alert 확인 클릭 완료, 매칭 정상 진행)")
        else:
            time.sleep(0.2)

        # ── grid3 행 증가 검증 (최대 3회 재시도) ──
        row_increased, grid3_rows_now = wait_for_grid3_row_increase(
            driver, grid3_count_before, processed_count
        )

        retry_attempt = 0
        max_dbl_retries = 3

        while not row_increased and retry_attempt < max_dbl_retries:
            retry_attempt += 1
            log(f"    [WARN] grid3 행 증가 없음 (재시도 {retry_attempt}/{max_dbl_retries})")

            popup_handled = check_and_handle_popup(driver)
            if popup_handled:
                log(f"    [POPUP] 팝업 처리 후 grid3 재확인")
                time.sleep(CLICK_DELAY)
                row_increased, grid3_rows_now = wait_for_grid3_row_increase(
                    driver, grid3_count_before, processed_count, timeout=2.0
                )
                if row_increased:
                    break

            log(f"    재더블클릭 시도")
            retry_row = find_matching_result_row(driver, span_text, timeout=2)
            if retry_row is None:
                log(f"    검색결과 사라짐 -> span 재클릭")
                try:
                    fresh_spans = get_option_spans(driver)
                    if processed_count < len(fresh_spans):
                        driver.execute_script("arguments[0].scrollIntoView(true);", fresh_spans[processed_count])
                        time.sleep(0.2)
                        safe_click(driver, fresh_spans[processed_count])
                        time.sleep(CLICK_DELAY)
                except Exception:
                    pass
                retry_row = find_matching_result_row(driver, span_text, timeout=2)

            if retry_row is not None:
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", retry_row)
                    time.sleep(0.2)
                    safe_double_click(driver, retry_row, actions)
                except UnexpectedAlertPresentException:
                    pass
                check_and_handle_native_alert(driver)
                time.sleep(CLICK_DELAY + 0.2 * retry_attempt)
                row_increased, grid3_rows_now = wait_for_grid3_row_increase(
                    driver, grid3_count_before, processed_count, timeout=2.5
                )

        if not row_increased:
            log(f"    [MISS] {max_dbl_retries}회 재시도 후에도 grid3 행 증가 없음 -> '{span_text}' 수동 확인 필요")
        else:
            if retry_attempt > 0:
                log(f"    [OK] {retry_attempt}회 재시도 후 grid3 행 증가 확인됨")
            else:
                log(f"    [OK] grid3 행 증가 확인됨 (총 {len(grid3_rows_now)}행)")

        time.sleep(CLICK_DELAY)
        check_and_handle_popup(driver)
        clear_search_input(driver)
        time.sleep(CLICK_DELAY)

        processed_count += 1
        log(f"    [OK] {processed_count}/{len(spans)}번째 옵션 처리 완료\n")


# ─────────────────────────────────────────
#  전체 매크로 (매칭 건 반복)
# ─────────────────────────────────────────

def run_matching_macro(driver):
    log("=" * 50)
    log("상품 매칭 매크로 시작")
    log("=" * 50)

    round_num = 0
    consecutive_mismatch = 0
    MAX_CONSECUTIVE_MISMATCH = 3  # 같은 건이 계속 실패하면(예: 화면이 근본적으로 안 맞는 상황) 무한반복 방지

    while True:
        round_num += 1
        log(f"\n[{round_num}번째 매칭 건 처리 시작]")

        result = process_one_matching_item(driver)

        if result == "mismatch":
            consecutive_mismatch += 1
            log(f"  (연속 검증실패 {consecutive_mismatch}/{MAX_CONSECUTIVE_MISMATCH}회)")

            if consecutive_mismatch >= MAX_CONSECUTIVE_MISMATCH:
                log("")
                log(f"🛑 같은 매칭 건이 {MAX_CONSECUTIVE_MISMATCH}회 연속 검증 실패했습니다 — "
                    "재시작으로도 해결이 안 되는 것 같아 매크로를 완전히 멈춥니다.")
                log("   이 건은 화면을 직접 열어서 확인해주세요.")
                return False

            if not restart_matching_session(driver):
                log("")
                log("🛑 재시작(닫기->조회->연속매칭)에 실패했습니다 — 매크로를 멈춥니다.")
                log("   화면 상태를 직접 확인해주세요.")
                return False

            round_num -= 1  # 재시작한 건 새 매칭 건이 아니라 같은 건 재시도이므로 회차 번호는 그대로 유지
            continue

        consecutive_mismatch = 0

        log("auto_count_flag 체크박스 확인 중...")
        check_auto_count_flag(driver)

        log("grid3 [샘플] 스캔 중...")
        check_all_gift_rows_in_grid3(driver)

        log("매칭 버튼 찾는 중...")
        matching_btn = find_matching_button(driver)

        if matching_btn is None:
            log("[WARN] 매칭 버튼을 찾지 못했습니다. 수동으로 확인해주세요.")
            return False

        try:
            if not safe_click(driver, matching_btn):
                log("[ERR] 매칭 버튼 클릭 실패 -> 정지")
                return False
            log(f"[OK] {round_num}번째 매칭 건 -> 매칭 버튼 클릭 완료")
        except Exception as e:
            log(f"[ERR] 매칭 버튼 클릭 실패: {e} -> 정지")
            return False

        check_and_handle_native_alert(driver)
        time.sleep(CLICK_DELAY * 2)

        if MAX_MATCHING_ROUNDS > 0 and round_num >= MAX_MATCHING_ROUNDS:
            log(f"\n설정된 반복 횟수({MAX_MATCHING_ROUNDS}회) 도달 -> 매크로 종료")
            return True

        next_spans = get_option_spans(driver)
        if not next_spans:
            log("\n더 이상 처리할 매칭 건이 없습니다 -> 매크로 정상 종료")
            return True


# ─────────────────────────────────────────
#  실행 진입점
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  상품 매칭 자동화 매크로")
    print("=" * 50)
    print()

    if not IS_GUI:
        print("사용 방법:")
        print("  1. Chrome을 디버깅 모드로 먼저 실행하세요:")
        print('     chrome.exe --remote-debugging-port=9224 --user-data-dir="C:\\chrome-debug-profile-macro"')
        print("  2. 그 Chrome에서 매칭 팝업을 열어둔 상태로 이 스크립트를 실행하세요")
        print()

    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9224")
    driver = webdriver.Chrome(options=options)

    # 크롬 창이 작으면 이지어드민이 반응형 레이아웃으로 바뀌면서 '매칭' 버튼이
    # 화면에 아예 안 그려지거나 숨겨져서, 셀렉터는 맞는데도 매크로가 못 찾고
    # 멈추는 사고가 실제로 있었다(2026-08-19). 시작할 때 항상 최대화해서 예방한다.
    try:
        driver.maximize_window()
        log("[OK] 크롬 창 최대화 완료")
    except Exception as e:
        log(f"[WARN] 크롬 창 최대화 실패(무시하고 진행): {e}")

    log(f"브라우저 연결됨: {driver.title}")

    try:
        # 매칭 팝업이 이미 열려있으면(옵션코드 span이 보이면) 그대로 진행,
        # 안 열려있으면 grid1 맨 위 '조회' -> '연속매칭' 체크까지 자동으로 진행
        if not get_option_spans(driver):
            log("매칭 팝업이 아직 안 열려있는 것으로 보여, 자동으로 시작합니다 (조회 -> 연속매칭)...")
            if not open_matching_session(driver):
                log("[FAIL] 매칭 시작에 실패했습니다 — grid1 목록/조회 버튼 상태를 확인해주세요.")
                raise SystemExit(1)

        success = run_matching_macro(driver)
        if success:
            log("[DONE] 매크로 정상 완료")
        else:
            log("[FAIL] 매크로 비정상 종료")
    except Exception as e:
        log(f"[ERR] 오류 발생: {e}")
        traceback.print_exc()
    finally:
        if not IS_GUI:
            try:
                input("\n[Enter] 키를 눌러 종료...")
            except EOFError:
                pass