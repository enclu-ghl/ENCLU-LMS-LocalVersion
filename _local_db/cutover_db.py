# -*- coding: utf-8 -*-
"""Supabase(public) -> 새 DB(enclu_scm_next) 구축 후 enclu_scm과 교체하는 전환 스크립트.

  --dry-run   교체 직전(검증)까지만 하고 기존 enclu_scm은 건드리지 않는다.
  --rename    검증이 통과하면 기존 enclu_scm을 enclu_scm_pre_<날짜>로 보관하고 새 DB를 enclu_scm으로 교체한다.
              (이 DB에 붙은 모든 프로그램/백업이 끊긴 상태여야 한다 — 접속은 스크립트가 종료시킨다)

접속정보: 로컬은 _local_db/.env(LOCAL_DB_URL), Supabase는 구 폴더 UPH .env 또는 SUPABASE_URL,
postgres 관리자 비밀번호는 환경변수 POSTGRES_PASSWORD (파일에 저장하지 않는다).
"""
import argparse
import io
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import dotenv_values, load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PG16 = Path(os.environ["PG_BIN"])
PG17_DUMP = r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
OLD_UPH_ENV = ROOT.parent.parent / "통합시스템" / "UPH 시스템" / ".env"

LIVE_DB, NEXT_DB = "enclu_scm", "enclu_scm_next"
BOX_TABLES = ["box_combinations", "products"]
DUMP, BOX_DUMP = ROOT / "next_dump.sql", ROOT / "box_dump.sql"


def parts(url):
    u = urlparse(url)
    return {"host": u.hostname, "port": str(u.port or 5432), "user": u.username,
            "password": unquote(u.password or ""), "dbname": u.path.lstrip("/")}


SUPA_URL = os.environ.get("SUPABASE_URL") or dotenv_values(OLD_UPH_ENV).get("DATABASE_URL")
if not SUPA_URL or "supabase" not in SUPA_URL:
    sys.exit("Supabase 접속정보를 찾지 못했습니다 (구 폴더 UPH .env 또는 SUPABASE_URL)")
SUPA, LOC = parts(SUPA_URL), parts(os.environ["LOCAL_DB_URL"])
ADMIN_PW = os.environ.get("POSTGRES_PASSWORD")
if not ADMIN_PW:
    sys.exit("환경변수 POSTGRES_PASSWORD(postgres 관리자 비밀번호)를 지정하세요")


def run(cmd, pw, name):
    t = time.time()
    print(f"[{name}] ...")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PGPASSWORD": pw})
    if r.returncode != 0:
        print(r.stderr[-1500:])
        sys.exit(f"[{name}] 실패 (rc={r.returncode}) — 중단")
    print(f"[{name}] 완료 {time.time() - t:.0f}s")


def psql(db, user, pw, args, name):
    run([str(PG16 / "psql.exe"), "-h", LOC["host"], "-p", LOC["port"], "-U", user, "-d", db,
         "-v", "ON_ERROR_STOP=1", "-q", *args], pw, name)


def admin(sql, name):
    psql("postgres", "postgres", ADMIN_PW, ["-c", sql], name)


def strip_dump(path):
    drop = re.compile(r"^(SET transaction_timeout|CREATE SCHEMA public;)")
    tmp = path.with_suffix(".tmp")
    with open(path, encoding="utf-8") as src, open(tmp, "w", encoding="utf-8") as dst:
        for line in src:
            if not drop.match(line):
                dst.write(line)
    tmp.replace(path)


def engine(p):
    return create_engine(URL.create("postgresql+psycopg2", username=p["user"], password=p["password"],
                                    host=p["host"], port=int(p["port"]), database=p["dbname"]))


def counts(eng, tables):
    out = {}
    with eng.connect() as c:
        for t in tables:
            out[t] = c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rename", action="store_true")
    a = ap.parse_args()
    if a.dry_run == a.rename:
        sys.exit("--dry-run 또는 --rename 중 하나만 지정하세요")
    t0 = time.time()

    admin(f"DROP DATABASE IF EXISTS {NEXT_DB}", "1. 기존 임시 DB 정리")
    admin(f"CREATE DATABASE {NEXT_DB} OWNER {LOC['user']} ENCODING 'UTF8'", "2. 새 DB 생성")

    run([PG17_DUMP, "-h", SUPA["host"], "-p", SUPA["port"], "-U", SUPA["user"], "-d", SUPA["dbname"],
         "-n", "public", "--no-owner", "--no-privileges", "-f", str(DUMP)], SUPA["password"], "3. Supabase 덤프")
    strip_dump(DUMP)
    psql(NEXT_DB, LOC["user"], LOC["password"], ["-f", str(DUMP)], "4. 새 DB로 복원")

    run([str(PG16 / "pg_dump.exe"), "-h", LOC["host"], "-p", LOC["port"], "-U", LOC["user"], "-d", LIVE_DB,
         *[x for t in BOX_TABLES for x in ("-t", t)], "--no-owner", "--no-privileges", "-f", str(BOX_DUMP)],
        LOC["password"], "5. 박스추천 테이블 덤프(기존 로컬)")
    psql(NEXT_DB, LOC["user"], LOC["password"], ["-f", str(BOX_DUMP)], "6. 박스추천 테이블 복원")

    print("[7. 행수 검증]")
    se = engine(SUPA)
    with se.connect() as c:
        tables = [r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")).fetchall()]
    nxt = engine({**LOC, "dbname": NEXT_DB})
    live = engine({**LOC, "dbname": LIVE_DB})
    cs, cn = counts(se, tables), counts(nxt, tables)
    bad = [t for t in tables if cs[t] != cn[t]]
    for t in tables:
        print(f"  {t:<30}{cs[t]:>10,}{cn[t]:>10,}  {'OK' if cs[t] == cn[t] else '!! 불일치'}")
    cb_old, cb_new = counts(live, BOX_TABLES), counts(nxt, BOX_TABLES)
    for t in BOX_TABLES:
        print(f"  {t:<30}{cb_old[t]:>10,}{cb_new[t]:>10,}  {'OK' if cb_old[t] == cb_new[t] else '!! 불일치'}")
        if cb_old[t] != cb_new[t]:
            bad.append(t)

    if bad:
        msg = f"불일치: {bad}"
        if a.rename:
            sys.exit(msg + " — 교체하지 않고 중단 (Supabase에 아직 쓰는 프로그램이 있는지 확인)")
        print(msg + " (dry-run: 라이브 데이터라 약간의 차이는 정상일 수 있음)")

    if a.dry_run:
        print(f"\n[dry-run 종료] 총 {time.time() - t0:.0f}s — 기존 {LIVE_DB}는 그대로입니다.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    kill = ("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname IN ('{a}','{b}') AND pid <> pg_backend_pid()").format(a=LIVE_DB, b=NEXT_DB)
    admin(kill, "8. 두 DB의 기존 접속 종료")
    admin(f"ALTER DATABASE {LIVE_DB} RENAME TO {LIVE_DB}_pre_{stamp}", "9. 기존 DB 보관용으로 이름 변경")
    admin(f"ALTER DATABASE {NEXT_DB} RENAME TO {LIVE_DB}", "10. 새 DB를 운영 이름으로 교체")
    print(f"\n[전환 완료] 총 {time.time() - t0:.0f}s — 이전 DB는 {LIVE_DB}_pre_{stamp} 로 보관 중입니다.")


if __name__ == "__main__":
    main()
