"""
ENCLU UPH 실시간 현황판 — 로컬 watchdog 에이전트 (v2)

v2 변경점 (기존 대비):
  - detected_at(watchdog이 파일을 감지한 시각) 의존을 제거하고,
    WMS가 실제로 내려주는 업무 일시(송장일_날짜/시간, 배송일_날짜/시간)를 정식 컬럼으로 저장.
  - '배송 보류' 헤더를 그대로 반영해 is_hold 컬럼으로 저장 (기존엔 CS 드롭다운값 중 '보류'를 썼음).
  - 이 3개 값이 바뀔 수 있으므로(특히 보류 해제) 캐시 비교 키에 is_hold 포함.

역할:
  1. 지정된 감시 폴더(WMS 배송파일 다운로드 폴더)를 상시 감시
  2. 새 파일이 생기면 읽어서, 각 행(주문 상품 줄)의 상태를 이전 상태와 비교
  3. 상태(발주/접수/송장/배송) 또는 CS/보류가 바뀐 행만 Supabase로 push
  4. 판매처 → 동(A/B/F) 매핑은 sales_channel_dong_mapping 테이블을 주기적으로 조회해 반영

실행 방식:
  - 개발/테스트: `python watchdog_agent.py`
  - 실제 배포: pythonw.exe로 콘솔창 없이 백그라운드 실행 (ENCLU SCM ALL SYSTEM 런처와 동일 패턴)

필요 패키지: watchdog, pandas, xlrd, openpyxl, sqlalchemy, psycopg2-binary, python-dotenv, beautifulsoup4, lxml

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
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

# ══════════════════════════════════════════════════════════════
# 설정 (.env에서 읽음)
# ══════════════════════════════════════════════════════════════
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")                     # 기존 Streamlit 앱과 동일한 Supabase 접속정보 재사용
WATCH_FOLDER = os.getenv("UPH_WATCH_FOLDER", r"C:\ENCLU\WMS_다운로드")   # WMS 파일이 떨어지는 폴더
CACHE_DB_PATH = os.getenv("UPH_CACHE_DB", "uph_agent_cache.sqlite3")     # 로컬 "직전 상태" 캐시
POLL_INTERVAL_SEC = int(os.getenv("UPH_POLL_INTERVAL_SEC", "10"))       # 폴더 감시 주기(초)
MAPPING_REFRESH_SEC = int(os.getenv("UPH_MAPPING_REFRESH_SEC", "300"))  # 판매처→동 매핑 갱신 주기(초)
FILE_STABLE_WAIT_SEC = 2   # 파일이 완전히 저장될 때까지 대기 (다운로드 도중 읽기 방지)
KEEP_LATEST_FILES = int(os.getenv("UPH_KEEP_LATEST_FILES", "5"))  # 감시폴더에 최신 몇 개 파일만 남기고 정리할지

KST = timezone(timedelta(hours=9))

LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uph_agent.log")

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_cache (
            order_key TEXT PRIMARY KEY,
            status TEXT,
            cs_status TEXT,
            is_hold INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    # 기존(v1) 캐시 파일에는 is_hold 컬럼이 없을 수 있으므로 안전하게 추가 시도
    try:
        conn.execute("ALTER TABLE order_cache ADD COLUMN is_hold INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 존재하면 무시
    conn.commit()
    return conn


def load_cache_dict(conn):
    """order_cache 테이블 전체를 한 번에 메모리로 읽어온다 (행마다 SQLite 왕복하는 것 방지)."""
    cur = conn.execute("SELECT order_key, status, cs_status, is_hold FROM order_cache")
    return {row[0]: (row[1], row[2], bool(row[3])) for row in cur.fetchall()}


def bulk_save_cache(conn, updates):
    """변경된 캐시 항목들을 한 번에 upsert. updates: [(order_key, status, cs_status, is_hold, updated_at), ...]"""
    if not updates:
        return
    conn.executemany("""
        INSERT INTO order_cache (order_key, status, cs_status, is_hold, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(order_key) DO UPDATE SET status=excluded.status,
            cs_status=excluded.cs_status, is_hold=excluded.is_hold, updated_at=excluded.updated_at
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


def process_file(filepath, engine, cache_conn, dong_cache):
    log.info(f"파일 처리 시작: {filepath}")
    try:
        df = read_wms_file(filepath)
    except Exception as e:
        log.error(f"파일 읽기 실패 ({filepath}): {e}")
        return

    log.info(f"총 {len(df):,}행 로드 완료 — diffing 시작")

    cache_dict = load_cache_dict(cache_conn)   # 전체 캐시를 한 번만 메모리로 로드
    cache_updates = []
    changed_rows_dict = {}  # key: (order_key, status) -> row dict. 같은 파일 안에서 같은 (order_key,status)
                             # 조합이 여러 번 걸리더라도 나중 값으로 덮어써서, push_to_db의 UPSERT 배치에
                             # 동일 충돌키가 두 번 들어가는 걸 원천 차단한다 (안 그러면 PostgreSQL이
                             # "ON CONFLICT DO UPDATE command cannot affect row a second time" 로 거부함).
    now_iso = datetime.now(KST).isoformat()

    for _, row in df.iterrows():
        mgmt_no = str(row[COL_MGMT_NO]).strip()
        # WMS가 같은 상품의 상품코드를 어떤 날은 '3727', 어떤 날은 '03727'처럼 앞자리 0
        # 유무를 다르게 내려주는 경우가 있어, 이를 그대로 키에 쓰면 같은 상품이 서로 다른
        # order_key로 갈라져 상태 추적이 끊기는 버그가 있었음 (2026-08-05, 대시보드 잔여
        # 과다집계로 발견). 앞자리 0을 제거해 정규화한 값을 키로 사용해 이 둘을 항상
        # 같은 order_key로 합친다.
        product_code_raw = str(row[COL_PRODUCT_CODE]).strip()
        product_code = product_code_raw.lstrip("0") or "0"
        order_key = f"{mgmt_no}_{product_code}"

        status = str(row[COL_STATUS]).strip()
        cs_status = str(row[COL_CS]).strip() if pd.notna(row[COL_CS]) else "정상"
        is_hold = str(row[COL_HOLD]).strip() == "보류" if pd.notna(row[COL_HOLD]) else False

        prev_status, prev_cs, prev_hold = cache_dict.get(order_key, (None, None, False))

        # 상태 / CS / 보류여부 중 하나라도 바뀐 경우에만 반영 (완전히 동일하면 스킵 — 중복 방지)
        # v1에서는 status·cs만 비교해서 보류 해제처럼 같은 상태 안에서 바뀌는 변화를 놓쳤음 → is_hold 추가
        if status == prev_status and cs_status == prev_cs and is_hold == prev_hold:
            continue

        # 메모리 캐시도 즉시 갱신 (같은 파일 안에 order_key 중복 행이 있어도 정확히 비교되도록)
        cache_dict[order_key] = (status, cs_status, is_hold)
        cache_updates.append((order_key, status, cs_status, int(is_hold), now_iso))

        # 실시간 현황판이 참고하는 상태는 '송장' / '배송'이 핵심.
        # 그 외 상태(발주/접수)는 캐시만 갱신하고 DB에는 올리지 않음 (필요해지면 조건 완화 가능)
        if status not in ("송장", "배송"):
            continue

        channel_name = str(row[COL_CHANNEL]).strip()
        dong = dong_cache.get(channel_name)

        extra_data = {}
        for col in EXTRA_COLS:
            if col in df.columns:
                val = row[col]
                extra_data[col] = None if pd.isna(val) else str(val)

        # 같은 (order_key, status)가 이미 이번 파일에서 잡혔으면 나중 값(=이 행)으로 덮어씀
        changed_rows_dict[(order_key, status)] = {
            "order_key": order_key,
            "invoice_no": str(row[COL_INVOICE]).strip(),
            "channel_name": channel_name,
            "dong": dong,
            "product_name": str(row[COL_PRODUCT_NAME]).strip(),
            "quantity": int(row[COL_QTY]) if pd.notna(row[COL_QTY]) else 1,
            "status": status,
            "cs_status": cs_status,
            "is_hold": is_hold,
            "invoice_datetime": parse_kst_datetime(row.get(COL_INVOICE_DATE), row.get(COL_INVOICE_TIME)),
            "delivery_datetime": parse_kst_datetime(row.get(COL_DELIVERY_DATE), row.get(COL_DELIVERY_TIME)),
            "detected_at": now_iso,
            "extra_data": json.dumps(extra_data, ensure_ascii=False),
        }

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
            extra_data = EXCLUDED.extra_data
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
# 폴더 감시 핸들러
# ══════════════════════════════════════════════════════════════
class WmsFileHandler(FileSystemEventHandler):
    def __init__(self, engine, cache_conn, dong_cache):
        self.engine = engine
        self.cache_conn = cache_conn
        self.dong_cache = dong_cache
        self.processed_recently = {}  # 파일별 마지막 처리시각 (짧은 시간 내 중복 이벤트 방지)

    def _handle(self, filepath):
        if not filepath.lower().endswith((".xls", ".xlsx", ".csv")):
            return
        if not os.path.isfile(filepath):
            return

        last = self.processed_recently.get(filepath, 0)
        if time.time() - last < 5:
            return  # 5초 내 중복 이벤트 무시

        # 파일이 완전히 써질 때까지 잠깐 대기 (다운로드 도중 파일 오픈 방지)
        time.sleep(FILE_STABLE_WAIT_SEC)

        self.processed_recently[filepath] = time.time()
        process_file(filepath, self.engine, self.cache_conn, self.dong_cache)
        cleanup_old_downloads(WATCH_FOLDER)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════
def main():
    if not os.path.isdir(WATCH_FOLDER):
        log.error(f"감시 폴더가 존재하지 않습니다: {WATCH_FOLDER}  (.env의 UPH_WATCH_FOLDER 확인)")
        sys.exit(1)

    engine = get_engine()
    cache_conn = init_cache_db()
    dong_cache = DongMappingCache(engine)

    log.info(f"UPH watchdog 에이전트 시작 (v2) — 감시 폴더: {WATCH_FOLDER}")

    # 시작 시 폴더에 이미 있는 최신 파일 1개는 초기 스캔 (에이전트 재시작 대비)
    existing_files = [
        os.path.join(WATCH_FOLDER, f) for f in os.listdir(WATCH_FOLDER)
        if f.lower().endswith((".xls", ".xlsx", ".csv"))
    ]
    if existing_files:
        latest = max(existing_files, key=os.path.getmtime)
        log.info(f"초기 스캔 대상 파일: {latest}")
        process_file(latest, engine, cache_conn, dong_cache)
        cleanup_old_downloads(WATCH_FOLDER)

    handler = WmsFileHandler(engine, cache_conn, dong_cache)
    observer = Observer()
    observer.schedule(handler, WATCH_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        observer.stop()
        log.info("에이전트 종료 요청 받음")
    observer.join()
    cache_conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("치명적 오류로 에이전트가 종료됨")
        sys.exit(1)