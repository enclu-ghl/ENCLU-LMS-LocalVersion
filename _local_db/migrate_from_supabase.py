# -*- coding: utf-8 -*-
"""Supabase -> 로컬 PostgreSQL(enclu_scm) 전체 이전 (스키마+데이터).
pg_dump로 Supabase를 통째로 덤프받은 뒤 로컬로 복원한다.

비밀번호에 특수문자가 있으면 pg_dump/psql에 연결 URI를 통째로 넘길 때
Windows에서 인자 파싱 에러가 나므로(backup_daily.py에서 확인), host/port/
user/dbname을 분리하고 비밀번호는 PGPASSWORD 환경변수로 넘긴다.
"""
import os
import sys
import io
import subprocess
from pathlib import Path
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

PG_BIN = os.environ["PG_BIN"]
LOCAL_DB_URL = os.environ["LOCAL_DB_URL"]

# UPH 시스템의 .env에서 Supabase 접속정보를 그대로 가져온다 (같은 DB 공유)
UPH_ENV = ROOT.parent / "UPH 시스템" / ".env"
load_dotenv(UPH_ENV)
SUPABASE_URL = os.environ["DATABASE_URL"]

DUMP_PATH = ROOT / "supabase_dump.sql"


def conn_parts(url):
    u = urlparse(url)
    return {
        "host": u.hostname,
        "port": str(u.port or 5432),
        "user": u.username,
        "password": unquote(u.password) if u.password else "",
        "dbname": u.path.lstrip("/"),
    }


def run(cmd, env_extra, step_name):
    env = {**os.environ, **env_extra}
    print(f"[{step_name}] 실행 중...")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"[{step_name}] STDERR:\n{result.stderr}")
        raise RuntimeError(f"{step_name} 실패 (exit {result.returncode})")
    print(f"[{step_name}] 완료")
    return result


def main():
    src = conn_parts(SUPABASE_URL)
    dst = conn_parts(LOCAL_DB_URL)

    # ⚠️ Supabase 서버가 PostgreSQL 17.6이라 16.15 pg_dump로는 버전 불일치로
    # 거부됨(2026-09-17 확인) — 덤프는 별도 설치한 17 클라이언트로, 복원은
    # 기존 로컬 16 서버로 진행한다(구버전 서버로의 복원은 문제없음).
    pg_dump = r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
    psql = str(Path(PG_BIN) / "psql.exe")

    # Step 1: Supabase 덤프 (스키마+데이터, 소유권/권한 제외)
    run(
        [pg_dump, "-h", src["host"], "-p", src["port"], "-U", src["user"],
         "-d", src["dbname"], "--no-owner", "--no-privileges",
         "-f", str(DUMP_PATH)],
        {"PGPASSWORD": src["password"]},
        "1. Supabase 덤프",
    )
    size_mb = DUMP_PATH.stat().st_size / 1024 / 1024
    print(f"    덤프 파일 크기: {size_mb:.1f} MB")

    # Step 2: 로컬 DB로 복원
    run(
        [psql, "-h", dst["host"], "-p", dst["port"], "-U", dst["user"],
         "-d", dst["dbname"], "-f", str(DUMP_PATH)],
        {"PGPASSWORD": dst["password"]},
        "2. 로컬 DB 복원",
    )

    print("\n이전 완료. verify_migration.py로 행수 대조 검증을 실행하세요.")


if __name__ == "__main__":
    main()
