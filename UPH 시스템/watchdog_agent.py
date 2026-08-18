"""
ENCLU UPH 실시간 현황판 — 로컬 감시 에이전트 (v3)

v3 변경점 (2026-08-06):
  - watchdog 라이브러리의 파일 이벤트 감시를 걷어내고 직접 폴링 방식으로 전환.
    이벤트 방식은 감시를 담당하는 emitter 스레드가 조용히 죽어도 Observer는 살아있는 것으로
    보여서, 몇 시간씩 새 파일을 하나도 처리 안 하는 상태를 자동으로 알아챌 수 없었음.

v2 변경점 (기존 대비):
  - detected_at(파일을 감지한 시각) 의존을 제거하고,
    WMS가 실제로 내려주는 업무 일시(송장일_날짜/시간, 배송일_날짜/시간)를 정식 컬럼으로 저장.
  - '배송 보류' 헤더를 그대로 반영해 is_hold 컬럼으로 저장 (기존엔 CS 드롭다운값 중 '보류'를 썼음).
  - 이 3개 값이 바뀔 수 있으므로(특히 보류 해제) 캐시 비교 키에 is_hold 포함.

역할:
  1. 지정된 감시 폴더(WMS 배송파일 다운로드 폴더)를 주기적으로(POLL_INTERVAL_SEC) 확인
  2. 가장 최신 파일이 아직 처리 안 된 것이면 읽어서, 각 행(주문 상품 줄)의 상태를 이전 상태와 비교
     (파일 하나가 매번 전체 스냅샷이라 최신 것 하나만 처리하면 충분)
  3. 상태(발주/접수/송장/배송) 또는 CS/보류가 바뀐 행만 Supabase로 push
  4. 판매처 → 동(A/B/F) 매핑은 sales_channel_dong_mapping 테이블을 주기적으로 조회해 반영

실행 방식:
  - 개발/테스트: `python watchdog_agent.py`
  - 실제 배포: pythonw.exe로 콘솔창 없이 백그라운드 실행 (ENCLU SCM ALL SYSTEM 런처와 동일 패턴)

필요 패키지: pandas, xlrd, openpyxl, sqlalchemy, psycopg2-binary, python-dotenv, beautifulsoup4, lxml

⚠️ 반드시 migration_uph_v2.sql을 Supabase에 먼저 실행한 뒤 이 에이전트를 가동하세요.
   (order_status_log에 invoice_datetime / delivery_datetime / is_hold 컬럼이 없으면 push_to_db가 실패합니다.)
"""

import os
import sys
import io
import time
import json
import sqlite3
import logging
from datetime import datetime, timezone, timedelta

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from psycopg2.extras import execute_values

# ══════════════════════════════════════════════════════════════
# 설정 (.env에서 읽음)
# ══════════════════════════════════════════════════════════════
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")                     # 기존 Streamlit 앱과 동일한 Supabase 접속정보 재사용


def _default_watch_folder() -> str:
    """감시 폴더 기본값.

    통합 exe로 배포됐을 때는 **프로그램 폴더 안**에 만든다.
    예전 기본값은 C:\\ENCLU\\WMS_다운로드 였는데, 설치 위치로 안내하는
    C:\\ENCLU_SCM\\ 과 이름만 비슷한 전혀 다른 폴더라 "폴더가 안 생긴다"는
    신고가 실제로 있었다. 프로그램 옆에 있으면 찾을 일이 없다.

    단독 실행(.py)일 때는 예전 기본값을 유지한다 — 기존 운영 PC는 .env의
    UPH_WATCH_FOLDER로 경로를 지정해 쓰고 있어 어차피 영향을 받지 않는다.
    """
    try:
        from hub import paths
        if paths.IS_FROZEN:
            return os.path.join(paths.APP_DIR, "WMS_다운로드")
    except ImportError:
        pass
    return r"C:\ENCLU\WMS_다운로드"


WATCH_FOLDER = os.getenv("UPH_WATCH_FOLDER") or _default_watch_folder()  # WMS 파일이 떨어지는 폴더
CACHE_DB_PATH = os.getenv("UPH_CACHE_DB", "uph_agent_cache.sqlite3")     # 로컬 "직전 상태" 캐시
POLL_INTERVAL_SEC = int(os.getenv("UPH_POLL_INTERVAL_SEC", "10"))       # 폴더 감시 주기(초)
MAPPING_REFRESH_SEC = int(os.getenv("UPH_MAPPING_REFRESH_SEC", "300"))  # 판매처→동 매핑 갱신 주기(초)
FILE_STABLE_WAIT_SEC = 2   # 파일이 완전히 저장될 때까지 대기 (다운로드 도중 읽기 방지)
KEEP_LATEST_FILES = int(os.getenv("UPH_KEEP_LATEST_FILES", "5"))  # 감시폴더에 최신 몇 개 파일만 남기고 정리할지

KST = timezone(timedelta(hours=9))

# 통합 허브 exe 안에서 돌 때는 __file__이 실행할 때마다 지워지는 임시 폴더라
# 로그가 남지 않는다. UPH 제어판이 이 로그를 읽어 상태를 보여주므로 화면이 비어버린다.
# 그래서 허브가 UPH_LOG_FILE로 쓰기 가능한 경로를 지정해주면 그쪽을 쓴다.
LOG_FILE_PATH = os.getenv("UPH_LOG_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "uph_agent.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("uph_agent")

# WMS 파일 컬럼 → 내부 표준 컬럼 매핑 (실제 WMS 다운로드 파일 헤더 그대로 사용)
COL_MGMT_NO = "관리번호"
COL_CHANNEL = "판매처"
COL_STATUS = "상태"
COL_INVOICE = "송장번호"
COL_PRODUCT_CODE = "상품코드"
COL_PRODUCT_NAME = "상품명"
COL_CS = "CS"
COL_QTY = "상품수량"

# v2 신규 컬럼 (배송일시/송장일시/보류 — WMS 다운로드 항목 설정에 추가된 헤더)
COL_HOLD = "배송 보류"
COL_INVOICE_DATE = "송장일_날짜"
COL_INVOICE_TIME = "송장일_시간"
COL_DELIVERY_DATE = "배송일_날짜"
COL_DELIVERY_TIME = "배송일_시간"

EXTRA_COLS = ["주문번호", "주문상세번호", "옵션명", "로케이션", "바코드",
              "주문일", "주문시간", "발주일", "발주시간", "송장입력일", "주문수량"]

# 취소 계열로 간주해 수량 합계에서 제외할 CS 값.
# ⚠️ app.py의 CANCELLED_CS_VALUES와 동일하게 유지해야 한다 —
#    여기서 제외한 수량과 대시보드가 필터링하는 기준이 어긋나면 숫자가 안 맞는다.
CANCELLED_CS_VALUES = {
    "취소",
    "취소(배송전+배송후)",
    "배송전 취소",
    "배송후 취소",
    "배송전 전체취소",
    "배송후 전체취소",
    "배송전 전체 취소",
    "배송후 전체 취소",
}

REQUIRED_COLS = [COL_MGMT_NO, COL_CHANNEL, COL_STATUS, COL_INVOICE,
                  COL_PRODUCT_CODE, COL_PRODUCT_NAME, COL_CS, COL_QTY,
                  COL_HOLD, COL_INVOICE_DATE, COL_INVOICE_TIME,
                  COL_DELIVERY_DATE, COL_DELIVERY_TIME]


# ══════════════════════════════════════════════════════════════
# 일시 파싱 헬퍼
# ══════════════════════════════════════════════════════════════
def parse_kst_datetime(date_val, time_val):
    """WMS의 '날짜' + '시간' 두 컬럼(문자열/NaN)을 KST 타임존 붙은 ISO 문자열로 변환.
    둘 중 하나라도 비어있으면(아직 그 단계에 도달 안 한 행) None 반환."""
    if pd.isna(date_val):
        return None
    date_str = str(date_val).strip()
    if not date_str or date_str.lower() in ("nan", "nat"):
        return None

    time_str = str(time_val).strip() if pd.notna(time_val) else ""
    if not time_str or time_str.lower() in ("nan", "nat"):
        time_str = "00:00:00"

    try:
        dt = pd.to_datetime(f"{date_str} {time_str}")
    except Exception:
        return None
    if pd.isna(dt):
        return None

    dt = dt.to_pydatetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.isoformat()


# ══════════════════════════════════════════════════════════════
# DB 연결 + 매핑 캐시
# ══════════════════════════════════════════════════════════════
def get_engine():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL이 .env에 설정되어 있지 않습니다.")
    return create_engine(DATABASE_URL)


class DongMappingCache:
    """sales_channel_dong_mapping을 주기적으로 조회해 메모리에 캐싱.
    WMS 파일마다 판매처명에 공백 표기가 미묘하게 다를 수 있어(예: '아리얼 쇼피(싱가폴)' vs
    '아리얼 쇼피 (싱가폴)'), 공백을 제거한 값을 매칭 키로 사용해 이런 차이를 흡수한다.
    """

    def __init__(self, engine):
        self.engine = engine
        self.mapping = {}
        self.last_refresh = 0
        self.refresh()

    @staticmethod
    def _normalize(name):
        return "".join(str(name).split())  # 모든 공백 제거

    def refresh(self):
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text("SELECT channel_name, dong FROM sales_channel_dong_mapping")).fetchall()
            self.mapping = {self._normalize(r.channel_name): r.dong for r in rows}
            self.last_refresh = time.time()
            log.info(f"판매처→동 매핑 갱신 완료 ({len(self.mapping)}건)")
        except Exception as e:
            log.error(f"매핑 갱신 실패: {e}")

    def get(self, channel_name):
        if time.time() - self.last_refresh > MAPPING_REFRESH_SEC:
            self.refresh()
        return self.mapping.get(self._normalize(channel_name))


# ══════════════════════════════════════════════════════════════
# 로컬 캐시 (직전 상태 저장 — SQLite)
# ══════════════════════════════════════════════════════════════
def init_cache_db():
    conn = sqlite3.connect(CACHE_DB_PATH, check_same_thread=False)
    # v3 캐시: 키가 (order_key, status)이고 quantity까지 비교한다.
    # v1/v2 캐시는 order_key 하나만 키로 썼는데, 한 주문상품이 '송장'과 '배송' 두 상태로
    # 동시에 존재할 수 있어서 캐시 슬롯 하나를 두고 서로 덮어쓰는 문제가 있었다.
    # DB(order_status_log)의 충돌키와 동일하게 맞춰서 이 어긋남을 없앤다.
    # 기존 order_cache 테이블은 건드리지 않는다 (롤백 시 되돌아갈 자리).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_cache_v3 (
            order_key  TEXT NOT NULL,
            status     TEXT NOT NULL,
            cs_status  TEXT,
            is_hold    INTEGER DEFAULT 0,
            quantity   INTEGER DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY (order_key, status)
        )
    """)
    conn.commit()
    return conn


def load_cache_dict(conn):
    """order_cache_v3 전체를 한 번에 메모리로 읽어온다 (행마다 SQLite 왕복하는 것 방지).
    반환: {(order_key, status): (cs_status, is_hold, quantity)}"""
    cur = conn.execute("SELECT order_key, status, cs_status, is_hold, quantity FROM order_cache_v3")
    return {(r[0], r[1]): (r[2], bool(r[3]), int(r[4] or 0)) for r in cur.fetchall()}


def bulk_save_cache(conn, updates):
    """변경된 캐시 항목들을 한 번에 upsert.
    updates: [(order_key, status, cs_status, is_hold, quantity, updated_at), ...]"""
    if not updates:
        return
    conn.executemany("""
        INSERT INTO order_cache_v3 (order_key, status, cs_status, is_hold, quantity, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_key, status) DO UPDATE SET
            cs_status=excluded.cs_status, is_hold=excluded.is_hold,
            quantity=excluded.quantity, updated_at=excluded.updated_at
    """, updates)
    conn.commit()


# ══════════════════════════════════════════════════════════════
# 파일 읽기 + diffing + DB push
# ══════════════════════════════════════════════════════════════
def read_wms_file(filepath):
    """
    ⚠ 모든 경로에서 값을 문자열 그대로 보존한다 (dtype 자동추론 금지).
    안 그러면 pandas가 관리번호/송장번호/전화번호처럼 숫자처럼 보이는 텍스트 컬럼을
    자동으로 숫자로 인식해서 맨 앞자리 0을 통째로 날려버리는 문제가 생긴다
    (file_splitter_gui.py에서 2026-07-29에 동일한 문제를 발견 후 수정한 것과 같은 종류의 버그).
    HTML로 위장된 xls는 원래 pd.read_html을 썼는데, read_html도 내부적으로 dtype 자동추론을 해서
    안전하지 않으므로 BeautifulSoup 직접 파싱으로 전환 (2026-08-03).
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".xls":
        # 이지어드민이 내려주는 '.xls'는 진짜 바이너리 엑셀이 아니라
        # HTML 표를 xls 확장자로 감싼 것일 수도, 진짜 바이너리(OLE2) 엑셀일 수도 있음.
        # 파일 앞부분을 바이너리로 살짝 열어서 실제 포맷을 판별한다.
        with open(filepath, "rb") as f:
            head = f.read(512).lstrip()
        if head.startswith(b"<"):
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                html = f.read()
            df = _parse_html_table_str(html)
            if df is None:
                raise ValueError("HTML로 위장된 xls 파일에서 필요한 컬럼을 가진 표를 찾지 못함")
        else:
            df = pd.read_excel(filepath, engine="xlrd", dtype=str)
    elif ext == ".xlsx":
        df = pd.read_excel(filepath, engine="openpyxl", dtype=str)
    elif ext == ".csv":
        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding="cp949", dtype=str)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")

    df.columns = df.columns.astype(str).str.strip()
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")
    return df


def _parse_html_table_str(html_content):
    """BeautifulSoup으로 직접 파싱 — pd.read_html과 달리 dtype 자동추론을 전혀 안 해서
    숫자처럼 보이는 텍스트(관리번호, 송장번호, 전화번호 등)의 앞자리 0이 안전하게 보존된다.
    REQUIRED_COLS를 전부 포함하는 첫 번째 표를 찾아서 반환. 못 찾으면 None."""
    soup = BeautifulSoup(html_content, "lxml")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [td.get_text(strip=True) for td in rows[0].find_all(["td", "th"])]
        if not all(c in headers for c in REQUIRED_COLS):
            continue
        data = []
        for r in rows[1:]:
            cells = [td.get_text(strip=True) for td in r.find_all("td")]
            if cells:
                data.append(cells)
        df = pd.DataFrame(data, columns=headers[:len(data[0])] if data else headers)
        # 빈 셀이 ""(빈 문자열)로 들어오는데, 다른 읽기 경로(read_excel/read_csv)는 빈 셀을
        # 실제 NaN으로 주기 때문에 pd.notna() 판정이 서로 다르게 동작하지 않도록 맞춰준다.
        df = df.replace("", pd.NA)
        return df
    return None


def merge_duplicate_rows(df, dong_cache):
    """같은 (order_key, status)로 중복되는 행들을 하나로 병합한다.

    WMS의 'UPH현황' 다운로드에는 행을 유일하게 식별하는 컬럼이 없다. 부분취소·부분교환이
    섞인 주문은 관리번호·상품코드·주문상세번호·송장번호가 전부 같은 줄이 수량과 CS만
    다르게 여러 개 내려온다. 실제 확인된 예:

        관리번호=1808854 상품코드=01345 주문상세번호=415421798 수량=1 CS=정상
        관리번호=1808854 상품코드=01345 주문상세번호=415421798 수량=3 CS=정상
        관리번호=1808854 상품코드=01345 주문상세번호=415421798 수량=2 CS=배송전 부분 취소

    이걸 그대로 두면 두 가지 문제가 생긴다 (2026-08-09 추적으로 확인):
      1. 캐시가 매 회차 서로 덮어써서 diffing이 영원히 안정되지 않고, 같은 행이 3분마다
         무한히 재푸시된다.
      2. DB는 (order_key, status)로 UPSERT하므로 여러 줄이 1행으로 뭉개지고, quantity가
         마지막 줄 값으로 덮여 '완료 상품 수량 합계'가 실제보다 적게 나온다.

    병합 규칙:
      - quantity : 취소 계열 CS인 줄을 뺀 나머지를 합산한다. 대시보드가 취소 건을 어차피
                   집계에서 제외하므로, 여기서 미리 빼두면 수량이 실제 출고량과 맞는다.
      - 전부 취소인 그룹 : 취소 상태 그대로 1건 남긴다(수량은 취소분 합계).
                   대시보드가 필터링할 수 있게 기록 자체는 남겨야 한다.
      - is_hold  : 남은 줄 중 하나라도 보류면 True (한 줄이라도 잡혀 있으면 그 주문은 못 나감).
      - 그 외 필드: 첫 줄 값. 중복 줄 사이에서 동일하다.

    반환: {(order_key, status): row dict}
    """
    merged = {}

    for _, row in df.iterrows():
        mgmt_no = str(row[COL_MGMT_NO]).strip()
        # WMS가 같은 상품의 상품코드를 어떤 날은 '3727', 어떤 날은 '03727'처럼 앞자리 0
        # 유무를 다르게 내려주는 경우가 있어, 그대로 키에 쓰면 같은 상품이 서로 다른
        # order_key로 갈라져 상태 추적이 끊긴다 (2026-08-05 확인). 앞자리 0을 제거해 정규화한다.
        product_code = str(row[COL_PRODUCT_CODE]).strip().lstrip("0") or "0"
        order_key = f"{mgmt_no}_{product_code}"

        status = str(row[COL_STATUS]).strip()
        cs_status = str(row[COL_CS]).strip() if pd.notna(row[COL_CS]) else "정상"
        is_hold = str(row[COL_HOLD]).strip() == "보류" if pd.notna(row[COL_HOLD]) else False
        try:
            qty = int(row[COL_QTY]) if pd.notna(row[COL_QTY]) else 1
        except (TypeError, ValueError):
            qty = 1

        is_cancelled = cs_status in CANCELLED_CS_VALUES
        key = (order_key, status)
        entry = merged.get(key)

        if entry is None:
            channel_name = str(row[COL_CHANNEL]).strip()
            extra_data = {
                col: (None if pd.isna(row[col]) else str(row[col]))
                for col in EXTRA_COLS
                if col in df.columns
            }
            entry = merged[key] = {
                "order_key": order_key,
                "invoice_no": str(row[COL_INVOICE]).strip(),
                "channel_name": channel_name,
                "dong": dong_cache.get(channel_name),
                "product_name": str(row[COL_PRODUCT_NAME]).strip(),
                "quantity": 0,
                "status": status,
                "cs_status": cs_status,
                "is_hold": False,
                "invoice_datetime": parse_kst_datetime(row.get(COL_INVOICE_DATE), row.get(COL_INVOICE_TIME)),
                "delivery_datetime": parse_kst_datetime(row.get(COL_DELIVERY_DATE), row.get(COL_DELIVERY_TIME)),
                "extra_data": json.dumps(extra_data, ensure_ascii=False),
                # 병합 과정에서만 쓰는 내부 값 — DB에 넣기 전에 제거한다.
                "_live_qty": 0,
                "_cancelled_qty": 0,
                "_has_live": False,
            }

        if is_cancelled:
            entry["_cancelled_qty"] += qty
        else:
            entry["_live_qty"] += qty
            entry["is_hold"] = entry["is_hold"] or is_hold
            if not entry["_has_live"]:
                # 살아있는 줄이 처음 나오면 그 CS 값을 대표값으로 삼는다
                # (초기값이 취소였을 수 있으므로 덮어쓴다)
                entry["cs_status"] = cs_status
                entry["_has_live"] = True

    # 내부 값을 정리하고 최종 quantity를 확정한다
    for entry in merged.values():
        if entry["_has_live"]:
            entry["quantity"] = entry["_live_qty"]
        else:
            # 전부 취소된 그룹 — 기록은 남기되 대시보드가 걸러낼 수 있게 취소 CS를 유지한다
            entry["quantity"] = entry["_cancelled_qty"]
        for k in ("_live_qty", "_cancelled_qty", "_has_live"):
            del entry[k]

    return merged


def process_file(filepath, engine, cache_conn, dong_cache):
    log.info(f"파일 처리 시작: {filepath}")
    try:
        df = read_wms_file(filepath)
    except Exception as e:
        log.error(f"파일 읽기 실패 ({filepath}): {e}")
        return

    log.info(f"총 {len(df):,}행 로드 완료 — diffing 시작")

    # 1단계: 파일 안의 중복 행을 (order_key, status) 단위로 병합.
    # 이 단계를 거치면 한 파일에서 같은 키가 두 번 나오는 일이 없어지므로,
    # 캐시가 자기 자신과 싸우며 무한 반복되는 문제가 원천 차단된다.
    merged = merge_duplicate_rows(df, dong_cache)

    # 2단계: 직전 상태와 비교해 실제로 바뀐 것만 추린다.
    cache_dict = load_cache_dict(cache_conn)   # 전체 캐시를 한 번만 메모리로 로드
    cache_updates = []
    changed_rows_dict = {}
    now_iso = datetime.now(KST).isoformat()

    for (order_key, status), entry in merged.items():
        prev = cache_dict.get((order_key, status))
        current = (entry["cs_status"], entry["is_hold"], entry["quantity"])

        # CS / 보류 / 수량 중 하나라도 바뀐 경우에만 반영 (동일하면 스킵)
        if prev == current:
            continue

        cache_updates.append(
            (order_key, status, entry["cs_status"], int(entry["is_hold"]), entry["quantity"], now_iso)
        )

        # 실시간 현황판이 참고하는 상태는 '송장' / '배송'이 핵심.
        # 그 외 상태(발주/접수)는 캐시만 갱신하고 DB에는 올리지 않는다.
        if status not in ("송장", "배송"):
            continue

        entry["detected_at"] = now_iso
        changed_rows_dict[(order_key, status)] = entry

    changed_rows = list(changed_rows_dict.values())

    bulk_save_cache(cache_conn, cache_updates)
    log.info(f"diffing 완료 — 캐시 변경 {len(cache_updates):,}건 / DB 반영 대상(송장·배송) {len(changed_rows):,}건")

    if not changed_rows:
        log.info("변경된 상태 없음 (신규 반영 대상 0건)")
        return

    unmapped = sorted({r["channel_name"] for r in changed_rows if r["dong"] is None})
    if unmapped:
        log.warning(f"매핑 안 된 판매처 발견: {unmapped} — Streamlit '판매처 매핑 관리'에서 추가해주세요.")

    push_to_db(engine, changed_rows)
    log.info(f"DB 반영 완료: {len(changed_rows):,}건")


def push_to_db(engine, rows, chunk_size=2000):
    """대량 행을 psycopg2의 execute_values로 upsert.
    이러면 청크(기본 2000행)당 네트워크 왕복이 '딱 1번'만 발생한다.
    2~3만 건 규모에서도 15개 안팎의 왕복으로 끝나 훨씬 빠르다.
    """
    if not rows:
        return

    columns = ["order_key", "invoice_no", "channel_name", "dong", "product_name",
               "quantity", "status", "cs_status", "is_hold",
               "invoice_datetime", "delivery_datetime", "detected_at", "extra_data"]
    sql = f"""
        INSERT INTO order_status_log ({', '.join(columns)})
        VALUES %s
        ON CONFLICT (order_key, status) DO UPDATE SET
            cs_status = EXCLUDED.cs_status,
            is_hold = EXCLUDED.is_hold,
            invoice_datetime = EXCLUDED.invoice_datetime,
            delivery_datetime = EXCLUDED.delivery_datetime,
            dong = EXCLUDED.dong,
            invoice_no = EXCLUDED.invoice_no,
            quantity = EXCLUDED.quantity,
            extra_data = EXCLUDED.extra_data,
            detected_at = EXCLUDED.detected_at
    """
    # invoice_datetime / delivery_datetime / detected_at / extra_data 캐스팅 명시
    template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)"

    total = len(rows)
    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        for i in range(0, total, chunk_size):
            chunk = rows[i:i + chunk_size]
            values = [tuple(r[c] for c in columns) for r in chunk]
            execute_values(cur, sql, values, template=template, page_size=chunk_size)
            raw_conn.commit()
            log.info(f"  ↳ DB 저장 진행: {min(i + chunk_size, total):,} / {total:,}건")
    finally:
        raw_conn.close()


# ══════════════════════════════════════════════════════════════
# SKU별 일별 출고 요약 (재고보충계획용 수요 데이터)
# ══════════════════════════════════════════════════════════════
# order_status_log는 용량 관리 정책상 2개월 뒤 원본이 지워진다. 그 전에
# 상품코드(옵션명)별 하루 출고량만 미리 요약해서 sku_daily_shipment에 남겨두면,
# 원본이 사라져도 수요 예측에 쓸 이력은 계속 쌓인다.
NOT_CANCELLED_SQL_WD = "cs_status NOT IN (" + ", ".join(f"'{v}'" for v in CANCELLED_CS_VALUES) + ")"

SKU_AGG_INTERVAL_SEC = int(os.getenv("UPH_SKU_AGG_INTERVAL_SEC", "600"))   # 10분마다
SKU_AGG_LOOKBACK_DAYS = 3   # 늦게 들어오는 배송확정 반영— 최근 며칠은 계속 다시 계산


def build_sku_daily_shipment(engine, date_from, date_to, chunk_size=2000):
    """[date_from, date_to] 구간(KST 날짜)을 상품코드별로 다시 집계해서 upsert.
    같은 구간을 몇 번 다시 돌려도 결과가 같다(멱등) — 그래서 최근 며칠을 매번
    재계산해도 안전하다.

    push_to_db와 같은 방식(execute_values 일괄 upsert)을 쓴다 — 이 함수는 watchdog
    메인 루프에서 10분마다 불리므로, 행 하나씩 왕복하면 그만큼 감시가 지연된다."""
    query = f"""
        SELECT (delivery_datetime AT TIME ZONE 'Asia/Seoul')::date AS work_date,
               COALESCE(NULLIF(extra_data->>'옵션명', ''), 'UNKNOWN') AS product_code,
               MAX(product_name) AS product_name,
               SUM(quantity) AS shipped_qty,
               COUNT(DISTINCT invoice_no) AS order_count
        FROM order_status_log
        WHERE status='배송' AND {NOT_CANCELLED_SQL_WD}
          AND delivery_datetime IS NOT NULL
          AND (delivery_datetime AT TIME ZONE 'Asia/Seoul')::date BETWEEN :d1 AND :d2
        GROUP BY 1, 2
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query), {"d1": date_from, "d2": date_to}).fetchall()
    if not rows:
        return 0

    sql = """
        INSERT INTO sku_daily_shipment
            (work_date, product_code, product_name, shipped_qty, order_count, updated_at)
        VALUES %s
        ON CONFLICT (work_date, product_code) DO UPDATE SET
            product_name = EXCLUDED.product_name,
            shipped_qty  = EXCLUDED.shipped_qty,
            order_count  = EXCLUDED.order_count,
            updated_at   = now()
    """
    template = "(%s, %s, %s, %s, %s, now())"
    values = [(r.work_date, r.product_code, r.product_name or "",
               int(r.shipped_qty or 0), int(r.order_count or 0)) for r in rows]

    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        for i in range(0, len(values), chunk_size):
            execute_values(cur, sql, values[i:i + chunk_size], template=template, page_size=chunk_size)
        raw_conn.commit()
    finally:
        raw_conn.close()
    return len(rows)


def cleanup_old_downloads(folder, keep_n=KEEP_LATEST_FILES):
    """감시폴더에 WMS 다운로드 파일이 계속 쌓이는 것을 방지 — 수정시각(mtime) 기준
    최신 keep_n개만 남기고 나머지는 삭제한다. 이미 처리(diffing)까지 끝난 파일들이라
    지워도 데이터 유실은 없음 (반영 결과는 이미 Supabase에 저장돼 있음)."""
    try:
        files = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith((".xls", ".xlsx", ".csv")) and os.path.isfile(os.path.join(folder, f))
        ]
        if len(files) <= keep_n:
            return
        files.sort(key=os.path.getmtime, reverse=True)  # 최신 파일이 앞으로 오게 정렬
        for old_file in files[keep_n:]:
            try:
                os.remove(old_file)
                log.info(f"오래된 다운로드 파일 정리: {os.path.basename(old_file)}")
            except Exception as e:
                log.warning(f"파일 삭제 실패({os.path.basename(old_file)}): {e}")
    except Exception as e:
        log.warning(f"다운로드 폴더 정리 중 오류: {e}")


# ══════════════════════════════════════════════════════════════
# 폴더 감시 (직접 폴링)
# ══════════════════════════════════════════════════════════════
def find_latest_wms_file(folder):
    """감시 폴더에서 가장 최근에 받은 WMS 파일 경로를 반환. 없으면 None."""
    try:
        files = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith((".xls", ".xlsx", ".csv"))
            and os.path.isfile(os.path.join(folder, f))
        ]
    except OSError as e:
        log.warning(f"감시 폴더 조회 실패: {e}")
        return None
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def is_file_settled(filepath):
    """다운로드가 끝나 파일이 안정됐는지 확인 (쓰는 중인 파일을 읽지 않기 위함).
    마지막 수정 시각이 FILE_STABLE_WAIT_SEC 이상 지났으면 다 받은 것으로 본다."""
    try:
        return (time.time() - os.path.getmtime(filepath)) >= FILE_STABLE_WAIT_SEC
    except OSError:
        return False


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════
def main():
    # 감시 폴더는 없으면 만든다.
    # 예전에는 없으면 그냥 종료했는데, 통합 exe를 새 PC에 설치하면 이 폴더가 당연히
    # 없어서 UPH 제어판에서 시작을 눌러도 즉시 죽어버렸다. 폴더를 만들지 못하는
    # 경우(권한 없음 등)에만 실패로 처리한다.
    if not os.path.isdir(WATCH_FOLDER):
        try:
            os.makedirs(WATCH_FOLDER, exist_ok=True)
            log.info(f"감시 폴더를 새로 만들었습니다: {WATCH_FOLDER}")
        except OSError as e:
            log.error(
                f"감시 폴더를 만들 수 없습니다: {WATCH_FOLDER}  ({e})\n"
                f"  → 다른 위치를 쓰려면 환경변수 UPH_WATCH_FOLDER를 지정하세요."
            )
            sys.exit(1)

    engine = get_engine()
    cache_conn = init_cache_db()
    dong_cache = DongMappingCache(engine)

    log.info(f"UPH watchdog 에이전트 시작 (v3) — 감시 폴더: {WATCH_FOLDER}")

    # v3 (2026-08-06): watchdog 라이브러리의 파일 이벤트 감시를 걷어내고 직접 폴링으로 전환.
    # 이벤트 방식은 실제 감시를 담당하는 emitter 스레드가 조용히 죽어도 Observer 객체는
    # is_alive()=True를 계속 반환해서, "프로세스는 멀쩡한데 몇 시간째 새 파일을 하나도 처리
    # 안 하는" 상태를 자동으로 알아챌 수 없었다 (2026-08-06, 1~2시간씩 통째로 건너뛴 구간이
    # 반복되던 걸 로그로 확인). 다운로드 파일은 매번 전체 스냅샷(1.7만 행 전량)이라 최신 파일
    # 하나만 처리하면 충분하므로, 그냥 주기적으로 폴더를 훑어 가장 최신 파일을 처리한다.
    # 이러면 감시가 멈추는 실패 모드 자체가 없고, 밀렸을 때도 중간 파일을 건너뛰고 최신 것으로
    # 바로 따라잡는다.
    last_processed = None
    last_sku_agg = 0.0
    try:
        while True:
            try:
                latest = find_latest_wms_file(WATCH_FOLDER)
                if latest and latest != last_processed and is_file_settled(latest):
                    process_file(latest, engine, cache_conn, dong_cache)
                    cleanup_old_downloads(WATCH_FOLDER)
                    last_processed = latest
            except Exception:
                log.exception("파일 처리 중 예외 발생 (감시는 계속 유지됨)")

            # SKU별 일별 출고 요약 — 재고보충계획용 수요 데이터가 계속 쌓이도록 주기적으로 재계산
            if time.time() - last_sku_agg >= SKU_AGG_INTERVAL_SEC:
                try:
                    today_kst = datetime.now(KST).date()
                    d_from = today_kst - timedelta(days=SKU_AGG_LOOKBACK_DAYS)
                    n = build_sku_daily_shipment(engine, d_from, today_kst)
                    log.info(f"SKU별 일별 출고 요약 갱신: {d_from} ~ {today_kst} ({n}건)")
                except Exception:
                    log.exception("SKU별 일별 출고 요약 갱신 실패 (감시는 계속 유지됨)")
                last_sku_agg = time.time()

            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        log.info("에이전트 종료 요청 받음")
    cache_conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("치명적 오류로 에이전트가 종료됨")
        sys.exit(1)