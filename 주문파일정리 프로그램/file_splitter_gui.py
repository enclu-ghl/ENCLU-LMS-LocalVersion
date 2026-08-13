"""
ENCLU 파일 찢기 프로그램 (Tkinter GUI)

WMS/플랫폼 다운로드 파일을 받아서 "정리 → 합포/일괄/싱글/단품 분류" 후
지정 폴더에 쪼개서 저장하는 프로그램.

화면 구성: 팝업창(Toplevel) 대신 상단 탭 4개로 전환
  📋 주문 정리 / 🏷️ 브랜드 관리 / 📦 일괄 관리 / 🔗 아마존 URL 관리

개발 진행 순서 (전부 완료):
  1단계: 큐텐 "파일 정리" 기능
  2단계: 공통 분류 로직(합포→일괄→싱글→단품, 모드1~6 전부) + 브랜드/일괄코드 관리
  3단계: 아마존 정리 로직(요미가나 변환 + URL 매칭) — 모드1(정리)만 지원, 모드2~6은 합포/일괄/싱글 판단
         기준 컬럼(장바구니번호 등)이 큐텐과 달라서 아직 미지원 (시도하면 명확한 에러로 안내됨)
  4단계: 라쿠텐 정리 로직(WMS 다운로드 파일 + 원본 파일 결합) — 마찬가지로 모드1(정리)만 지원

브랜드/일괄코드/일괄소진로그/아마존URL — 팀원 누구 PC에서 켜든 항상 같은 내용이 보여야 해서
UPH 시스템과 같은 Supabase DB에 저장 (실시간에 가깝게: 탭 열려있는 동안 5초마다 자동 재조회).
"기본 저장 폴더"만큼은 PC마다 다를 수 있는 설정이라 로컬 settings.json 그대로 유지.

필요 패키지: pandas, openpyxl, xlrd, xlsxwriter, sqlalchemy, psycopg2-binary, python-dotenv, pykakasi, beautifulsoup4, lxml

※ 저장은 xlsxwriter 엔진 사용 (openpyxl 기본 저장은 inline string 방식이라 일부 외부 시스템
  Excel 업로드 파서가 "파일 분석 실패"로 거부하는 문제가 있어 xlsxwriter로 전환함, 2026-07-29)
.env 파일에 DATABASE_URL=(UPH 시스템과 동일한 Supabase 접속정보) 필요.
먼저 migration_file_splitter.sql, migration_file_splitter_v2_revert.sql을 Supabase에 실행해야 함.
"""

import os
import sys
import json
import time
import re
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, bindparam

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _settings_dir() -> str:
    """settings.json을 둘 폴더.

    통합 exe 안에서는 __file__이 실행할 때마다 지워지는 번들 임시 폴더라,
    거기에 저장하면 프로그램을 껐다 켤 때마다 "기본 저장 폴더" 설정이 사라진다.
    그래서 exe로 돌 때는 프로그램 폴더(exe 옆)에 남긴다.
    """
    try:
        from hub import paths
        if paths.IS_FROZEN:
            return paths.APP_DIR
    except ImportError:
        pass
    return BASE_DIR


SETTINGS_FILE = os.path.join(_settings_dir(), "settings.json")  # "기본 저장 폴더"만 PC별 로컬로 유지

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
_engine = None


def get_engine():
    """UPH 시스템과 동일한 Supabase 접속정보를 재사용 (.env의 DATABASE_URL)."""
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL이 .env에 설정되어 있지 않습니다. "
                "UPH 시스템 폴더의 .env를 참고해서 같은 값을 넣어주세요."
            )
        _engine = create_engine(DATABASE_URL)
    return _engine


POLL_INTERVAL_MS = 5000  # 관리 탭들이 몇 ms마다 DB를 다시 조회할지 (실시간에 가깝게)

PLATFORMS = ["큐텐", "아마존", "라쿠텐", "스타일셀러"]
# 1단계에서는 큐텐만 실제 동작. 나머지는 선택은 가능하지만 실행 시 "준비중" 안내.
IMPLEMENTED_PLATFORMS = {"큐텐", "아마존", "라쿠텐", "스타일셀러"}

MODES = [
    "1. 파일 정리 (기본 정보만 정리 후 저장)",
    "2. 파일 정리 + 합포 + 단품",
    "3. 파일 정리 + 합포 + 일괄 + 단품",
    "4. 파일 정리 + 합포 + 일괄 + 싱글 + 단품",
    "5. 파일 정리 + 합포 + 싱글 + 단품",
    "6. 파일 정리 + 합포 + 싱글(사은품 동일) + 단품",
]
# 2단계 완료: 모드 1~6 전부 동작.
IMPLEMENTED_MODES = set(MODES)
MODES_NEED_BATCH = {MODES[2], MODES[3]}       # 일괄 단계가 있는 모드 (3,4)
MODES_NEED_SINGLE_THRESHOLD = {MODES[3], MODES[4], MODES[5]}  # 싱글 기준값이 필요한 모드 (4,5,6)

# 플랫폼별로 실제 지원하는 자르는 방식. 아마존/라쿠텐은 합포/일괄/싱글 판단 기준 컬럼(장바구니번호 등)이
# 큐텐과 달라서 아직 모드1(정리)만 지원 — 드롭다운에도 그 모드만 보이게 필터링한다.
# 스타일셀러(자체 플랫폼)는 애초에 합포/일괄/싱글/단품 분류 자체가 필요 없고 요미가나 변환만 하면 되므로
# 항상 모드1(정리)만 지원.
PLATFORM_SUPPORTED_MODES = {
    "큐텐": MODES,
    "아마존": [MODES[0]],
    "라쿠텐": [MODES[0]],
    "스타일셀러": [MODES[0]],
}


# ══════════════════════════════════════════════════════════════
# 로컬 설정 (기본 저장 폴더만 — PC마다 다를 수 있어서 DB로 안 옮김)
# ══════════════════════════════════════════════════════════════
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
# 브랜드 목록 (fs_brands)
# ══════════════════════════════════════════════════════════════
def load_brands():
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT name FROM fs_brands ORDER BY name")).fetchall()
    return [r.name for r in rows]


def add_brand(name):
    """추가 성공하면 True, 이미 있어서 중복이면 False."""
    with get_engine().begin() as conn:
        result = conn.execute(
            text("INSERT INTO fs_brands (name) VALUES (:n) ON CONFLICT (name) DO NOTHING RETURNING name"),
            {"n": name}
        ).fetchone()
    return result is not None


def delete_brand(name):
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM fs_brands WHERE name=:n"), {"n": name})


# ══════════════════════════════════════════════════════════════
# 일괄코드 목록 (fs_batch_codes)
# ══════════════════════════════════════════════════════════════
def load_batch_codes():
    """일괄코드 목록: [{"code","remaining_qty","product_name","gift"}, ...] (남은수량 0 이하는 제외)"""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT code, remaining_qty, product_name, gift FROM fs_batch_codes "
            "WHERE remaining_qty > 0 ORDER BY code"
        )).fetchall()
    return [{"code": r.code, "remaining_qty": r.remaining_qty,
              "product_name": r.product_name or "", "gift": r.gift or ""} for r in rows]


def add_batch_code(code, qty, product_name, gift):
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO fs_batch_codes (code, remaining_qty, product_name, gift)
            VALUES (:code, :qty, :pn, :gift)
        """), {"code": code, "qty": qty, "pn": product_name, "gift": gift})


def update_batch_code(old_code, new_code, qty, product_name, gift):
    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE fs_batch_codes SET code=:new_code, remaining_qty=:qty,
                   product_name=:pn, gift=:gift, updated_at=NOW()
            WHERE code=:old_code
        """), {"new_code": new_code, "qty": qty, "pn": product_name, "gift": gift, "old_code": old_code})


def delete_batch_code(code):
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM fs_batch_codes WHERE code=:c"), {"c": code})


def delete_all_batch_codes():
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM fs_batch_codes"))


def check_existing_batch_codes(codes):
    """엑셀 업로드 전 미리보기용 — 이미 DB에 있는 코드만 골라서 반환 (경고 팝업에 쓰임)."""
    if not codes:
        return set()
    stmt = text("SELECT code FROM fs_batch_codes WHERE code IN :codes").bindparams(
        bindparam("codes", expanding=True)
    )
    with get_engine().connect() as conn:
        rows = conn.execute(stmt, {"codes": list(codes)}).fetchall()
    return {r.code for r in rows}


def bulk_upsert_batch_codes(rows):
    """엑셀 대량 등록용. rows: [{"code","qty","product_name","gift"}, ...]
    이미 있는 코드면 수량을 더해주고(보충), 상품명/사은품은 새 값이 있으면 그걸로 갱신.
    반환: (성공 건수, 오류 목록[(행번호,사유)])
    """
    ok_count = 0
    with get_engine().begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO fs_batch_codes (code, remaining_qty, product_name, gift)
                VALUES (:code, :qty, :pn, :gift)
                ON CONFLICT (code) DO UPDATE SET
                    remaining_qty = fs_batch_codes.remaining_qty + EXCLUDED.remaining_qty,
                    product_name = CASE WHEN EXCLUDED.product_name <> '' THEN EXCLUDED.product_name ELSE fs_batch_codes.product_name END,
                    gift = CASE WHEN EXCLUDED.gift <> '' THEN EXCLUDED.gift ELSE fs_batch_codes.gift END,
                    updated_at = NOW()
            """), {"code": r["code"], "qty": r["qty"], "pn": r.get("product_name", ""), "gift": r.get("gift", "")})
            ok_count += 1
    return ok_count


def consume_batch_codes_atomic(needed_counts):
    """일괄코드를 실제로 소진(차감)하는 유일한 통로.
    코드별로 'SELECT ... FOR UPDATE'로 행을 잠그고 나서 차감하기 때문에,
    여러 사람이 동시에 처리하더라도 같은 코드를 이중으로 뜯어가는 일이 없다
    (한쪽 트랜잭션이 끝날 때까지 다른 쪽은 그 행 앞에서 대기).

    needed_counts: {code: 이번 파일에서 이 코드로 필요한 건수}
    반환: {code: 실제로 내준 수량} (등록 안 된 코드나 남은수량 0인 코드는 0)
    """
    if not needed_counts:
        return {}
    taken = {}
    with get_engine().begin() as conn:
        for code, needed in needed_counts.items():
            row = conn.execute(
                text("SELECT remaining_qty FROM fs_batch_codes WHERE code=:c FOR UPDATE"),
                {"c": code}
            ).fetchone()
            if not row:
                taken[code] = 0
                continue
            avail = row.remaining_qty
            take = min(needed, avail)
            taken[code] = take
            if take > 0:
                conn.execute(
                    text("UPDATE fs_batch_codes SET remaining_qty = remaining_qty - :t, updated_at=NOW() WHERE code=:c"),
                    {"t": take, "c": code}
                )
    return taken


# ══════════════════════════════════════════════════════════════
# 일괄 소진 로그 (fs_batch_usage_log)
# ══════════════════════════════════════════════════════════════
def load_batch_usage_log(limit=100):
    query = "SELECT id, occurred_at, brand, code, used_qty, reverted FROM fs_batch_usage_log ORDER BY occurred_at DESC"
    params = {}
    if limit is not None:
        query += " LIMIT :n"
        params["n"] = limit
    with get_engine().connect() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [{"id": r.id, "date": r.occurred_at.strftime("%Y-%m-%d %H:%M:%S"), "brand": r.brand,
              "code": r.code, "used_qty": r.used_qty, "reverted": r.reverted} for r in rows]


def append_batch_usage_log(entries):
    """반환: 방금 남긴 로그의 id 목록.
    저장이 실패했을 때 이 id들로 revert_batch_usage를 불러 차감을 되돌린다."""
    if not entries:
        return []
    ids = []
    with get_engine().begin() as conn:
        for e in entries:
            row = conn.execute(text("""
                INSERT INTO fs_batch_usage_log (brand, code, used_qty)
                VALUES (:brand, :code, :qty)
                RETURNING id
            """), {"brand": e["brand"], "code": e["code"], "qty": e["used_qty"]}).fetchone()
            if row:
                ids.append(row.id)
    return ids


def revert_batch_usage(log_id):
    """소진 로그 한 건을 되돌린다 — 그 수량만큼 remaining_qty에 다시 더해주고 로그를 '되돌림'으로 표시.
    행 잠금으로 처리해서 같은 로그를 실수로 두 번 되돌리는 것도 막는다.
    코드 자체가 그새 삭제됐어도(휴지통 버튼 등) upsert라서 다시 그 수량으로 살아난다.
    반환: (성공 여부, 메시지)
    """
    with get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT id, code, used_qty, reverted FROM fs_batch_usage_log WHERE id=:id FOR UPDATE"),
            {"id": log_id}
        ).fetchone()
        if not row:
            return False, "로그를 찾을 수 없습니다."
        if row.reverted:
            return False, "이미 되돌린 로그입니다."

        conn.execute(text("""
            INSERT INTO fs_batch_codes (code, remaining_qty)
            VALUES (:code, :qty)
            ON CONFLICT (code) DO UPDATE SET
                remaining_qty = fs_batch_codes.remaining_qty + EXCLUDED.remaining_qty,
                updated_at = NOW()
        """), {"code": row.code, "qty": row.used_qty})

        conn.execute(
            text("UPDATE fs_batch_usage_log SET reverted = TRUE WHERE id=:id"),
            {"id": log_id}
        )
    return True, f"'{row.code}' {row.used_qty}개를 되돌렸습니다."


# ══════════════════════════════════════════════════════════════
# 아마존 URL 목록 (fs_amazon_url_map)
# ══════════════════════════════════════════════════════════════
def load_amazon_url_map():
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT hscode, asin, url FROM fs_amazon_url_map ORDER BY hscode")).fetchall()
    return [{"hscode": r.hscode, "asin": r.asin or "", "url": r.url or ""} for r in rows]


def add_amazon_url(hscode, asin, url):
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO fs_amazon_url_map (hscode, asin, url) VALUES (:h, :a, :u)
        """), {"h": hscode, "a": asin, "u": url})


def update_amazon_url(old_hscode, new_hscode, asin, url):
    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE fs_amazon_url_map SET hscode=:new_h, asin=:a, url=:u, updated_at=NOW()
            WHERE hscode=:old_h
        """), {"new_h": new_hscode, "a": asin, "u": url, "old_h": old_hscode})


def delete_amazon_url(hscode):
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM fs_amazon_url_map WHERE hscode=:h"), {"h": hscode})


def delete_all_amazon_urls():
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM fs_amazon_url_map"))


def bulk_upsert_amazon_urls(rows):
    """엑셀 대량 등록용. rows: [{"hscode","asin","url"}, ...]
    이미 있는 HSCODE면 최신 값으로 덮어씀.
    """
    ok_count = 0
    with get_engine().begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO fs_amazon_url_map (hscode, asin, url)
                VALUES (:h, :a, :u)
                ON CONFLICT (hscode) DO UPDATE SET
                    asin = EXCLUDED.asin, url = EXCLUDED.url, updated_at = NOW()
            """), {"h": r["hscode"], "a": r.get("asin", ""), "u": r.get("url", "")})
            ok_count += 1
    return ok_count


# ══════════════════════════════════════════════════════════════
# 파일 읽기 공통 헬퍼 (HTML로 위장된 xls / 진짜 바이너리 xls / xlsx 전부 대응)
# ══════════════════════════════════════════════════════════════
def _normalize_cell_text(text):
    """셀 텍스트의 양쪽 끝 공백(특수공백 \\xa0/\\u3000 포함)만 제거한다.
    내부(글자 사이) 공백은 건드리지 않음 — 일본어 이름/주소에서 전각공백(\\u3000)은
    성과 이름을 구분하는 정식 표기법으로 실제로 쓰이는 문자라(예: '久木田　貴'),
    이걸 일반 공백으로 뭉개면 오히려 사람이 엑셀에서 직접 처리한 결과와 달라짐
    (실측 비교로 확인됨). 그래서 '빈칸 셀이 &nbsp; 같은 padding으로만 채워진' 경우만
    걸러내는 목적의 양끝 strip만 적용한다."""
    return text.strip()


def _parse_html_table_raw(html_content):
    """pd.read_html 대신 BeautifulSoup으로 직접 파싱해서, 판다스가 내부적으로 하던
    콤마를 천단위 구분자로 착각해서 지우는 문제를 원천적으로 피한다.
    공백은 _normalize_cell_text()로 양끝만 정리 (내부 공백/특수공백은 원본 그대로 보존 —
    일본어 성명의 전각공백 구분자 등 의미있는 문자를 지키기 위함).
    수치처럼 보이는 컬럼의 자동 dtype 변환은 여기서 하지 않는다 — 필요한 곳(예: 수량)에서
    각 정리 함수가 개별적으로 pd.to_numeric 처리한다.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, "lxml")
    table = soup.find("table")
    if table is None:
        raise ValueError("HTML 안에서 표(<table>)를 찾지 못했습니다.")
    rows = table.find_all("tr")
    if not rows:
        raise ValueError("표에 행이 없습니다.")

    header = [_normalize_cell_text(c.get_text()) for c in rows[0].find_all(["th", "td"])]
    if not header:
        raise ValueError("표의 헤더 행을 읽지 못했습니다.")

    data = []
    for tr in rows[1:]:
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        values = [_normalize_cell_text(c.get_text()) for c in cells]
        if len(values) < len(header):
            values += [""] * (len(header) - len(values))
        data.append(values[:len(header)])

    return pd.DataFrame(data, columns=header)


def read_wms_excel(filepath):
    """
    ⚠ 전부 dtype=str로 강제해서 읽는다. 그렇지 않으면 pandas가 전화번호(090..., 03...)나
    우편번호처럼 숫자처럼 보이는 텍스트 컬럼을 자동으로 숫자로 인식해서 맨 앞자리 0을
    통째로 날려버리는 문제가 있었다 (2026-07-29 발견 — 라쿠텐 원본파일 送付先電話番号1~3 등에서 실제 발생).
    WMS 다운로드 파일(HTML 위장 .xls)은 BeautifulSoup으로 파싱해서 원래도 전부 문자열이라 안전하지만,
    진짜 바이너리 .xlsx/.xls나 .csv(예: 라쿠텐 원본파일)는 dtype을 명시하지 않으면 안전하지 않다.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".xls":
        with open(filepath, "rb") as f:
            head = f.read(512).lstrip()
        if head.startswith(b"<"):
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                html = f.read()
            df = _parse_html_table_raw(html)
            if df is None or df.empty:
                raise ValueError("HTML 형식 파일에서 표를 찾지 못했습니다.")
            return df
        else:
            return pd.read_excel(filepath, engine="xlrd", dtype=str)
    elif ext == ".xlsx":
        return pd.read_excel(filepath, engine="openpyxl", dtype=str)
    elif ext == ".csv":
        # 라쿠텐 RMS가 내려주는 원본 CSV는 Shift_JIS(cp932)가 표준이다.
        # 예전에는 utf-8-sig -> cp949(한국어) 두 개뿐이라, cp932 파일을 만나면
        # 디코드 에러로 죽거나 운 나쁘면 깨진 글자로 읽혀 헤더가 망가졌다
        # (그러면 "원본 파일 필수 컬럼 누락"으로 실패한다). 일본어 인코딩을 먼저 본다.
        last_err = None
        for enc in ("utf-8-sig", "cp932", "shift_jis", "euc-jp", "cp949"):
            try:
                return pd.read_csv(filepath, encoding=enc, dtype=str)
            except UnicodeDecodeError as e:
                last_err = e
                continue
        raise ValueError(
            f"CSV 인코딩을 판별하지 못했습니다: {os.path.basename(filepath)}\n"
            f"(utf-8 / cp932 / shift_jis / euc-jp / cp949 모두 실패)\n{last_err}"
        )
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")


# ══════════════════════════════════════════════════════════════
# 큐텐 — 파일 정리 로직
#
# 1. P열(옵션정보) 전체 빈값으로
# 2. Q열(판매자옵션코드) 빈값이면 같은 행 E열(상품코드) 값을 복사
#    (그래도 빈값이면 — 상품코드도 없는 경우 — 에러 로그에 남기고 건너뜀)
# 3. Q열 전체에서 '+' -> ',' 치환만 진행 (2026-07-29 변경: '_' -> ',' 치환은 제거)
#    사유: 바노바기 브랜드가 '_'를 포함한 옵션코드를 정상적으로 사용하고 있어서,
#    '_'를 무조건 구분자로 치환하면 그 옵션코드 자체가 깨지는 문제가 있었음.
#    큐텐 옵션코드 묶음 표기에서 '_'가 구분자로 들어오는 경우는 없고 '+'만 쓰이므로 '+'만 치환.
# ══════════════════════════════════════════════════════════════
def clean_qoo10(df, context=None):
    errors = []
    required = ["상품코드", "옵션정보", "판매자옵션코드"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing} (큐텐 다운로드 파일이 맞는지 확인해주세요)")

    df = df.copy()

    # BeautifulSoup 직접 파싱으로 바뀌면서 모든 값이 문자열로 들어오므로,
    # 합포/일괄/싱글 분류에서 '수량 == 1' 비교가 정확히 되도록 수량만 숫자로 변환해둔다.
    if "수량" in df.columns:
        df["수량"] = pd.to_numeric(df["수량"], errors="coerce")

    # 1. 옵션정보 전체 빈값
    df["옵션정보"] = ""

    # 2. 판매자옵션코드 빈값 -> 상품코드로 채움
    def is_blank(v):
        return pd.isna(v) or str(v).strip() == ""

    filled_count = 0
    still_blank_rows = []
    for idx in df.index:
        if is_blank(df.at[idx, "판매자옵션코드"]):
            fallback = df.at[idx, "상품코드"]
            if is_blank(fallback):
                order_no = df.at[idx, "주문번호"] if "주문번호" in df.columns else "?"
                still_blank_rows.append(f"{idx + 2}행 (주문번호: {order_no}): 판매자옵션코드·상품코드 둘 다 빈값")
            else:
                df.at[idx, "판매자옵션코드"] = fallback
                filled_count += 1

    errors.extend(still_blank_rows)

    # 3. + -> , 치환만 진행 (문자열로 강제 변환 후 처리, '_'는 건드리지 않음)
    df["판매자옵션코드"] = (
        df["판매자옵션코드"].astype(str)
        .str.replace("+", ",", regex=False)
    )
    # NaN이 astype(str)에서 'nan' 문자열이 되는 것 방지
    df.loc[df["판매자옵션코드"] == "nan", "판매자옵션코드"] = ""

    return df, errors, filled_count


# ══════════════════════════════════════════════════════════════
# 아마존 — 파일 정리 로직
#
# 1. H열 YOMIGANA를 G열 RECEIVER_NAME 기준 가타카나로 변환
#    -> api.excelapi.org(한자→히라가나, 히라가나→가타카나 2단계, Yahoo!재팬 API 기반)를 그대로 호출.
#       실제로 사람이 엑셀에서 쓰던 것과 동일한 서비스라 인명 정확도가 pykakasi 자체 사전보다 높음.
#       API 호출이 실패하면(네트워크 오류 등) pykakasi로 대체하고 그 행은 로그에 남김.
#    영어(로마자) 이름은 API/변환기 둘 다 그대로 통과시켜준다.
# 2. AH열 OPTION 전체 빈값
# 3. AI열 ITEM_CODE 전체에서 '+' -> ',' , '_' -> ',' 치환
# 4. AD열 PURCHASE_URL을 AG열 HSCODE 기준으로 URL 목록(fs_amazon_url_map)에서 찾아 채움
#    (HSCODE는 가공 없이 원본 값 그대로 비교 — '*2' 같은 접미사도 그대로 매칭)
# ══════════════════════════════════════════════════════════════
_kakasi_instance = None
_yomigana_cache = {}  # 같은 이름 반복 API호출 방지 (세션 내내 유지되는 캐시)


def _get_kakasi():
    global _kakasi_instance
    if _kakasi_instance is None:
        import pykakasi
        _kakasi_instance = pykakasi.kakasi()
    return _kakasi_instance


def _pykakasi_fallback(text):
    kks = _get_kakasi()
    result = kks.convert(str(text))
    return "".join(r["kana"] for r in result)


#: 요미가나 API가 돌려줘도 되는 문자 — 가나/한자/로마자/숫자/공백/기본 문장부호.
#  사내 프록시·보안 게이트웨이가 "차단 안내 HTML"을 200 OK로 돌려주는 일이 흔한데,
#  그걸 검증 없이 받으면 HTML 덩어리가 이름인 줄 알고 캐시되고 그대로 파일에 저장된다.
#  개발 PC(직결 인터넷)에서는 절대 재현되지 않고 직원 PC(사내망)에서만 나온다.
_YOMIGANA_OK = re.compile(
    r"^[぀-ゟ゠-ヿ一-鿿ｦ-ﾟA-Za-z0-9ー・\s\.\-',/]*$"
)


def _call_excelapi(endpoint, param_name, text, timeout=10):
    import urllib.request
    import urllib.parse
    encoded = urllib.parse.quote(str(text))
    url = f"https://api.excelapi.org/language/{endpoint}?{param_name}={encoded}"
    req = urllib.request.Request(url, headers={
        # UA 없는 요청을 막는 게이트웨이가 있어 명시한다.
        "User-Agent": "ENCLU-SCM/1.0 (+internal tool)",
        "Accept": "text/plain",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if getattr(resp, "status", 200) != 200:
            raise ValueError(f"HTTP {resp.status}")
        raw = resp.read(4096)          # 정상 응답은 이름 한 줄뿐 — 길면 안내 페이지다
        result = raw.decode("utf-8", errors="replace").strip()

    # 응답 검증. 여기서 걸러내지 않으면 잘못된 값이 '성공'으로 저장된다.
    if not result:
        raise ValueError("빈 응답")
    if len(result) > max(40, len(str(text)) * 4):
        raise ValueError(f"응답이 비정상적으로 김 ({len(result)}자) — 안내 페이지로 보임")
    if not _YOMIGANA_OK.match(result):
        raise ValueError(f"이름으로 볼 수 없는 응답: {result[:40]!r}")
    return result


_english_only_pattern = re.compile(r"^[A-Za-z0-9\s\.\-'/,]*$")


def is_english_only(text):
    """영어(로마자)+숫자+공백/기본 문장부호로만 이루어진 이름인지 판별 — 한자/가나가 하나도 없으면 True."""
    return bool(_english_only_pattern.fullmatch(str(text)))


def to_katakana(text):
    """RECEIVER_NAME -> YOMIGANA 변환.
    반환: (변환결과, api_성공여부, 실패사유 또는 None)
    영어(로마자) 이름은 API 호출 없이 그대로 사용.
    1순위: api.excelapi.org로 한자->히라가나->가타카나 2단계 호출 (사람이 엑셀에서 쓰던 것과 동일 서비스)
    2순위(API 실패시): pykakasi로 오프라인 대체 변환 (정확도는 API보다 떨어질 수 있음)
    """
    if pd.isna(text) or str(text).strip() == "":
        return text, True, None
    text = str(text)

    if is_english_only(text):
        return text, True, None  # 영어 이름은 API 호출 없이 원본 그대로 사용

    if text in _yomigana_cache:
        return _yomigana_cache[text], True, None

    # 대량 순차 호출 중 어쩌다 한 번씩 생기는 일시적 타임아웃/지연 대비 — 실패하면 짧게 쉬었다 재시도.
    # 2026-07-29: API 응답이 전반적으로 느려지는 시간대가 있어(4초 타임아웃에 대량 실패 발생),
    # 타임아웃을 10초로 늘리고 재시도도 2회->3회로 늘림.
    last_error = None
    for attempt in range(3):
        try:
            hiragana = _call_excelapi("kanji2kana", "text", text)
            katakana = _call_excelapi("hira-kana", "input", hiragana)
            if katakana:
                _yomigana_cache[text] = katakana
                return katakana, True, None
            last_error = "빈 응답"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt < 2:
                time.sleep(1.0)

    # API 재시도까지 실패 -> pykakasi로 대체
    try:
        return _pykakasi_fallback(text), False, last_error
    except Exception as e:
        return text, False, f"{last_error} / pykakasi도 실패: {e}"


def clean_amazon(df, context=None):
    context = context or {}
    url_map = context.get("url_map", {})  # {HSCODE: URL}

    errors = []
    required = ["RECEIVER_NAME", "YOMIGANA", "OPTION", "ITEM_CODE", "PURCHASE_URL", "HSCODE"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing} (아마존 다운로드 파일이 맞는지 확인해주세요)")

    df = df.copy()

    # 1. YOMIGANA = RECEIVER_NAME 가타카나 변환 (API 우선, 실패시 pykakasi로 대체 + 로그)
    df["YOMIGANA"] = df["YOMIGANA"].astype(object)

    # 같은 이름이 여러 행에 반복되는 경우가 많아서, 고유 이름만 추려서 병렬로 API 호출.
    # (동시에 너무 많이 부르면 무료 API 특성상 오히려 실패율이 올라가는 게 실측으로 확인돼서 3개로 제한)
    unique_names = sorted({
        str(n).strip() for n in df["RECEIVER_NAME"].dropna()
        if str(n).strip() != ""
    })
    name_results = {}
    if unique_names:
        with ThreadPoolExecutor(max_workers=3) as executor:
            for name, result in zip(unique_names, executor.map(to_katakana, unique_names)):
                name_results[name] = result

    api_fallback_count = 0
    for idx in df.index:
        name = df.at[idx, "RECEIVER_NAME"]
        if pd.isna(name) or str(name).strip() == "":
            df.at[idx, "YOMIGANA"] = name
            continue
        kana, api_ok, reason = name_results.get(str(name).strip(), (name, False, "결과 없음"))
        df.at[idx, "YOMIGANA"] = kana
        if not api_ok:
            api_fallback_count += 1
            order_no = df.at[idx, "ORDER_NO1"] if "ORDER_NO1" in df.columns else "?"
            reason_txt = f" (사유: {reason})" if reason else ""
            errors.append(f"{idx + 2}행 (주문번호: {order_no}): 요미가나 API 호출 실패 — pykakasi로 대체 변환됨{reason_txt}")

    # 2. OPTION 전체 빈값
    df["OPTION"] = ""

    # 3. ITEM_CODE + / _ -> , 치환
    df["ITEM_CODE"] = (
        df["ITEM_CODE"].astype(str)
        .str.replace("+", ",", regex=False)
        .str.replace("_", ",", regex=False)
    )
    df.loc[df["ITEM_CODE"] == "nan", "ITEM_CODE"] = ""

    # 4. PURCHASE_URL = HSCODE 매칭 (원본 값 그대로 비교, 가공 없음)
    # PURCHASE_URL 컬럼이 원본에서 전부 빈값(NaN)이면 pandas가 float64로 추론해버려서
    # 문자열(URL)을 넣으려 하면 타입 에러가 남 -> 미리 object(문자열 가능) 타입으로 바꿔둠
    df["PURCHASE_URL"] = df["PURCHASE_URL"].astype(object)
    matched_count = 0
    for idx in df.index:
        hscode = df.at[idx, "HSCODE"]
        if pd.isna(hscode) or str(hscode).strip() == "":
            continue
        hscode_str = str(hscode).strip()
        url = url_map.get(hscode_str)
        if url:
            df.at[idx, "PURCHASE_URL"] = url
            matched_count += 1
        else:
            order_no = df.at[idx, "ORDER_NO1"] if "ORDER_NO1" in df.columns else "?"
            errors.append(f"{idx + 2}행 (주문번호: {order_no}): HSCODE '{hscode_str}'에 매칭되는 URL이 없음")

    return df, errors, matched_count


# ══════════════════════════════════════════════════════════════
# 스타일셀러(자체 플랫폼) — 파일 정리 로직
#
# 아마존과 컬럼 구조는 같지만(ORDER_NO1~OPTION_CODE 표준 WMS 포맷) 필요한 작업은 딱 하나뿐:
#   H열 YOMIGANA를 G열 RECEIVER_NAME 기준 가타카나로 변환 -> 그대로 저장.
# OPTION 비우기 / ITEM_CODE 치환 / PURCHASE_URL 매칭 같은 아마존의 나머지 단계는 해당 없음.
# 변환 로직 자체(API 우선 + pykakasi 대체, 캐시, 영어 이름 패스스루)는 위 to_katakana()를 그대로 재사용.
# ══════════════════════════════════════════════════════════════
def clean_styleseller(df, context=None):
    errors = []
    required = ["RECEIVER_NAME", "YOMIGANA"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing} (스타일셀러 다운로드 파일이 맞는지 확인해주세요)")

    df = df.copy()
    df["YOMIGANA"] = df["YOMIGANA"].astype(object)

    unique_names = sorted({
        str(n).strip() for n in df["RECEIVER_NAME"].dropna()
        if str(n).strip() != ""
    })
    name_results = {}
    if unique_names:
        with ThreadPoolExecutor(max_workers=3) as executor:
            for name, result in zip(unique_names, executor.map(to_katakana, unique_names)):
                name_results[name] = result

    for idx in df.index:
        name = df.at[idx, "RECEIVER_NAME"]
        if pd.isna(name) or str(name).strip() == "":
            df.at[idx, "YOMIGANA"] = name
            continue
        kana, api_ok, reason = name_results.get(str(name).strip(), (name, False, "결과 없음"))
        df.at[idx, "YOMIGANA"] = kana
        if not api_ok:
            order_no = df.at[idx, "ORDER_NO1"] if "ORDER_NO1" in df.columns else "?"
            reason_txt = f" (사유: {reason})" if reason else ""
            errors.append(f"{idx + 2}행 (주문번호: {order_no}): 요미가나 API 호출 실패 — pykakasi로 대체 변환됨{reason_txt}")

    return df, errors, 0  # filled_count는 스타일셀러에선 안 쓰지만 시그니처 통일을 위해 0 고정


# ══════════════════════════════════════════════════════════════
# 라쿠텐 — 파일 정리 로직 (WMS 다운로드 파일 + 원본 파일 두 개를 합쳐서 처리)
#
# 1. WMS 파일 A열(ORDER_NO1)과 원본파일 A열(注文番号)이 같은 행을 찾아서,
#    WMS 파일 X열(OPTION_CODE)의 값을 원본파일 BW열(商品管理番号)에 넣어준다.
#    ※ WMS 파일은 AI열도 이름이 똑같이 'OPTION_CODE'라서 이름으로는 X열을 특정할 수 없음 —
#       그래서 이 값만 이름이 아니라 위치(24번째 컬럼, 인덱스 23)로 직접 가져온다.
# 2. 원본파일 CC열(項目・選択肢) 전체 빈값
# 3. 원본파일 FB열(SKU情報) 전체 빈값
# 4. 원본파일 FA열(システム連携用SKU番号) 전체에서 '+' -> ',' , '_' -> ',' 치환
# ══════════════════════════════════════════════════════════════
def clean_rakuten(wms_df, original_df):
    errors = []
    wms_df = wms_df.reset_index(drop=True)
    original_df = original_df.reset_index(drop=True)

    if "ORDER_NO1" not in wms_df.columns:
        raise ValueError("WMS 다운로드 파일에 ORDER_NO1 컬럼이 없습니다. (라쿠텐 WMS 파일이 맞는지 확인해주세요)")
    if wms_df.shape[1] <= 23:
        raise ValueError("WMS 다운로드 파일의 컬럼 구성이 예상과 다릅니다 (X열 OPTION_CODE를 찾을 수 없음).")

    required_orig = ["注文番号", "商品管理番号", "項目・選択肢", "SKU情報", "システム連携用SKU番号"]
    missing_orig = [c for c in required_orig if c not in original_df.columns]
    if missing_orig:
        raise ValueError(f"원본 파일 필수 컬럼 누락: {missing_orig} (라쿠텐 원본 파일이 맞는지 확인해주세요)")

    # ORDER_NO1 -> X열(OPTION_CODE, 위치로 접근) 매핑
    wms_order_no = wms_df["ORDER_NO1"].astype(str).str.strip()
    wms_option_code_x = wms_df.iloc[:, 23]
    wms_map = {}
    for order_no, code in zip(wms_order_no, wms_option_code_x):
        if order_no == "" or order_no == "nan":
            continue
        wms_map[order_no] = code  # 같은 주문번호가 여러 번 나오면 마지막 값으로 덮어씀

    df = original_df.copy()
    df["商品管理番号"] = df["商品管理番号"].astype(object)

    matched_count = 0
    order_col = df["注文番号"].astype(str).str.strip()
    for idx in df.index:
        key = order_col.iloc[idx]
        if key in wms_map:
            df.at[idx, "商品管理番号"] = wms_map[key]
            matched_count += 1
        else:
            errors.append(f"{idx + 2}행 (注文番号: {key or '(빈값)'}): WMS 파일에서 매칭되는 주문을 찾을 수 없음")

    # 2. 項目・選択肢 전체 빈값
    df["項目・選択肢"] = ""

    # 3. SKU情報 전체 빈값
    df["SKU情報"] = ""

    # 4. システム連携用SKU番号 + / _ -> , 치환
    df["システム連携用SKU番号"] = (
        df["システム連携用SKU番号"].astype(str)
        .str.replace("+", ",", regex=False)
        .str.replace("_", ",", regex=False)
    )
    df.loc[df["システム連携用SKU番号"] == "nan", "システム連携用SKU番号"] = ""

    return df, errors, matched_count


PLATFORM_CLEANERS = {
    "큐텐": clean_qoo10,
    "아마존": clean_amazon,
    "스타일셀러": clean_styleseller,
    # "라쿠텐"은 파일 두 개(WMS+원본)를 받아야 해서 다른 플랫폼과 시그니처가 달라 이 딕셔너리에는 안 넣고
    # run_process에서 platform=="라쿠텐"일 때 clean_rakuten을 직접 호출함.
}


# ══════════════════════════════════════════════════════════════
# 공통 분류 로직 — 합포 → 일괄 → 싱글 → 단품
# (플랫폼 공통 로직. 컬럼명만 플랫폼별로 다르게 넘겨주면 재사용 가능)
#
# 순서:
#   1. 합포: 장바구니(주문묶음) 번호가 같은 행이 2개 이상이면 전부 '합포'로 분리
#   2. 일괄: 남은 행 중 수량=1 이고, 옵션코드가 일괄코드 목록에 있으면 '일괄'로 분리.
#      단, 그 코드의 남은수량만큼만 뜯어내고(선착순), 뜯어낸 만큼 남은수량 차감.
#      남은수량이 0이 되면 그 코드는 목록에서 자동 제외됨.
#   3. 싱글: 남은 행 중 수량=1 이고, 같은 옵션코드가 기준값(N) 이상 나오면 '싱글'로 분리.
#      (모드6은 콤마 뒤쪽 사은품코드 기준으로 동일하게 판단 — VIDIVICI 방식)
#   4. 단품: 그러고도 남은 행 전부.
# ══════════════════════════════════════════════════════════════
def classify_orders(df, mode, single_threshold, consume_fn=None,
                     cart_col="장바구니번호", code_col="판매자옵션코드", qty_col="수량", date_col="주문일"):
    """
    mode: MODES 리스트의 문자열 값 그대로
    consume_fn: 일괄코드 소진을 실제로 수행하는 콜백. {code: 필요건수} -> {code: 실제로 내준 수량}
                (run_process에서 consume_batch_codes_atomic을 넘겨줌 — DB 행 잠금으로 이중 차감을 막음)
    date_col: 일괄코드 수량이 부족할 때 누구부터 배정할지 정하는 기준 — 주문일이 빠른 건부터 우선 배정.
    반환: (result_dict, logs, usage_log)
      result_dict 키는 "합포"/"일괄"/"싱글"/"단품" 중 이번 모드에서 실제로 쓰인 것만 들어있음
      usage_log: [{"code": str, "used_qty": int}, ...] — 이번 실행에서 실제로 소진된 일괄코드 내역
                 (브랜드/일시는 호출부(run_process)에서 붙여서 fs_batch_usage_log에 남김)
    """
    logs = []
    df = df.reset_index(drop=True).copy()
    remaining = df.copy()
    result = {}
    usage_log = []

    use_bundle = mode != MODES[0]
    use_batch = mode in MODES_NEED_BATCH
    use_single = mode == MODES[3] or mode == MODES[4]          # 일반 싱글 (모드4,5)
    use_gift_single = mode == MODES[5]                          # 싱글(사은품 동일, VIDIVICI 방식, 모드6)

    # ── ① 합포 ──
    if use_bundle:
        if cart_col not in remaining.columns:
            raise ValueError(f"합포 판단 기준 컬럼 '{cart_col}'이 파일에 없습니다.")
        counts = remaining[cart_col].value_counts()
        bundle_keys = counts[counts >= 2].index
        mask = remaining[cart_col].isin(bundle_keys)
        result["합포"] = remaining[mask].copy()
        remaining = remaining[~mask].copy()
        logs.append(f"합포: {len(result['합포']):,}행 분리 (장바구니 {len(bundle_keys):,}개)")

    # ── ② 일괄 (수량=1 조건 필수). 실제 소진은 DB 행 잠금으로 원자적으로 처리(consume_fn) —
    #     동시에 다른 사람이 처리 중이어도 같은 코드를 이중으로 뜯어가지 않음.
    #     수량이 모자라서 그 코드에 해당하는 행을 다 못 뜯을 경우, 주문일이 빠른 것부터 우선 배정한다. ──
    if use_batch:
        picked_idx = []
        if qty_col in remaining.columns and code_col in remaining.columns:
            eligible = remaining[remaining[qty_col] == 1]
            if date_col in eligible.columns:
                eligible = eligible.copy()
                eligible["_order_dt"] = pd.to_datetime(eligible[date_col], errors="coerce")
                eligible = eligible.sort_values("_order_dt", na_position="last")
            groups = {code: g for code, g in eligible.groupby(code_col, sort=False)}
            needed_counts = {code: len(g) for code, g in groups.items()}
            if needed_counts and consume_fn is not None:
                taken = consume_fn(needed_counts)
                for code, take_n in taken.items():
                    if take_n <= 0:
                        continue
                    group = groups.get(code)
                    if group is None:
                        continue
                    take_rows = group.iloc[:take_n]  # 위에서 주문일 오름차순 정렬해뒀으므로 오래된 순으로 뜯김
                    picked_idx.extend(take_rows.index.tolist())
                    usage_log.append({"code": code, "used_qty": len(take_rows)})
            elif needed_counts and consume_fn is None:
                logs.append("⚠️ 일괄코드 소진 콜백이 없어 일괄 분류를 건너뜁니다 (DB 연결 확인 필요)")

        result["일괄"] = remaining.loc[picked_idx].copy()
        remaining = remaining.drop(index=picked_idx)
        logs.append(f"일괄: {len(picked_idx):,}행 분리")

    # ── ③ 싱글 (일반 — 동일 옵션코드가 기준값 이상, 수량=1) ──
    if use_single:
        if qty_col not in remaining.columns or code_col not in remaining.columns:
            raise ValueError("싱글 분류에 필요한 수량/옵션코드 컬럼이 없습니다.")
        candidates = remaining[remaining[qty_col] == 1]
        code_counts = candidates[code_col].value_counts()
        valid_codes = code_counts[code_counts >= single_threshold].index
        mask_idx = candidates[candidates[code_col].isin(valid_codes)].index
        result["싱글"] = remaining.loc[mask_idx].copy()
        remaining = remaining.drop(index=mask_idx)
        logs.append(f"싱글: {len(mask_idx):,}행 분리 (기준 {single_threshold}건 이상, 옵션코드 {len(valid_codes):,}종)")

    # ── ③' 싱글(사은품 동일) — VIDIVICI 방식.
    #     '정리' 단계에서 이미 +/_ 가 전부 콤마로 바뀐 값을 그대로 콤마 기준으로 파싱한다
    #     (원래 매크로도 정리 끝난 파일에 콤마 파싱만 돌리는 방식이었으므로 동일하게 구현).
    #     콤마로 나눈 조각 중 맨 앞(본품코드)만 빼고 나머지 조각 전체를 '사은품 묶음'으로 보고,
    #     그 묶음이 기준값 이상 반복되면 싱글로 분리한다.
    #     (맨 뒤 조각 하나만 보면 안 됨 — 3조각짜리에서 가운데=진짜 사은품, 맨뒤=공통 동봉품인 경우가 있어서
    #      맨 뒤만 같고 가운데가 다른 것끼리 잘못 합쳐지는 문제가 실제로 있었음. 반드시 나머지 조각 '전체'가
    #      똑같아야 같은 묶음으로 센다.)
    #     콤마가 없는(=사은품 없는) 단일코드는 이 분류 대상이 아니라 단품으로 남는다.
    if use_gift_single:
        if qty_col not in remaining.columns or code_col not in remaining.columns:
            raise ValueError("싱글(사은품) 분류에 필요한 수량/옵션코드 컬럼이 없습니다.")
        candidates = remaining[remaining[qty_col] == 1].copy()

        def extract_gift(v):
            parts = [p.strip() for p in str(v).split(",") if p.strip() != ""]
            return tuple(parts[1:]) if len(parts) >= 2 else None  # 콤마 없으면(조각 1개) 사은품 없음

        candidates["__gift__"] = candidates[code_col].apply(extract_gift)
        gift_candidates = candidates[candidates["__gift__"].notna()]
        gift_counts = gift_candidates["__gift__"].value_counts()
        valid_gifts = set(gift_counts[gift_counts >= single_threshold].index)
        mask_idx = gift_candidates[gift_candidates["__gift__"].isin(valid_gifts)].index

        result["싱글"] = remaining.loc[mask_idx].copy()
        remaining = remaining.drop(index=mask_idx)
        logs.append(f"싱글(사은품 동일): {len(mask_idx):,}행 분리 (기준 {single_threshold}건 이상, 사은품묶음 {len(valid_gifts):,}종)")

    result["단품"] = remaining.copy()
    logs.append(f"단품(나머지): {len(remaining):,}행")

    return result, logs, usage_log


# ══════════════════════════════════════════════════════════════
# 탭 ② 브랜드 관리 — Frame으로 구현해서 Notebook 탭 안에 그대로 들어감
# ══════════════════════════════════════════════════════════════
class BrandTab(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent, padding=16)
        self.on_change = on_change
        self.brands = []

        ttk.Label(self, text="🏷️ 진행 중인 브랜드 목록", font=("맑은 고딕", 12, "bold")).pack(anchor="w", pady=(0, 10))
        ttk.Label(
            self, text="DB에 저장돼서 다른 PC에서 켠 프로그램에도 그대로 반영됩니다 (몇 초 내로 자동 동기화).",
            foreground="#888", font=("맑은 고딕", 8)
        ).pack(anchor="w", pady=(0, 8))

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("맑은 고딕", 10))
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        add_row = ttk.Frame(self)
        add_row.pack(fill="x", pady=(10, 4))
        self.new_brand_var = tk.StringVar()
        entry = ttk.Entry(add_row, textvariable=self.new_brand_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda e: self.add_brand())
        ttk.Button(add_row, text="➕ 추가", command=self.add_brand).pack(side="left", padx=(6, 0))

        ttk.Button(self, text="🗑️ 선택 삭제", command=self.delete_selected).pack(fill="x", pady=(4, 0))

        self.refresh()
        self._poll()

    def _poll(self):
        self.refresh()
        self.after(POLL_INTERVAL_MS, self._poll)

    def refresh(self):
        try:
            self.brands = load_brands()
        except Exception as e:
            self.brands = []
            print(f"[BrandTab] DB 조회 실패: {e}")
        self._refresh_listbox()

    def _refresh_listbox(self):
        self.listbox.delete(0, "end")
        for b in self.brands:
            self.listbox.insert("end", b)

    def add_brand(self):
        name = self.new_brand_var.get().strip()
        if not name:
            return
        try:
            added = add_brand(name)
        except Exception as e:
            messagebox.showerror("DB 오류", f"브랜드 추가 실패:\n{e}")
            return
        if not added:
            messagebox.showwarning("중복", "이미 등록된 브랜드입니다.")
            return
        self.new_brand_var.set("")
        self.refresh()
        self.on_change()

    def delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        if messagebox.askyesno("삭제 확인", f"'{name}' 브랜드를 삭제할까요?"):
            try:
                delete_brand(name)
            except Exception as e:
                messagebox.showerror("DB 오류", f"브랜드 삭제 실패:\n{e}")
                return
            self.refresh()
            self.on_change()


# ══════════════════════════════════════════════════════════════
# 탭 ③ 일괄 관리 — 옵션코드/수량/상품명/사은품 + 소진 로그
# ══════════════════════════════════════════════════════════════
class BatchTab(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent, padding=16)
        self.on_change = on_change
        self.batch_codes = []

        ttk.Label(self, text="📦 일괄코드 목록", font=("맑은 고딕", 12, "bold")).pack(anchor="w")
        ttk.Label(
            self, text="수량=1인 주문 중 이 옵션코드와 일치하는 건이 매칭될 때마다 남은수량이 차감되고,\n"
                       "0이 되면 자동으로 목록에서 빠집니다. DB로 관리돼서 다른 PC와 실시간에 가깝게 동기화됩니다.",
            foreground="#888", font=("맑은 고딕", 8), justify="left"
        ).pack(anchor="w", pady=(2, 10))

        # ── 목록 (Treeview: 코드 / 수량 / 상품명 / 사은품) ──
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(list_frame, columns=("code", "qty", "product_name", "gift"), show="headings", height=8)
        self.tree.heading("code", text="옵션코드")
        self.tree.heading("qty", text="남은수량")
        self.tree.heading("product_name", text="상품명")
        self.tree.heading("gift", text="사은품")
        self.tree.column("code", width=110)
        self.tree.column("qty", width=70, anchor="center")
        self.tree.column("product_name", width=180)
        self.tree.column("gift", width=140)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # ── 추가/수정 입력 ──
        form = ttk.Frame(self)
        form.pack(fill="x", pady=(10, 4))
        row_a = ttk.Frame(form)
        row_a.pack(fill="x", pady=2)
        ttk.Label(row_a, text="옵션코드", width=9).pack(side="left")
        self.code_var = tk.StringVar()
        ttk.Entry(row_a, textvariable=self.code_var, width=16).pack(side="left", padx=(0, 12))
        ttk.Label(row_a, text="수량", width=5).pack(side="left")
        self.qty_var = tk.StringVar(value="1")
        ttk.Entry(row_a, textvariable=self.qty_var, width=8).pack(side="left")

        row_b = ttk.Frame(form)
        row_b.pack(fill="x", pady=2)
        ttk.Label(row_b, text="상품명", width=9).pack(side="left")
        self.product_name_var = tk.StringVar()
        ttk.Entry(row_b, textvariable=self.product_name_var).pack(side="left", fill="x", expand=True, padx=(0, 12))

        row_c = ttk.Frame(form)
        row_c.pack(fill="x", pady=2)
        ttk.Label(row_c, text="사은품", width=9).pack(side="left")
        self.gift_var = tk.StringVar()
        ttk.Entry(row_c, textvariable=self.gift_var).pack(side="left", fill="x", expand=True)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(6, 4))
        ttk.Button(btn_row, text="➕ 추가", command=self.add_code).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(btn_row, text="✏️ 선택 수정", command=self.update_selected).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(btn_row, text="🗑️ 선택 삭제", command=self.delete_selected).pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="📥 엑셀로 일괄 추가 (옵션코드/수량/상품명/사은품)", command=self.import_excel).pack(fill="x", pady=(4, 0))
        ttk.Button(self, text="⚠️ 전체 삭제", command=self.delete_all).pack(fill="x", pady=(2, 0))

        # ── 소진 로그 (선택해서 되돌리기 가능) ──
        ttk.Label(self, text="📋 소진 로그 (언제 · 어느 브랜드 · 어떤 코드 · 몇 개)", font=("맑은 고딕", 10, "bold")).pack(anchor="w", pady=(14, 4))
        ttk.Label(
            self, text="파일을 잘못 잘랐을 때, 아래에서 해당 소진 건을 선택하고 '되돌리기'를 누르면 그 수량만큼 자동으로 복원됩니다.",
            foreground="#888", font=("맑은 고딕", 8)
        ).pack(anchor="w")
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True, pady=(4, 0))
        self.log_tree = ttk.Treeview(log_frame, columns=("date", "brand", "code", "used_qty", "status"), show="headings", height=6)
        self.log_tree.heading("date", text="일시")
        self.log_tree.heading("brand", text="브랜드")
        self.log_tree.heading("code", text="옵션코드")
        self.log_tree.heading("used_qty", text="소진 수량")
        self.log_tree.heading("status", text="상태")
        self.log_tree.column("date", width=140)
        self.log_tree.column("brand", width=90)
        self.log_tree.column("code", width=100)
        self.log_tree.column("used_qty", width=80, anchor="center")
        self.log_tree.column("status", width=70, anchor="center")
        self.log_tree.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_tree.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_tree.config(yscrollcommand=log_scroll.set)

        ttk.Button(self, text="↩️ 선택 소진 되돌리기", command=self.revert_selected_usage).pack(fill="x", pady=(4, 0))
        ttk.Button(self, text="📥 소진 로그 엑셀 다운로드 (전체)", command=self.export_usage_log).pack(fill="x", pady=(4, 0))

        self.refresh()
        self._poll()

    def _poll(self):
        self.refresh()
        self.after(POLL_INTERVAL_MS, self._poll)

    def refresh(self):
        try:
            self.batch_codes = load_batch_codes()
            usage = load_batch_usage_log()
        except Exception as e:
            self.batch_codes = []
            usage = []
            print(f"[BatchTab] DB 조회 실패: {e}")
        self._refresh_tree()
        self._refresh_usage_log(usage)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for b in self.batch_codes:
            self.tree.insert("", "end", values=(
                b.get("code", ""), b.get("remaining_qty", 0),
                b.get("product_name", ""), b.get("gift", "")
            ))

    def _refresh_usage_log(self, usage):
        self.log_tree.delete(*self.log_tree.get_children())
        for entry in usage:  # load_batch_usage_log()가 이미 최신순으로 줌
            status = "↩️ 되돌림" if entry.get("reverted") else "정상"
            self.log_tree.insert("", "end", iid=str(entry["id"]), values=(
                entry.get("date", ""), entry.get("brand", ""),
                entry.get("code", ""), entry.get("used_qty", ""), status
            ))

    def revert_selected_usage(self):
        sel = self.log_tree.selection()
        if not sel:
            messagebox.showwarning("선택 필요", "되돌릴 소진 내역을 먼저 선택해주세요.")
            return
        log_id = int(sel[0])
        values = self.log_tree.item(sel[0], "values")
        date_str, brand, code, used_qty, status = values
        if status == "↩️ 되돌림":
            messagebox.showwarning("이미 되돌림", "이 항목은 이미 되돌려진 내역입니다.")
            return

        if not messagebox.askyesno(
            "되돌리기 확인",
            f"이 소진 내역을 되돌릴까요?\n\n일시: {date_str}\n브랜드: {brand}\n옵션코드: {code}\n소진수량: {used_qty}\n\n"
            f"'{code}' 코드의 남은수량에 {used_qty}개가 다시 더해집니다."
        ):
            return

        try:
            ok, msg = revert_batch_usage(log_id)
        except Exception as e:
            messagebox.showerror("DB 오류", f"되돌리기 실패:\n{e}")
            return

        if not ok:
            messagebox.showwarning("되돌리기 불가", msg)
        else:
            messagebox.showinfo("완료", msg)

        self.refresh()
        self.on_change()

    def export_usage_log(self):
        try:
            full_log = load_batch_usage_log(limit=None)
        except Exception as e:
            messagebox.showerror("DB 오류", f"소진 로그 조회 실패:\n{e}")
            return

        if not full_log:
            messagebox.showinfo("내보낼 내용 없음", "소진 로그가 비어있습니다.")
            return

        default_name = f"일괄소진로그_{datetime.now().strftime('%Y%m%d')}.xlsx"
        path = filedialog.asksaveasfilename(
            title="소진 로그 저장 위치",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("엑셀 파일", "*.xlsx")]
        )
        if not path:
            return

        df = pd.DataFrame(full_log)
        df = df.rename(columns={
            "id": "번호", "date": "일시", "brand": "브랜드",
            "code": "옵션코드", "used_qty": "소진수량", "reverted": "되돌림여부"
        })
        df["되돌림여부"] = df["되돌림여부"].map({True: "되돌림", False: "정상"})

        try:
            df.to_excel(path, index=False, engine="xlsxwriter")
        except Exception as e:
            messagebox.showerror("저장 오류", f"엑셀 저장 실패:\n{e}")
            return

        messagebox.showinfo("완료", f"소진 로그 {len(df):,}건을 저장했습니다.\n\n{path}")

    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        code, qty, product_name, gift = self.tree.item(sel[0], "values")
        self.code_var.set(code)
        self.qty_var.set(str(qty))
        self.product_name_var.set(product_name)
        self.gift_var.set(gift)

    def _validate_qty(self):
        try:
            qty = int(self.qty_var.get())
            if qty < 0:
                raise ValueError
            return qty
        except ValueError:
            messagebox.showwarning("입력 오류", "수량은 0 이상의 정수로 입력해주세요.")
            return None

    def add_code(self):
        code = self.code_var.get().strip()
        if not code:
            messagebox.showwarning("입력 필요", "옵션코드를 입력해주세요.")
            return
        qty = self._validate_qty()
        if qty is None:
            return
        product_name = self.product_name_var.get().strip()
        gift = self.gift_var.get().strip()

        try:
            existing = check_existing_batch_codes([code])
        except Exception as e:
            messagebox.showerror("DB 오류", f"기존 코드 확인 실패:\n{e}")
            return

        if existing:
            proceed = messagebox.askyesno(
                "⚠️ 이미 등록된 코드",
                f"'{code}'는 이미 등록되어 있습니다.\n\n"
                "그대로 진행하면 삭제/교체가 아니라 기존 남은수량에 지금 입력한 수량이 그대로 더해집니다(합산).\n\n"
                "계속 진행할까요?"
            )
            if not proceed:
                return

        try:
            bulk_upsert_batch_codes([{"code": code, "qty": qty, "product_name": product_name, "gift": gift}])
        except Exception as e:
            messagebox.showerror("DB 오류", f"저장 실패:\n{e}")
            return
        self.refresh()
        self.on_change()

    def update_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("선택 필요", "목록에서 수정할 코드를 먼저 선택해주세요.")
            return
        qty = self._validate_qty()
        if qty is None:
            return
        old_code = self.tree.item(sel[0], "values")[0]
        try:
            update_batch_code(
                old_code, self.code_var.get().strip(), qty,
                self.product_name_var.get().strip(), self.gift_var.get().strip()
            )
        except Exception as e:
            messagebox.showerror("DB 오류", f"수정 실패:\n{e}")
            return
        self.refresh()
        self.on_change()

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        code = self.tree.item(sel[0], "values")[0]
        try:
            delete_batch_code(code)
        except Exception as e:
            messagebox.showerror("DB 오류", f"삭제 실패:\n{e}")
            return
        self.refresh()
        self.on_change()

    def delete_all(self):
        if not self.batch_codes:
            return
        if messagebox.askyesno("전체 삭제 확인", "일괄코드 목록을 전부 삭제할까요? 되돌릴 수 없습니다."):
            try:
                delete_all_batch_codes()
            except Exception as e:
                messagebox.showerror("DB 오류", f"전체 삭제 실패:\n{e}")
                return
            self.refresh()
            self.on_change()

    def import_excel(self):
        path = filedialog.askopenfilename(
            title="일괄코드 엑셀 파일 선택 (옵션코드/수량 필수, 상품명/사은품 선택)",
            filetypes=[("엑셀/CSV 파일", "*.xls *.xlsx *.csv"), ("모든 파일", "*.*")]
        )
        if not path:
            return

        try:
            df = read_wms_excel(path)
        except Exception as e:
            messagebox.showerror("파일 읽기 오류", f"파일을 읽지 못했습니다:\n{e}")
            return

        df.columns = df.columns.astype(str).str.strip()
        if "옵션코드" not in df.columns or "수량" not in df.columns:
            messagebox.showerror("컬럼 오류", "필수 컬럼(옵션코드, 수량)이 없습니다.\n헤더명을 확인해주세요.")
            return

        rows = []
        errors = []
        for idx, row in df.iterrows():
            code = str(row["옵션코드"]).strip() if pd.notna(row["옵션코드"]) else ""
            if not code:
                errors.append(f"{idx + 2}행: 옵션코드가 비어있음")
                continue
            try:
                qty = int(row["수량"])
                if qty < 0:
                    raise ValueError
            except (ValueError, TypeError):
                errors.append(f"{idx + 2}행: 수량이 올바르지 않음 ('{row['수량']}')")
                continue
            product_name = str(row["상품명"]).strip() if ("상품명" in df.columns and pd.notna(row["상품명"])) else ""
            gift = str(row["사은품"]).strip() if ("사은품" in df.columns and pd.notna(row["사은품"])) else ""
            rows.append({"code": code, "qty": qty, "product_name": product_name, "gift": gift})

        if not rows:
            messagebox.showwarning("등록할 내용 없음", f"유효한 행이 없습니다.\n\n오류 {len(errors)}건")
            return

        # 이미 등록된 코드가 섞여있으면 "수량이 합산된다"는 경고를 먼저 보여주고 진행/취소를 받는다
        codes_in_file = [r["code"] for r in rows]
        try:
            existing = check_existing_batch_codes(codes_in_file)
        except Exception as e:
            messagebox.showerror("DB 오류", f"기존 코드 확인 실패:\n{e}")
            return

        if existing:
            preview = ", ".join(sorted(existing)[:15])
            more = f" 외 {len(existing) - 15}건" if len(existing) > 15 else ""
            proceed = messagebox.askyesno(
                "⚠️ 이미 등록된 코드 발견",
                f"이미 등록되어 있는 옵션코드가 {len(existing)}건 있습니다:\n{preview}{more}\n\n"
                "그대로 진행하면 해당 코드들은 삭제/교체가 아니라 "
                "기존 남은수량에 엑셀의 수량이 그대로 더해집니다(합산).\n\n"
                "계속 진행할까요?"
            )
            if not proceed:
                return

        try:
            ok_count = bulk_upsert_batch_codes(rows)
        except Exception as e:
            messagebox.showerror("DB 오류", f"일괄 등록 실패:\n{e}")
            return

        self.refresh()
        self.on_change()

        msg = f"등록/합산 완료: {ok_count}건"
        if errors:
            msg += f"\n\n⚠️ 건너뛴 행 {len(errors)}건:\n" + "\n".join(errors[:20])
            if len(errors) > 20:
                msg += f"\n... 외 {len(errors) - 20}건 더 있음"
        messagebox.showinfo("엑셀 업로드 완료", msg)


# ══════════════════════════════════════════════════════════════
# 탭 ④ 아마존 URL 관리 — HSCODE / ASIN / URL
# (3단계에서 실제 매칭 로직을 붙이기 전에 저장소부터 미리 구축해두는 용도)
# ══════════════════════════════════════════════════════════════
class AmazonUrlTab(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent, padding=16)
        self.on_change = on_change
        self.url_map = []

        ttk.Label(self, text="🔗 아마존 URL 목록 (HSCODE / ASIN / URL)", font=("맑은 고딕", 12, "bold")).pack(anchor="w")
        ttk.Label(
            self, text="아마존 정리 단계(3단계)에서 AG열(HSCODE) 값과 이 목록을 비교해 AD열(PURCHASE_URL)을 자동으로 채울 예정입니다.\n"
                       "지금은 저장소만 미리 만들어둔 상태라, 목록을 미리 채워두시면 3단계 개발 후 바로 쓸 수 있어요. (DB로 실시간 동기화)",
            foreground="#888", font=("맑은 고딕", 8), justify="left"
        ).pack(anchor="w", pady=(2, 10))

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(list_frame, columns=("hscode", "asin", "url"), show="headings", height=12)
        self.tree.heading("hscode", text="HSCODE")
        self.tree.heading("asin", text="ASIN")
        self.tree.heading("url", text="URL")
        self.tree.column("hscode", width=120)
        self.tree.column("asin", width=120)
        self.tree.column("url", width=260)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.Frame(self)
        form.pack(fill="x", pady=(10, 4))
        row_a = ttk.Frame(form)
        row_a.pack(fill="x", pady=2)
        ttk.Label(row_a, text="HSCODE", width=8).pack(side="left")
        self.hscode_var = tk.StringVar()
        ttk.Entry(row_a, textvariable=self.hscode_var, width=16).pack(side="left", padx=(0, 12))
        ttk.Label(row_a, text="ASIN", width=6).pack(side="left")
        self.asin_var = tk.StringVar()
        ttk.Entry(row_a, textvariable=self.asin_var, width=16).pack(side="left")

        row_b = ttk.Frame(form)
        row_b.pack(fill="x", pady=2)
        ttk.Label(row_b, text="URL", width=8).pack(side="left")
        self.url_var = tk.StringVar()
        ttk.Entry(row_b, textvariable=self.url_var).pack(side="left", fill="x", expand=True)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(6, 4))
        ttk.Button(btn_row, text="➕ 추가", command=self.add_entry).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(btn_row, text="✏️ 선택 수정", command=self.update_selected).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(btn_row, text="🗑️ 선택 삭제", command=self.delete_selected).pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="📥 엑셀로 일괄 추가 (HSCODE/ASIN/URL, 겹치면 덮어씀)", command=self.import_excel).pack(fill="x", pady=(4, 0))
        ttk.Button(self, text="⚠️ 전체 삭제", command=self.delete_all).pack(fill="x", pady=(2, 0))

        self.refresh()
        self._poll()

    def _poll(self):
        self.refresh()
        self.after(POLL_INTERVAL_MS, self._poll)

    def refresh(self):
        try:
            self.url_map = load_amazon_url_map()
        except Exception as e:
            self.url_map = []
            print(f"[AmazonUrlTab] DB 조회 실패: {e}")
        self._refresh_tree()

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for u in self.url_map:
            self.tree.insert("", "end", values=(u.get("hscode", ""), u.get("asin", ""), u.get("url", "")))

    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        hscode, asin, url = self.tree.item(sel[0], "values")
        self.hscode_var.set(hscode)
        self.asin_var.set(asin)
        self.url_var.set(url)

    def add_entry(self):
        hscode = self.hscode_var.get().strip()
        if not hscode:
            messagebox.showwarning("입력 필요", "HSCODE를 입력해주세요.")
            return
        try:
            add_amazon_url(hscode, self.asin_var.get().strip(), self.url_var.get().strip())
        except Exception as e:
            messagebox.showerror("DB 오류", f"이미 등록된 HSCODE이거나 저장에 실패했습니다:\n{e}")
            return
        self.refresh()
        self.on_change()

    def update_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("선택 필요", "목록에서 수정할 항목을 먼저 선택해주세요.")
            return
        old_hscode = self.tree.item(sel[0], "values")[0]
        try:
            update_amazon_url(old_hscode, self.hscode_var.get().strip(), self.asin_var.get().strip(), self.url_var.get().strip())
        except Exception as e:
            messagebox.showerror("DB 오류", f"수정 실패:\n{e}")
            return
        self.refresh()
        self.on_change()

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        hscode = self.tree.item(sel[0], "values")[0]
        try:
            delete_amazon_url(hscode)
        except Exception as e:
            messagebox.showerror("DB 오류", f"삭제 실패:\n{e}")
            return
        self.refresh()
        self.on_change()

    def delete_all(self):
        if not self.url_map:
            return
        if messagebox.askyesno("전체 삭제 확인", "아마존 URL 목록을 전부 삭제할까요? 되돌릴 수 없습니다."):
            try:
                delete_all_amazon_urls()
            except Exception as e:
                messagebox.showerror("DB 오류", f"전체 삭제 실패:\n{e}")
                return
            self.refresh()
            self.on_change()

    def import_excel(self):
        path = filedialog.askopenfilename(
            title="아마존 URL 엑셀 파일 선택 (HSCODE 필수, ASIN/URL 선택)",
            filetypes=[("엑셀/CSV 파일", "*.xls *.xlsx *.csv"), ("모든 파일", "*.*")]
        )
        if not path:
            return

        try:
            df = read_wms_excel(path)
        except Exception as e:
            messagebox.showerror("파일 읽기 오류", f"파일을 읽지 못했습니다:\n{e}")
            return

        df.columns = df.columns.astype(str).str.strip()
        if "HSCODE" not in df.columns:
            messagebox.showerror("컬럼 오류", "필수 컬럼(HSCODE)이 없습니다.\n헤더명을 확인해주세요.")
            return

        rows = []
        errors = []
        for idx, row in df.iterrows():
            hscode = str(row["HSCODE"]).strip() if pd.notna(row["HSCODE"]) else ""
            if not hscode:
                errors.append(f"{idx + 2}행: HSCODE가 비어있음")
                continue
            asin = str(row["ASIN"]).strip() if ("ASIN" in df.columns and pd.notna(row["ASIN"])) else ""
            url = str(row["URL"]).strip() if ("URL" in df.columns and pd.notna(row["URL"])) else ""
            rows.append({"hscode": hscode, "asin": asin, "url": url})

        if not rows:
            messagebox.showwarning("등록할 내용 없음", f"유효한 행이 없습니다.\n\n오류 {len(errors)}건")
            return

        # 아마존 URL은 겹쳐도 경고 없이 최신 값으로 그대로 덮어씀
        try:
            ok_count = bulk_upsert_amazon_urls(rows)
        except Exception as e:
            messagebox.showerror("DB 오류", f"일괄 등록 실패:\n{e}")
            return

        self.refresh()
        self.on_change()

        msg = f"등록/갱신 완료: {ok_count}건"
        if errors:
            msg += f"\n\n⚠️ 건너뛴 행 {len(errors)}건:\n" + "\n".join(errors[:20])
            if len(errors) > 20:
                msg += f"\n... 외 {len(errors) - 20}건 더 있음"
        messagebox.showinfo("엑셀 업로드 완료", msg)


# ══════════════════════════════════════════════════════════════
# 탭 ① 주문 정리 — 기존 메인 화면 그대로, Frame으로 옮김
# ══════════════════════════════════════════════════════════════
class OrderTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(16, 14))
        self.app = app  # App 인스턴스 (settings, log 등 공유)

        self.input_path_var = tk.StringVar(value="")
        self.input_path2_var = tk.StringVar(value="")  # 라쿠텐 원본파일 전용
        self.output_folder_var = tk.StringVar(value=app.settings.get("output_folder", ""))
        self.platform_var = tk.StringVar(value=PLATFORMS[0])
        self.brand_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value=MODES[0])

        sub = ttk.Label(
            self, text="큐텐: 정리+모드1~6 동작 · 아마존/라쿠텐/스타일셀러: 정리(모드1)만 동작",
            foreground="#888", font=("맑은 고딕", 9)
        )
        sub.pack(anchor="w", pady=(0, 10))

        # ── 옵션 영역 ──
        opt_frame = ttk.LabelFrame(self, text="① 옵션 선택", padding=14)
        opt_frame.pack(fill="x", pady=(0, 10))

        row1 = ttk.Frame(opt_frame)
        row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="플랫폼", width=10).pack(side="left")
        platform_combo = ttk.Combobox(row1, textvariable=self.platform_var, values=PLATFORMS, state="readonly")
        platform_combo.pack(side="left", fill="x", expand=True)
        platform_combo.bind("<<ComboboxSelected>>", self.on_platform_change)

        row2 = ttk.Frame(opt_frame)
        row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="브랜드", width=10).pack(side="left")
        self.brand_combo = ttk.Combobox(row2, textvariable=self.brand_var, values=[], state="readonly")
        self.brand_combo.pack(side="left", fill="x", expand=True)
        ttk.Label(row2, text="(브랜드 관리 탭에서 추가/삭제)", foreground="#888", font=("맑은 고딕", 8)).pack(side="left", padx=(6, 0))

        row3 = ttk.Frame(opt_frame)
        row3.pack(fill="x", pady=4)
        ttk.Label(row3, text="자르는 방식", width=10).pack(side="left", anchor="n")
        self.mode_combo = ttk.Combobox(row3, textvariable=self.mode_var, values=MODES, state="readonly", width=42)
        self.mode_combo.pack(side="left", fill="x", expand=True)
        self.mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)

        # 일괄코드 상태 (모드3,4에서만 표시) — 관리는 '일괄 관리' 탭에서
        self.batch_row = ttk.Frame(opt_frame)
        ttk.Label(self.batch_row, text="일괄코드", width=10).pack(side="left")
        self.batch_status_label = ttk.Label(self.batch_row, text="", foreground="#666")
        self.batch_status_label.pack(side="left", fill="x", expand=True)
        ttk.Label(self.batch_row, text="(일괄 관리 탭에서 추가/삭제)", foreground="#888", font=("맑은 고딕", 8)).pack(side="left", padx=(6, 0))

        # 싱글 기준값 (모드4,5,6에서만 표시)
        self.single_row = ttk.Frame(opt_frame)
        ttk.Label(self.single_row, text="싱글 기준값", width=10).pack(side="left")
        self.single_threshold_var = tk.IntVar(value=5)
        ttk.Spinbox(self.single_row, from_=2, to=999, textvariable=self.single_threshold_var, width=8).pack(side="left")
        ttk.Label(self.single_row, text="건 이상이면 싱글로 분리", foreground="#888").pack(side="left", padx=(6, 0))

        self.on_mode_change()  # 초기 상태 반영

        # ── 파일 선택 영역 ──
        self.file_frame = ttk.LabelFrame(self, text="② WMS 다운로드 파일 선택", padding=14)
        self.file_frame.pack(fill="x", pady=(0, 10))

        file_row = ttk.Frame(self.file_frame)
        file_row.pack(fill="x")
        ttk.Entry(file_row, textvariable=self.input_path_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(file_row, text="파일 선택", command=self.select_input_file).pack(side="left", padx=(6, 0))

        # 라쿠텐 전용 — 원본 파일도 같이 필요 (평소엔 숨겨져 있다가 플랫폼=라쿠텐일 때만 표시)
        self.raku_file_row = ttk.Frame(self.file_frame)
        ttk.Label(self.raku_file_row, text="라쿠텐 원본 파일", foreground="#333", font=("맑은 고딕", 9, "bold")).pack(anchor="w", pady=(8, 2))
        raku_inner = ttk.Frame(self.raku_file_row)
        raku_inner.pack(fill="x")
        ttk.Entry(raku_inner, textvariable=self.input_path2_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(raku_inner, text="파일 선택", command=self.select_input_file2).pack(side="left", padx=(6, 0))

        # ── 출력 폴더 영역 ──
        out_frame = ttk.LabelFrame(self, text="③ 기본 저장 폴더", padding=14)
        out_frame.pack(fill="x", pady=(0, 10))

        out_row = ttk.Frame(out_frame)
        out_row.pack(fill="x")
        ttk.Entry(out_row, textvariable=self.output_folder_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(out_row, text="변경", command=self.select_output_folder).pack(side="left", padx=(6, 0))
        ttk.Label(out_frame, text="한 번 지정해두면 계속 이 폴더에 저장됩니다.", foreground="#888", font=("맑은 고딕", 8)).pack(anchor="w", pady=(4, 0))

        # ── 실행 버튼 + 상태 표시 ──
        run_row = ttk.Frame(self)
        run_row.pack(fill="x", pady=(6, 4))
        self.run_btn = ttk.Button(run_row, text="▶ 실행", command=self.run_process)
        self.run_btn.pack(side="left", fill="x", expand=True, ipady=8)

        status_row = ttk.Frame(self)
        status_row.pack(fill="x", pady=(0, 10))
        self.status_label = ttk.Label(status_row, text="⚪ 준비", font=("맑은 고딕", 10, "bold"))
        self.status_label.pack(side="left")

        # ── 로그 영역 ──
        log_frame = ttk.LabelFrame(self, text="처리 로그", padding=10)
        log_frame.pack(fill="both", expand=True)
        self.log_box = scrolledtext.ScrolledText(
            log_frame, height=12, state="disabled",
            bg="#0c0c0c", fg="#33ff33", insertbackground="#33ff33",
            font=("Consolas", 9), wrap="word"
        )
        self.log_box.pack(fill="both", expand=True)

        self.on_platform_change()  # 초기 플랫폼(큐텐) 기준으로 모드 목록 동기화
        self.refresh_batch_status()
        self._poll()

    def _poll(self):
        self.refresh_brand_list()
        self.refresh_batch_status()
        self.after(POLL_INTERVAL_MS, self._poll)

    # ── 로그 출력 (백그라운드 스레드에서 불러도 안전 — 항상 after()로 메인 스레드에 위임) ──
    def log(self, text):
        self.after(0, self._append_log_line, text)

    def _append_log_line(self, text):
        self.log_box.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {text}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ── 상태 표시 (준비/진행 중/저장 중/완료/오류) — 역시 after()로 스레드 안전하게 처리 ──
    def set_status(self, text):
        self.after(0, lambda: self.status_label.config(text=text))

    # ── 브랜드 콤보박스 새로고침 (브랜드 관리 탭에서 변경됐을 때 App이 호출) ──
    def refresh_brand_list(self):
        try:
            brands = load_brands()
        except Exception as e:
            print(f"[OrderTab] 브랜드 조회 실패: {e}")
            return
        self.brand_combo["values"] = brands
        if self.brand_var.get() not in brands:
            self.brand_var.set(brands[0] if brands else "")

    # ── 파일/폴더 선택 ──
    def select_input_file(self):
        path = filedialog.askopenfilename(
            title="WMS 다운로드 파일 선택",
            filetypes=[("엑셀/CSV 파일", "*.xls *.xlsx *.csv"), ("모든 파일", "*.*")]
        )
        if path:
            self.input_path_var.set(path)

    def select_input_file2(self):
        path = filedialog.askopenfilename(
            title="라쿠텐 원본 파일 선택",
            filetypes=[("엑셀/CSV 파일", "*.xls *.xlsx *.csv"), ("모든 파일", "*.*")]
        )
        if path:
            self.input_path2_var.set(path)

    def on_platform_change(self, event=None):
        platform = self.platform_var.get()
        if platform == "라쿠텐":
            self.file_frame.config(text="② WMS 다운로드 파일 선택 (+ 라쿠텐은 원본파일도 필요)")
            self.raku_file_row.pack(fill="x")
        else:
            self.file_frame.config(text="② WMS 다운로드 파일 선택")
            self.raku_file_row.pack_forget()
            self.input_path2_var.set("")

        # 플랫폼별로 실제 지원하는 모드만 드롭다운에 남기기 (아마존/라쿠텐은 아직 '정리'만 지원)
        supported = PLATFORM_SUPPORTED_MODES.get(platform, [MODES[0]])
        self.mode_combo["values"] = supported
        if self.mode_var.get() not in supported:
            self.mode_var.set(supported[0])
        self.on_mode_change()

    def on_mode_change(self, event=None):
        mode = self.mode_var.get()
        if mode in MODES_NEED_BATCH:
            self.batch_row.pack(fill="x", pady=4)
            self.refresh_batch_status()
        else:
            self.batch_row.pack_forget()
        if mode in MODES_NEED_SINGLE_THRESHOLD:
            self.single_row.pack(fill="x", pady=4)
        else:
            self.single_row.pack_forget()

    def refresh_batch_status(self):
        try:
            codes = load_batch_codes()
        except Exception as e:
            self.batch_status_label.config(text=f"⚠️ DB 조회 실패: {e}")
            return
        active = [b for b in codes if b["remaining_qty"] > 0]
        if active:
            self.batch_status_label.config(text=f"등록됨 {len(active)}종 (남은수량 합계 {sum(b['remaining_qty'] for b in active):,}개)")
        else:
            self.batch_status_label.config(text="등록된 일괄코드 없음 — '일괄 관리' 탭에서 추가해주세요")

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="기본 저장 폴더 선택")
        if folder:
            self.output_folder_var.set(folder)
            self.app.settings["output_folder"] = folder
            save_settings(self.app.settings)
            self.log(f"기본 저장 폴더 설정: {folder}")

    # ── 실행 ──
    def run_process(self):
        platform = self.platform_var.get()
        brand = self.brand_var.get()
        mode = self.mode_var.get()
        input_path = self.input_path_var.get()
        output_folder = self.output_folder_var.get()

        if not input_path:
            messagebox.showwarning("입력 필요", "WMS 다운로드 파일을 먼저 선택해주세요.")
            return
        if platform == "라쿠텐" and not self.input_path2_var.get():
            messagebox.showwarning("입력 필요", "라쿠텐은 원본 파일도 함께 선택해주세요.")
            return
        if not brand:
            messagebox.showwarning("입력 필요", "브랜드를 선택해주세요. (없으면 '브랜드 관리' 탭에서 먼저 추가)")
            return
        if not output_folder:
            messagebox.showwarning("입력 필요", "기본 저장 폴더를 먼저 지정해주세요.")
            return

        if platform not in IMPLEMENTED_PLATFORMS:
            messagebox.showinfo("준비중", f"'{platform}' 플랫폼은 아직 개발 중입니다. (다음 단계에서 추가 예정)")
            return
        if mode not in IMPLEMENTED_MODES:
            messagebox.showinfo("준비중", f"'{mode}' 모드는 아직 개발 중입니다.")
            return

        # 실제 처리(파일 읽기·API 호출·저장)는 시간이 걸릴 수 있어서 화면이 안 멈추도록 백그라운드 스레드에서 실행.
        # 실행 중 중복 클릭 방지를 위해 버튼도 잠가둠.
        self.run_btn.config(state="disabled")
        self.set_status("🟡 진행 중...")
        self.log(f"===== 실행 시작 — 플랫폼:{platform} / 브랜드:{brand} / 모드:{mode} =====")
        self.log(f"입력 파일(WMS): {input_path}")
        if platform == "라쿠텐":
            self.log(f"입력 파일(원본): {self.input_path2_var.get()}")

        thread = threading.Thread(
            target=self._run_process_worker,
            args=(platform, brand, mode, input_path, output_folder, self.input_path2_var.get()),
            daemon=True
        )
        thread.start()

    def _finish_run(self, status_text):
        """처리 종료(성공/실패 무관) 시 버튼/상태를 원상복구 — 항상 메인 스레드에서 실행되도록 예약."""
        def _do():
            self.run_btn.config(state="normal")
            self.status_label.config(text=status_text)
        self.after(0, _do)

    def _check_output_writable(self, output_folder, date_str, brand):
        """일괄 차감 전에 결과 파일들을 실제로 쓸 수 있는지 확인한다.
        반환: 못 쓰는 파일 이름 목록 (비어 있으면 이상 없음).

        엑셀로 열어둔 파일은 열려 있어도 읽기는 되므로, 'a' 모드로 실제로 열어봐야 걸린다.
        폴더 자체를 못 쓰는 경우도 같이 잡는다."""
        blocked = []
        try:
            os.makedirs(output_folder, exist_ok=True)
        except Exception as e:
            return [f"{output_folder} (폴더를 만들 수 없음: {e})"]

        probe = os.path.join(output_folder, f".~write_test_{os.getpid()}.tmp")
        try:
            with open(probe, "w"):
                pass
            os.remove(probe)
        except Exception as e:
            return [f"{output_folder} (폴더에 쓸 수 없음: {e})"]

        for label in ("합포", "일괄", "싱글", "단품"):
            path = os.path.join(output_folder, f"{date_str}_{brand}_{label}.xlsx")
            if not os.path.exists(path):
                continue
            try:
                with open(path, "a"):
                    pass
            except Exception:
                blocked.append(os.path.basename(path))
        return blocked

    def _revert_usage(self, log_ids):
        """저장 실패로 되돌려야 하는 일괄 차감을 원복한다."""
        ok = 0
        for log_id in log_ids:
            try:
                done, msg = revert_batch_usage(log_id)
                if done:
                    ok += 1
                    self.log(f"    [차감 원복] {msg}")
                else:
                    self.log(f"    ⚠️ 차감 원복 실패(log id {log_id}): {msg}")
            except Exception as e:
                self.log(f"    ⚠️ 차감 원복 중 오류(log id {log_id}): {e}")
        self.log(f"↩️ 저장 실패로 일괄 차감 {ok}/{len(log_ids)}건을 되돌렸습니다.")
        self.after(0, self.refresh_batch_status)
        self.after(0, self.app.refresh_batch_tab)

    def _run_process_worker(self, platform, brand, mode, input_path, output_folder, input_path2=""):
        try:
            if platform == "라쿠텐":
                wms_df = read_wms_excel(input_path)
                self.log(f"WMS 다운로드 파일 로드 완료 — {len(wms_df):,}행")
                orig_df = read_wms_excel(input_path2)
                self.log(f"원본 파일 로드 완료 — {len(orig_df):,}행")
                df = orig_df  # 아래 공통 코드(모드1 저장 등)에서는 정리 대상인 원본파일 기준으로 다룸
            else:
                df = read_wms_excel(input_path)
                self.log(f"파일 로드 완료 — {len(df):,}행")

            context = {}
            if platform == "아마존":
                try:
                    url_list = load_amazon_url_map()
                except Exception as e:
                    self.log(f"❌ 아마존 URL 목록 조회 실패: {e}")
                    self.after(0, lambda err=e: messagebox.showerror("DB 오류", f"아마존 URL 목록을 불러오지 못했습니다:\n{err}"))
                    self._finish_run("🔴 오류")
                    return
                context["url_map"] = {u["hscode"]: u["url"] for u in url_list}
                self.log(f"아마존 URL 목록 {len(context['url_map']):,}건 로드 완료")

            self.set_status("🟡 정리 중...")
            if platform == "라쿠텐":
                df_cleaned, errors, filled_count = clean_rakuten(wms_df, orig_df)
            else:
                cleaner = PLATFORM_CLEANERS[platform]
                df_cleaned, errors, filled_count = cleaner(df, context)

            if platform == "라쿠텐":
                self.log(f"商品管理番号 매칭 성공: {filled_count:,}건")
            elif platform == "아마존":
                self.log(f"PURCHASE_URL 매칭 성공: {filled_count:,}건")

                # 요미가나는 API 결과가 정확도의 핵심이라 — 하나라도 API 호출이 실패하면(pykakasi로 대체됐더라도)
                # 저장하지 않고 재실행을 안내한다. (API가 될 때도 있고 안 될 때도 있는 불안정한 상황 대비)
                yomigana_failures = [e for e in errors if "요미가나 API 호출 실패" in e]
                if yomigana_failures:
                    self.log(f"❌ 요미가나 API 호출 실패 {len(yomigana_failures)}건 발견 — 저장을 중단합니다.")
                    for e in yomigana_failures[:15]:
                        self.log(f"    - {e}")
                    if len(yomigana_failures) > 15:
                        self.log(f"    ... 외 {len(yomigana_failures) - 15}건 더 있음")
                    self.after(0, lambda: messagebox.showerror(
                        "요미가나 API 실패 — 저장 중단",
                        f"요미가나 변환 API 호출이 {len(yomigana_failures)}건 실패했습니다.\n\n"
                        "일시적인 네트워크/API 문제로 보입니다.\n"
                        "잠시 후 '실행'을 다시 눌러 재시도해주세요. (파일은 저장되지 않았습니다)"
                    ))
                    self._finish_run("🔴 오류 — 재실행 필요")
                    return

                # URL은 필수값 — 하나라도 못 채운 게 있으면 저장 자체를 막는다
                url_col = df_cleaned["PURCHASE_URL"].astype(str)
                missing_mask = df_cleaned["PURCHASE_URL"].isna() | (url_col.str.strip() == "") | (url_col.str.strip() == "nan")
                if missing_mask.any():
                    hscode_col = df_cleaned["HSCODE"].astype(str)
                    blank_hscode_mask = df_cleaned["HSCODE"].isna() | (hscode_col.str.strip() == "") | (hscode_col.str.strip() == "nan")
                    unmatched_mask = missing_mask & ~blank_hscode_mask
                    missing_hscodes = sorted(df_cleaned.loc[unmatched_mask, "HSCODE"].astype(str).unique().tolist())
                    blank_hscode_count = int((missing_mask & blank_hscode_mask).sum())

                    parts = []
                    if missing_hscodes:
                        parts.append(f"URL을 찾을 수 없는 HSCODE ({len(missing_hscodes)}종):\n" + ", ".join(missing_hscodes))
                    if blank_hscode_count:
                        parts.append(f"HSCODE 자체가 비어있는 행: {blank_hscode_count}건")
                    detail = "\n\n".join(parts)

                    self.log(f"❌ URL 미매칭 {int(missing_mask.sum())}행 발견 — 저장을 중단합니다.")
                    self.log(f"    {detail.replace(chr(10), ' / ')}")
                    self.after(0, lambda: messagebox.showerror(
                        "URL 없음 — 저장 중단",
                        f"{detail}\n\nURL은 필수값이라 파일을 저장하지 않았습니다.\n"
                        "'아마존 URL 관리' 탭에서 먼저 등록한 뒤 다시 실행해주세요."
                    ))
                    self._finish_run("🔴 오류")
                    return
            elif platform == "스타일셀러":
                # 아마존과 동일한 to_katakana()를 쓰므로, 같은 이유로 API 실패 시 저장을 막는다.
                yomigana_failures = [e for e in errors if "요미가나 API 호출 실패" in e]
                if yomigana_failures:
                    self.log(f"❌ 요미가나 API 호출 실패 {len(yomigana_failures)}건 발견 — 저장을 중단합니다.")
                    for e in yomigana_failures[:15]:
                        self.log(f"    - {e}")
                    if len(yomigana_failures) > 15:
                        self.log(f"    ... 외 {len(yomigana_failures) - 15}건 더 있음")
                    self.after(0, lambda: messagebox.showerror(
                        "요미가나 API 실패 — 저장 중단",
                        f"요미가나 변환 API 호출이 {len(yomigana_failures)}건 실패했습니다.\n\n"
                        "일시적인 네트워크/API 문제로 보입니다.\n"
                        "잠시 후 '실행'을 다시 눌러 재시도해주세요. (파일은 저장되지 않았습니다)"
                    ))
                    self._finish_run("🔴 오류 — 재실행 필요")
                    return
            else:
                self.log(f"판매자옵션코드 빈값 → 상품코드로 채운 행: {filled_count:,}건")

            if errors:
                self.log(f"⚠️ 예외 {len(errors)}건 발견 (처리는 계속 진행됨):")
                for e in errors[:30]:
                    self.log(f"    - {e}")
                if len(errors) > 30:
                    self.log(f"    ... 외 {len(errors) - 30}건 더 있음")

            date_str = datetime.now().strftime("%Y%m%d")
            self.set_status("💾 저장 중...")

            if mode == MODES[0]:
                # 모드1: 정리만 하고 파일 하나로 저장
                out_name = f"{date_str}_{brand}_정리.xlsx"
                out_path = os.path.join(output_folder, out_name)
                df_cleaned.to_excel(out_path, index=False, engine="xlsxwriter")
                self.log(f"✅ 저장 완료: {out_path}")
                self.after(0, lambda: messagebox.showinfo("완료", f"처리 완료!\n\n저장 위치: {out_path}\n\n예외 {len(errors)}건 (로그 확인)"))
            else:
                # 모드2~6: 합포/일괄/싱글/단품으로 분류해서 각각 파일로 저장
                single_threshold = self.single_threshold_var.get()

                # 일괄 차감은 파일을 쓰기 전에 일어나기 때문에, 저장이 실패하면 코드만 날아간다.
                # 실제로 가장 흔한 실패는 '같은 이름의 파일을 엑셀로 열어둔 상태'다 —
                # 차감하기 전에 미리 쓸 수 있는지 확인해서, 아예 시작을 막는다.
                if mode in MODES_NEED_BATCH:
                    locked = self._check_output_writable(output_folder, date_str, brand)
                    if locked:
                        self.log("❌ 저장할 파일이 열려 있어 실행을 중단합니다 (일괄코드는 차감되지 않았습니다):")
                        for f in locked:
                            self.log(f"    - {f}")
                        self.after(0, lambda: messagebox.showerror(
                            "파일이 열려 있음 — 실행 중단",
                            "아래 파일이 다른 프로그램(엑셀 등)에서 열려 있어 저장할 수 없습니다.\n\n"
                            + "\n".join(locked)
                            + "\n\n닫은 뒤 다시 실행해주세요.\n"
                              "일괄코드는 차감되지 않았습니다."
                        ))
                        self._finish_run("🔴 오류 — 파일 닫고 재실행")
                        return

                consume_fn = consume_batch_codes_atomic if mode in MODES_NEED_BATCH else None
                result, class_logs, usage_log = classify_orders(
                    df_cleaned, mode, single_threshold, consume_fn=consume_fn
                )
                for line in class_logs:
                    self.log(f"    {line}")

                usage_log_ids = []
                if mode in MODES_NEED_BATCH:
                    if usage_log:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        log_entries = [
                            {"date": now_str, "brand": brand, "code": u["code"], "used_qty": u["used_qty"]}
                            for u in usage_log
                        ]
                        usage_log_ids = append_batch_usage_log(log_entries)
                        for u in usage_log:
                            self.log(f"    [일괄 소진] {u['code']}: {u['used_qty']}개 차감 (브랜드: {brand})")
                    self.after(0, self.refresh_batch_status)
                    self.after(0, self.app.refresh_batch_tab)
                    self.log("일괄코드 DB 갱신 완료 (소진된 코드는 자동 제외됨)")

                saved_paths = []
                try:
                    for label, df_part in result.items():
                        if df_part.empty:
                            self.log(f"    ({label}: 0건이라 저장 생략)")
                            continue
                        out_name = f"{date_str}_{brand}_{label}.xlsx"
                        out_path = os.path.join(output_folder, out_name)
                        df_part.to_excel(out_path, index=False, engine="xlsxwriter")
                        saved_paths.append(out_path)
                        self.log(f"✅ 저장 완료 ({label}, {len(df_part):,}행): {out_path}")
                except Exception:
                    # 파일을 못 썼는데 코드만 차감된 상태로 두면 안 된다 — 차감을 되돌린다.
                    if usage_log_ids:
                        self._revert_usage(usage_log_ids)
                    raise

                self.after(0, lambda: messagebox.showinfo(
                    "완료",
                    f"처리 완료!\n\n저장된 파일 {len(saved_paths)}개\n저장 폴더: {output_folder}\n\n예외 {len(errors)}건 (로그 확인)"
                ))

            self._finish_run("🟢 완료")

        except Exception as e:
            self.log(f"❌ 오류 발생: {e}")
            self.log(traceback.format_exc())
            self.after(0, lambda err=e: messagebox.showerror("오류", f"처리 중 오류가 발생했습니다:\n\n{err}"))
            self._finish_run("🔴 오류")


# ══════════════════════════════════════════════════════════════
# 메인 앱 — 상단 탭 4개(주문정리/브랜드관리/일괄관리/아마존URL관리)
# ══════════════════════════════════════════════════════════════
class App:
    def __init__(self, root):
        self.root = root
        root.title("ENCLU 파일 찢기 프로그램")
        root.geometry("700x820")
        root.minsize(620, 700)

        self.settings = load_settings()

        header = ttk.Label(root, text="✂️ ENCLU 파일 찢기 프로그램", font=("맑은 고딕", 14, "bold"))
        header.pack(pady=(14, 10))

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.order_tab = OrderTab(self.notebook, self)
        self.brand_tab = BrandTab(self.notebook, on_change=self.refresh_order_tab_brands)
        self.batch_tab = BatchTab(self.notebook, on_change=self.refresh_order_tab_batch)
        self.amazon_tab = AmazonUrlTab(self.notebook, on_change=lambda: None)

        self.notebook.add(self.order_tab, text="📋 주문 정리")
        self.notebook.add(self.brand_tab, text="🏷️ 브랜드 관리")
        self.notebook.add(self.batch_tab, text="📦 일괄 관리")
        self.notebook.add(self.amazon_tab, text="🔗 아마존 URL 관리")

        # 탭을 옮길 때마다 그 탭 내용을 최신 상태로 새로고침 (다른 탭에서 수정했을 수 있으므로)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def on_tab_changed(self, event=None):
        current = self.notebook.select()
        widget = self.notebook.nametowidget(current)
        if widget is self.order_tab:
            self.order_tab.refresh_brand_list()
            self.order_tab.refresh_batch_status()
        elif widget is self.brand_tab:
            self.brand_tab.refresh()
        elif widget is self.batch_tab:
            self.batch_tab.refresh()
        elif widget is self.amazon_tab:
            self.amazon_tab.refresh()

    # BrandTab/BatchTab에서 변경사항이 생겼을 때 주문정리 탭 쪽 표시를 즉시 갱신하기 위한 콜백
    def refresh_order_tab_brands(self):
        self.order_tab.refresh_brand_list()

    def refresh_order_tab_batch(self):
        self.order_tab.refresh_batch_status()

    def refresh_batch_tab(self):
        self.batch_tab.refresh()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()