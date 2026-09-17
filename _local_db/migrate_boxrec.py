# -*- coding: utf-8 -*-
"""박스추천프로그램의 별도 원격 PostgreSQL(18.4) -> 로컬 enclu_scm 이전.

원격 서버가 PostgreSQL 18이라 18 클라이언트로 덤프해야 한다(2026-09-17 확인:
16 클라이언트는 17 서버도 거부했음). 비밀번호에 특수문자(@ 등)가 있어
URI를 통째로 조립하면 깨지므로, host/port/user/dbname을 분리해서 넘긴다.
"""
import os
import sys
import io
import subprocess
from pathlib import Path
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PG_BIN = os.environ["PG_BIN"]  # 로컬(복원 대상) 16 서버 bin

BOXREC_ENV = ROOT.parent / "박스추천프로그램" / ".env"
load_dotenv(BOXREC_ENV, override=True)
SRC = {
    "host": os.environ["DB_HOST"],
    "port": os.environ.get("DB_PORT", "5432"),
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "dbname": os.environ["DB_NAME"],
}

from urllib.parse import urlparse, unquote
_dst_url = urlparse(os.environ["LOCAL_DB_URL"])  # 위 override로 덮이기 전에 읽었어야 하나,
# LOCAL_DB_URL은 override=True 이후에도 .env에 재정의가 없으므로 최초 load_dotenv(ROOT/".env") 값 유지됨.
DST = {
    "host": _dst_url.hostname, "port": str(_dst_url.port or 5432),
    "user": _dst_url.username, "password": unquote(_dst_url.password or ""),
    "dbname": _dst_url.path.lstrip("/"),
}

DUMP_PATH = ROOT / "boxrec_dump.sql"


def run(cmd, env_extra, step_name):
    env = {**os.environ, **env_extra}
    print(f"[{step_name}] 실행 중...")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(f"[{step_name}] STDERR:\n{result.stderr}")
        raise RuntimeError(f"{step_name} 실패 (exit {result.returncode})")
    print(f"[{step_name}] 완료")
    return result


def main():
    pg_dump18 = r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
    psql16 = str(Path(PG_BIN) / "psql.exe")

    run(
        [pg_dump18, "-h", SRC["host"], "-p", SRC["port"], "-U", SRC["user"],
         "-d", SRC["dbname"], "--no-owner", "--no-privileges",
         "-f", str(DUMP_PATH)],
        {"PGPASSWORD": SRC["password"]},
        "1. 박스추천 원격DB 덤프",
    )
    print(f"    덤프 파일 크기: {DUMP_PATH.stat().st_size / 1024:.1f} KB")

    run(
        [psql16, "-h", DST["host"], "-p", DST["port"], "-U", DST["user"],
         "-d", DST["dbname"], "-f", str(DUMP_PATH)],
        {"PGPASSWORD": DST["password"]},
        "2. 로컬 DB 복원",
    )
    print("\n이전 완료.")


if __name__ == "__main__":
    main()
