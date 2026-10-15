# -*- coding: utf-8 -*-
"""Supabase(원본)와 로컬 DB(대상)를 테이블 목록·컬럼 구성·행수로 대조해 이전이 정확한지 검증.

행수 규칙
  - 대상 < 원본 → 실패(!!)
  - 정수형 id가 양쪽에 있고 대상 >= 원본 → 원본 MIN(id)~MAX(id) 범위 안의 대상 행수가 원본 행수 이상인지 확인.
      미충족이면 실패. 충족이면 행수가 같으면 OK, 대상이 많으면 "증가"(전환 후 로컬에서 쌓인 행 — 정보).
      행수가 같아도 확인하는 이유: 원본 k건 누락 + 로컬 신규 k건이면 행수만으로는 OK처럼 보인다.
  - id가 없으면 행수만: 같으면 OK, 대상이 많으면 기본은 "증가(확인 못 함)" 정보, --strict면 실패.
대상에만 있는 테이블은 정보, 원본에만 있는 테이블·컬럼 구성(이름·data_type) 차이는 실패.

한계 (이 도구가 "전체 일치"여도 해지 전 따로 확인할 것)
  - 범위 확인은 근사다. 로컬에서 새로 생긴 행의 id가 원본 범위의 빈 번호에 들어가거나(시퀀스가 원본 MAX(id)보다
    낮게 잡힌 경우, id를 외부 값으로 정하는 테이블), 같은 수만큼 다른 행으로 바뀐 경우는 누락을 못 잡는다.
    → 로컬 시퀀스 현재값 >= 원본 MAX(id)인지 확인.
  - 컬럼은 이름·data_type만 비교한다(길이·정밀도·NOT NULL·기본값·enum 이름은 미비교).
    information_schema는 권한 있는 컬럼만 보여 주므로 권한 문제도 "컬럼 구성 다름"으로 나올 수 있다.
  - public 스키마의 테이블만 본다. 시퀀스 값·뷰·함수·트리거·RLS 정책은 비교하지 않는다.

원본(Supabase)은 저사양이라 가벼운 쿼리만 보낸다: 카탈로그 조회, COUNT(*), id MIN/MAX(카탈로그에서 id 인덱스를
확인한 테이블만 — 인덱스가 없으면 범위 확인을 건너뛰고 "id 없음"과 같게 처리), 쿼리당 시간 상한(SOURCE_STATEMENT_TIMEOUT).
범위 안 행수 세기는 대상(로컬)에서만 한다. 데이터 조회는 모두 "public".테이블로 스키마를 명시한다(search_path 영향 없음).

사용: py verify_migration.py [--strict]
종료코드: 실패 0건이면 0, 불일치·조회 실패가 있으면 1 (배치·스크립트에서 성공 여부 판단용).
"""
import os, sys, io
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from pathlib import Path

ROOT = Path(__file__).resolve().parent
from dotenv import dotenv_values
# 새 폴더의 UPH .env는 전환 후 로컬 URL이라 Supabase 원본은 구 폴더(또는 SUPABASE_URL 환경변수)에서 읽는다
OLD_UPH_ENV = ROOT.parent.parent / "통합시스템" / "UPH 시스템" / ".env"

INT_TYPES = {"integer", "bigint", "smallint"}
SOURCE_STATEMENT_TIMEOUT = "60s"  # 원본 쿼리 하나가 이보다 오래 걸리면 끊고 실패로 집계


def list_tables(conn):
    return [r[0] for r in conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).fetchall()]


def column_map(conn, table):
    """{컬럼명: 타입} — information_schema 기준."""
    rows = conn.execute(text("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position
    """), {"t": table}).fetchall()
    return {r[0]: r[1] for r in rows}


def qt(table):
    """스키마를 명시한 안전한 테이블 식별자 — 다른 스키마의 동명 테이블과 섞이지 않게."""
    return '"public"."' + table.replace('"', '""') + '"'


def count_rows(conn, table):
    return conn.execute(text(f"SELECT COUNT(*) FROM {qt(table)}")).scalar()


def source_has_id_index(src_conn, table):
    """public.<table>의 id가 유효한 인덱스의 첫 컬럼인지 (MIN/MAX가 인덱스로 끝나는지) — 카탈로그만 조회."""
    return src_conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0]
            WHERE n.nspname = 'public' AND c.relname = :t AND a.attname = 'id' AND i.indisvalid
        )
    """), {"t": table}).scalar()


def source_id_range(src_conn, table):
    return src_conn.execute(text(f"SELECT MIN(id), MAX(id) FROM {qt(table)}")).one()


def target_rows_in_range(dst_conn, table, lo, hi):
    return dst_conn.execute(text(f"SELECT COUNT(*) FROM {qt(table)} WHERE id BETWEEN :lo AND :hi"),
                            {"lo": lo, "hi": hi}).scalar()


def judge(n_src, n_dst, cols_src, cols_dst, in_range, strict):
    """(상태, 비고). in_range: 원본 id 범위 안의 대상 행수(정수 id가 없으면 None, 원본이 비었으면 n_src와 같게)."""
    if cols_src != cols_dst:
        only_s = sorted(set(cols_src.items()) - set(cols_dst.items()))
        only_d = sorted(set(cols_dst.items()) - set(cols_src.items()))
        return "!!", f"컬럼 구성 다름 (원본만: {only_s}, 로컬만: {only_d})"
    if n_dst < n_src:
        return "!!", f"로컬 행 {n_src - n_dst:,}건 부족"
    if in_range is not None:
        if in_range < n_src:
            return "!!", f"원본 id 범위 안의 로컬 행이 {n_src - in_range:,}건 부족"
        if n_dst == n_src:
            return "OK", ""
        return "증가", "전환 후 로컬에서 늘어남 — 원본 id 범위 안 행수 충분(근사 확인)"
    if n_dst == n_src:
        return "OK", ""
    if strict:
        return "!!", "로컬이 더 많음 — id가 없어 원본 행 포함 여부 확인 불가 (--strict)"
    return "증가", "로컬이 더 많음 — id가 없어 원본 행 포함 여부는 확인 못 함"


def compare(src, dst, strict=False):
    """원본과 대상을 대조해 표로 출력. 실패가 하나도 없으면 True."""
    with src.connect() as s:
        src_tables = list_tables(s)
    with dst.connect() as d:
        dst_tables = list_tables(d)

    print(f"{'테이블':<32} {'Supabase':>12} {'로컬':>12} {'상태':>6}  비고")
    failures, notes = 0, 0
    for t in src_tables:
        if t not in dst_tables:
            print(f"{t:<32} {'':>12} {'':>12} {'!!':>6}  로컬에 테이블 없음")
            failures += 1
            continue
        stage = "Supabase"
        try:
            with src.connect() as s:
                cols_src = column_map(s, t)
                n_src = count_rows(s, t)
                # 인덱스 없는 id에 MIN/MAX를 보내면 원본 전체 스캔이 되므로 확인된 경우만
                has_int_id = cols_src.get("id") in INT_TYPES and source_has_id_index(s, t)
                lo_hi = source_id_range(s, t) if has_int_id else None
            stage = "로컬"
            with dst.connect() as d:
                cols_dst = column_map(d, t)
                n_dst = count_rows(d, t)
                in_range = None
                if lo_hi is not None and cols_dst.get("id") in INT_TYPES:
                    lo, hi = lo_hi
                    in_range = n_src if lo is None else target_rows_in_range(d, t, lo, hi)
        except Exception as e:
            print(f"{t:<32} [{stage} 조회 실패: {e}]")
            failures += 1
            continue
        status, memo = judge(n_src, n_dst, cols_src, cols_dst, in_range, strict)
        failures += status == "!!"
        notes += status == "증가"
        print(f"{t:<32} {n_src:>12,} {n_dst:>12,} {status:>6}  {memo}")

    for t in dst_tables:
        if t not in src_tables:
            print(f"{t:<32} {'':>12} {'':>12} {'정보':>6}  로컬에만 있는 테이블")

    if failures:
        print(f"\n[경고] 실패 {failures}건 — 위 목록에서 !! 확인")
    else:
        print("\n전체 일치" + (f" (로컬 증가 {notes}건은 정보)" if notes else ""))
    print("※ 비교하지 않는 것: 시퀀스 값(로컬 >= 원본 MAX(id) 확인 권장)·뷰·함수·트리거·RLS, 컬럼 길이·NOT NULL 등 — 해지 전 따로 확인")
    return failures == 0


def limit_source_queries(engine):
    """원본(PostgreSQL) 트랜잭션마다 쿼리 시간 상한. 연결 문자열 옵션 대신 SET LOCAL을 써서 풀러(pooler)에서도 동작."""
    if engine.dialect.name != "postgresql":
        return

    @event.listens_for(engine, "begin")
    def _timeout(conn):
        conn.exec_driver_sql(f"SET LOCAL statement_timeout = '{SOURCE_STATEMENT_TIMEOUT}'")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    strict = "--strict" in sys.argv[1:]
    supabase_url = os.environ.get("SUPABASE_URL") or dotenv_values(OLD_UPH_ENV).get("DATABASE_URL")
    load_dotenv(ROOT / ".env")
    local_url = os.environ["LOCAL_DB_URL"]
    if not supabase_url or "supabase" not in supabase_url:
        sys.exit(f"Supabase 접속정보를 찾지 못했거나 Supabase가 아닙니다 (구 폴더 .env 또는 SUPABASE_URL 확인): {OLD_UPH_ENV}")

    src = create_engine(supabase_url, connect_args={"connect_timeout": 15})
    limit_source_queries(src)
    dst = create_engine(local_url)
    sys.exit(0 if compare(src, dst, strict=strict) else 1)


if __name__ == "__main__":
    main()
