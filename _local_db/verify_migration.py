# -*- coding: utf-8 -*-
"""Supabase와 로컬 DB의 테이블별 행수를 대조해 이전이 정확한지 검증."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pathlib import Path

ROOT = Path(__file__).resolve().parent
from dotenv import dotenv_values
# 새 폴더의 UPH .env는 전환 후 로컬 URL이라 Supabase 원본은 구 폴더(또는 SUPABASE_URL 환경변수)에서 읽는다
OLD_UPH_ENV = ROOT.parent.parent / "통합시스템" / "UPH 시스템" / ".env"
SUPABASE_URL = os.environ.get("SUPABASE_URL") or dotenv_values(OLD_UPH_ENV).get("DATABASE_URL")
load_dotenv(ROOT / ".env")
LOCAL_URL = os.environ["LOCAL_DB_URL"]
if not SUPABASE_URL or "supabase" not in SUPABASE_URL:
    sys.exit(f"Supabase 접속정보를 찾지 못했거나 Supabase가 아닙니다 (구 폴더 .env 또는 SUPABASE_URL 확인): {OLD_UPH_ENV}")

src = create_engine(SUPABASE_URL, connect_args={"connect_timeout": 15})
dst = create_engine(LOCAL_URL)

with src.connect() as c:
    tables = [r[0] for r in c.execute(text("""
        SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename
    """)).fetchall()]

print(f"{'테이블':<32} {'Supabase':>12} {'로컬':>12} {'일치':>6}")
all_ok = True
for t in tables:
    try:
        with src.connect() as c:
            n_src = c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
    except Exception as e:
        print(f"{t:<32} [Supabase 조회 실패: {e}]")
        all_ok = False
        continue
    try:
        with dst.connect() as c:
            n_dst = c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
    except Exception as e:
        print(f"{t:<32} [로컬 조회 실패: {e}]")
        all_ok = False
        continue
    ok = "OK" if n_src == n_dst else "!!"
    if n_src != n_dst:
        all_ok = False
    print(f"{t:<32} {n_src:>12,} {n_dst:>12,} {ok:>6}")

print("\n전체 일치" if all_ok else "\n[경고] 불일치 테이블 있음 — 위 목록에서 !! 확인")
