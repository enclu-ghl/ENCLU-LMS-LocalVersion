# -*- coding: utf-8 -*-
"""로컬 PostgreSQL(enclu_scm) 일일 백업.
pg_dump로 압축 백업 생성 + 오래된 백업 자동 삭제.
Windows 작업 스케줄러에서 매일 새벽에 이 스크립트를 실행하도록 등록한다.
"""
import os
import subprocess
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

PG_BIN = os.environ["PG_BIN"]
LOCAL_DB_URL = os.environ["LOCAL_DB_URL"]
KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "30"))
# 백업은 DB가 있는 C:와 다른 물리 디스크(E:)에 두는 걸 권장 — .env의 BACKUP_DIR로 지정, 없으면 기존 위치
BACKUP_DIR = Path(os.getenv("BACKUP_DIR") or (ROOT / "backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ⚠️ pg_dump에 URI를 통째로 넘기면 비밀번호에 '!' 같은 특수문자가 있을 때
# Windows에서 "너무 많은 명령행 인자" 에러가 남(2026-09-17 확인). host/port/user/dbname을
# 각각 분리하고 비밀번호는 PGPASSWORD 환경변수로 넘기면 이 문제가 없다.
_u = urlparse(LOCAL_DB_URL)
PG_HOST = _u.hostname
PG_PORT = str(_u.port or 5432)
PG_USER = _u.username
PG_PASSWORD = unquote(_u.password) if _u.password else ""
PG_DBNAME = _u.path.lstrip("/")


def run_backup():
    today = datetime.now().strftime("%Y%m%d")
    out_sql = BACKUP_DIR / f"enclu_scm_{today}.sql"
    out_gz = BACKUP_DIR / f"enclu_scm_{today}.sql.gz"

    pg_dump = str(Path(PG_BIN) / "pg_dump.exe")
    env = {**os.environ, "PGPASSWORD": PG_PASSWORD}
    result = subprocess.run(
        [pg_dump, "-h", PG_HOST, "-p", PG_PORT, "-U", PG_USER, "-d", PG_DBNAME,
         "-f", str(out_sql), "--no-owner", "--no-privileges"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump 실패: {result.stderr}")

    with open(out_sql, "rb") as f_in, gzip.open(out_gz, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    out_sql.unlink()

    size_mb = out_gz.stat().st_size / 1024 / 1024
    print(f"[백업 완료] {out_gz.name} ({size_mb:.1f} MB)")


def cleanup_old_backups():
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    removed = 0
    for f in BACKUP_DIR.glob("enclu_scm_*.sql.gz"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            removed += 1
    if removed:
        print(f"[정리] {KEEP_DAYS}일 지난 백업 {removed}개 삭제")


if __name__ == "__main__":
    run_backup()
    cleanup_old_backups()
