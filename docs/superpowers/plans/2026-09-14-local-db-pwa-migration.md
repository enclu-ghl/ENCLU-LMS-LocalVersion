# 로컬 DB 전환 + PWA 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supabase(UPH·주문파일정리·app.py) + 별도 원격 PostgreSQL(박스추천)을 이 PC의 로컬
PostgreSQL 하나로 통합하고, `app.py`를 Streamlit Community Cloud 대신 이 PC에서 직접 서빙 +
Tailscale 원격접속 + PWA(홈화면 설치)로 전환한다.

**Architecture:** 이 PC에 PostgreSQL을 설치해 단일 서버로 삼는다. 4개 프로그램 모두
`.env`의 `DATABASE_URL`만 로컬 연결 문자열로 바꾸면 코드 변경 없이 붙는다(표준 Postgres
SQL 호환). `app.py`는 이 PC에서 `streamlit run`으로 직접 띄우고, Tailscale로 폰·다른 PC가
포트포워딩 없이 안전하게 접속한다. PWA는 manifest+서비스워커를 얹어 홈화면 설치를 지원한다.

**Tech Stack:** PostgreSQL 16(Windows), Python/SQLAlchemy(기존 코드 재사용), `pg_dump`/`pg_restore`,
Streamlit, Tailscale, PWA(Web App Manifest + Service Worker)

**Spec:** `docs/superpowers/specs/2026-09-14-local-db-pwa-migration-design.md`

## 폴더 구조 (신규 — 기존 시스템은 그대로 둠)

기존 `통합시스템\`(운영 중, 건드리지 않음) 옆에 **새 폴더를 git clone으로 만들어서** 그
안에서 로컬 DB 전환 작업을 전부 진행한다. 검증 끝나고 전환할 준비가 되면, 그때 프로그램별로
"구 폴더 끄고 → 신 폴더 켜기"로 스위치한다.

```
개발 진행 중인 물류 프로그램\
├── 통합시스템\              ← 기존, 운영 중, 이번 작업 동안 안 건드림
└── 통합시스템_로컬DB\        ← 신규, git clone, 이번 계획의 작업 공간
    ├── (ENCLU-LMS-LocalVersion clone — UPH 시스템/주문파일정리/박스추천/허브런처)
    └── 웹으로 진행 중인 건\   ← (ENCLU-LMS clone — app.py)
```

이 문서의 모든 태스크에서 `통합시스템\...` 경로는 실제로는 **`통합시스템_로컬DB\...`**
기준이다 (Task 0에서 폴더를 만든 이후).

## Global Constraints

- 기존 `통합시스템\`은 전환 완료 전까지 절대 수정하지 않는다 — 모든 작업은
  `통합시스템_로컬DB\`에서 진행.
- **UPH 시스템(watchdog/매크로)은 병행 운영 금지** — WMS를 셀레니움으로 직접 조작하는
  크롤러라, 구·신 폴더를 동시에 띄우면 같은 WMS 세션/다운로드 폴더가 충돌한다. 전환은
  반드시 "구 폴더 프로세스 종료 → 신 폴더 프로세스 시작" 한 번의 스위치로만 한다. 그 전까지
  신 폴더 쪽은 라이브 크롤링 없이 DB 연결/저장 로직만 검증한다.
- 나머지 프로그램(`app.py`, 주문파일정리, 박스추천)은 DB만 읽고 쓰므로 구·신 폴더를 동시에
  띄워놓고 비교 테스트해도 안전하다.
- 실서비스 중단 없이 전환한다 — 문제 생기면 신 폴더 프로세스만 끄고 구 폴더로 그대로
  되돌리면 됨 (구 폴더가 안 건드려졌으므로 되돌리기가 항상 가능).
- DB 비밀번호 등 민감정보는 코드에 하드코딩하지 않는다 — `.env` + `python-dotenv` 패턴 유지.
- 로컬 PostgreSQL 비밀번호도 `.env`에 저장하고 `.gitignore` 대상 유지.
- 각 단계는 이전 단계가 검증 통과해야 다음으로 진행 (순서 건너뛰지 않음).
- git push는 매번 사용자 확인 후 (프로젝트 표준 규칙).

---

## Phase 1 — 새 폴더 준비 + 로컬 PostgreSQL 설치 + 백업 루틴 구축

### Task 0: 신 폴더 git clone

**Files:**
- Create: `C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템_로컬DB\` (신규 폴더)

**Interfaces:**
- Produces: 기존 두 GitHub 저장소의 최신 커밋이 그대로 들어있는 새 로컬 작업 폴더

- [ ] **Step 1: 상위 폴더로 이동 후 clone**

Run:
```powershell
cd "C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램"
git clone https://github.com/enclu-ghl/ENCLU-LMS-LocalVersion.git "통합시스템_로컬DB"
```

- [ ] **Step 2: app.py 저장소도 그 안에 같은 위치로 clone**

기존 구조(`통합시스템\웹으로 진행 중인 건\`)와 동일하게 맞춘다:
```powershell
cd "C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템_로컬DB"
git clone https://github.com/enclu-ghl/ENCLU-LMS.git "웹으로 진행 중인 건"
```

- [ ] **Step 3: 두 clone 모두 정상인지 확인**

Run:
```powershell
cd "C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템_로컬DB"
git status
cd "웹으로 진행 중인 건"
git status
```
Expected: 둘 다 `On branch main`, `nothing to commit, working tree clean`.

- [ ] **Step 4: 기존 `.env` 파일들 복사 (git-ignored라 clone에는 없음)**

각 프로그램 폴더(`UPH 시스템`, `주문파일정리 프로그램`, 박스추천프로그램, `웹으로 진행 중인 건`)의
`.env`를 기존 `통합시스템\`의 대응 폴더에서 신 폴더로 그대로 복사 (지금은 Supabase/원격
Postgres URL 그대로 — 이후 태스크에서 로컬 DB 정보 추가할 예정):
```powershell
Copy-Item "통합시스템\UPH 시스템\.env" "통합시스템_로컬DB\UPH 시스템\.env"
Copy-Item "통합시스템\주문파일정리 프로그램\.env" "통합시스템_로컬DB\주문파일정리 프로그램\.env"
Copy-Item "통합시스템\웹으로 진행 중인 건\.env" "통합시스템_로컬DB\웹으로 진행 중인 건\.env"
```
(박스추천프로그램의 `.env` 경로는 실행 직전에 실제 폴더 구조 확인 후 동일하게 복사)

이 시점부터 이 문서의 `통합시스템\...` 경로는 전부 `통합시스템_로컬DB\...` 기준이다.

---

### Task 1: PostgreSQL 설치 및 초기 설정

**Files:**
- Create: `C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\_local_db\README.md`
  (설치 정보, 접속 정보 요약 — 실제 비밀번호는 여기 안 적고 `.env` 참조하라고만 적음)

**Interfaces:**
- Produces: 로컬에서 접속 가능한 PostgreSQL 인스턴스, 기본 포트 `5432`, DB명 `enclu_scm`

- [ ] **Step 1: PostgreSQL 설치**

공식 설치본(postgresql.org, 16.x, Windows x64) 다운로드 후 설치.
- 설치 중 superuser(`postgres`) 비밀번호 설정 — 강력한 비밀번호 사용, 별도 메모장 등
  안전한 곳에 즉시 기록 (이 비밀번호는 절대 git에 커밋 안 함)
- 포트는 기본값 5432 유지
- "Stack Builder"는 설치 안 해도 됨

- [ ] **Step 2: 설치 확인**

Run (PowerShell, 설치 경로는 버전에 따라 다를 수 있음 — 실제 설치 로그의 bin 경로 확인):
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "SELECT version();"
```
Expected: PostgreSQL 버전 문자열 출력 (비밀번호 입력 프롬프트 뜨면 Step 1의 비밀번호 입력)

- [ ] **Step 3: 전용 DB + 전용 계정 생성**

Run:
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE enclu_scm;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE USER enclu_app WITH PASSWORD '여기에_강력한_비밀번호';"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE enclu_scm TO enclu_app;"
```
superuser(`postgres`) 계정을 앱에서 직접 쓰지 않고, 전용 계정(`enclu_app`)을 따로 만드는
이유: 나중에 실수로 DB를 통째로 지우는 명령을 앱 코드가 잘못 날려도 피해 범위를 줄이기 위함.

- [ ] **Step 4: 연결 문자열 기록**

`통합시스템\_local_db\README.md`에 아래 내용 작성 (비밀번호는 `<.env 참조>`로만 표기):
```markdown
# 로컬 PostgreSQL

- 호스트: localhost / 포트: 5432 / DB명: enclu_scm / 계정: enclu_app
- 연결 문자열 형태: postgresql://enclu_app:<.env 참조>@localhost:5432/enclu_scm
- 각 프로그램 .env의 DATABASE_URL_LOCAL 키에 실제 값 저장 (Task 6에서 전환 시 사용)
```

- [ ] **Step 5: Commit**

```bash
git add "통합시스템/_local_db/README.md"
git commit -m "docs: 로컬 PostgreSQL 설치 정보 기록"
```
(README만 커밋 — 비밀번호는 어디에도 커밋되지 않음)

---

### Task 2: 자동 일일 백업 스크립트

**Files:**
- Create: `C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\_local_db\backup_daily.py`
- Create: `C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\_local_db\.env` (git-ignored)

**Interfaces:**
- Consumes: Task 1에서 만든 `enclu_scm` DB
- Produces: `_local_db/backups/enclu_scm_YYYYMMDD.sql.gz` 매일 자동 생성, 오래된 백업 자동 정리

- [ ] **Step 1: `.env` 작성 (git-ignored)**

`통합시스템\_local_db\.env`:
```
LOCAL_DB_URL=postgresql://enclu_app:여기에_Task1_비밀번호@localhost:5432/enclu_scm
PG_BIN=C:\Program Files\PostgreSQL\16\bin
BACKUP_KEEP_DAYS=30
```

- [ ] **Step 2: `.gitignore`에 등록 확인**

Run:
```bash
grep -n "_local_db/.env" "C:/Users/enclu/Desktop/개발 진행 중인 물류 프로그램/통합시스템/.gitignore"
```
없으면 `.gitignore`에 `_local_db/.env`와 `_local_db/backups/` 두 줄 추가.

- [ ] **Step 3: 백업 스크립트 작성**

`통합시스템\_local_db\backup_daily.py`:
```python
# -*- coding: utf-8 -*-
"""로컬 PostgreSQL(enclu_scm) 일일 백업.
pg_dump로 압축 백업 생성 + 오래된 백업 자동 삭제.
Windows 작업 스케줄러에서 매일 새벽에 이 스크립트를 실행하도록 등록한다(Step 5).
"""
import os
import subprocess
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

PG_BIN = os.environ["PG_BIN"]
LOCAL_DB_URL = os.environ["LOCAL_DB_URL"]
KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "30"))
BACKUP_DIR = ROOT / "backups"
BACKUP_DIR.mkdir(exist_ok=True)


def run_backup():
    today = datetime.now().strftime("%Y%m%d")
    out_sql = BACKUP_DIR / f"enclu_scm_{today}.sql"
    out_gz = BACKUP_DIR / f"enclu_scm_{today}.sql.gz"

    pg_dump = str(Path(PG_BIN) / "pg_dump.exe")
    result = subprocess.run(
        [pg_dump, LOCAL_DB_URL, "-f", str(out_sql), "--no-owner", "--no-privileges"],
        capture_output=True, text=True,
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
```

- [ ] **Step 4: 수동 1회 실행해서 검증**

Run:
```powershell
cd "C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\_local_db"
& "C:\Users\enclu\AppData\Local\Python\pythoncore-3.14-64\python.exe" backup_daily.py
```
Expected: `[백업 완료] enclu_scm_20260914.sql.gz (N MB)` 출력, `backups/` 폴더에 파일 생성됨.
파일 크기가 0이거나 에러 나면 Task 1의 연결 문자열/비밀번호부터 재확인.

- [ ] **Step 5: Windows 작업 스케줄러 등록 (매일 새벽 3시)**

Run (관리자 권한 PowerShell):
```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\enclu\AppData\Local\Python\pythoncore-3.14-64\python.exe" `
    -Argument "backup_daily.py" `
    -WorkingDirectory "C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\_local_db"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "ENCLU_SCM_DB_Backup" -Action $action -Trigger $trigger -Description "로컬 PostgreSQL 일일 백업"
```

- [ ] **Step 6: 등록 확인**

Run:
```powershell
Get-ScheduledTask -TaskName "ENCLU_SCM_DB_Backup" | Select-Object TaskName, State
```
Expected: `State: Ready`

- [ ] **Step 7: Commit**

```bash
git add "통합시스템/_local_db/backup_daily.py" "통합시스템/.gitignore"
git commit -m "feat: 로컬 PostgreSQL 일일 자동 백업 스크립트 추가"
```

---

## Phase 2 — 스키마 + 데이터 이전

### Task 3: Supabase → 로컬 전체 이전

**Files:**
- Create: `C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\_local_db\migrate_from_supabase.py`

**Interfaces:**
- Consumes: 기존 `UPH 시스템\.env`의 `DATABASE_URL` (Supabase), Task 1의 `LOCAL_DB_URL`
- Produces: 로컬 `enclu_scm`에 Supabase와 동일한 스키마+데이터

- [ ] **Step 1: Supabase 전체 덤프 (pg_dump, 스키마+데이터)**

Run:
```powershell
$env:PGPASSWORD = "<Supabase 비밀번호 — UPH 시스템\.env의 DATABASE_URL에서 확인>"
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" `
    "postgresql://postgres.yfdxpcyegrtimldvyamd@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres" `
    --no-owner --no-privileges -f "통합시스템\_local_db\supabase_dump.sql"
```
Expected: `통합시스템\_local_db\supabase_dump.sql` 파일 생성 (수백 MB 가능 — 시간 걸릴 수 있음)

- [ ] **Step 2: 로컬 DB로 복원**

Run:
```powershell
$env:PGPASSWORD = "<Task 1에서 만든 enclu_app 비밀번호>"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" `
    -U enclu_app -h localhost -d enclu_scm -f "통합시스템\_local_db\supabase_dump.sql"
```
Expected: 에러 없이 완료 (권한 관련 경고 몇 줄은 무시 가능 — `--no-owner`로 이미 처리함)

- [ ] **Step 3: 행수 대조 검증 스크립트 작성**

`통합시스템\_local_db\verify_migration.py`:
```python
# -*- coding: utf-8 -*-
"""Supabase와 로컬 DB의 테이블별 행수를 대조해 이전이 정확한지 검증."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pathlib import Path

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / "UPH 시스템" / ".env")
SUPABASE_URL = os.environ["DATABASE_URL"]
load_dotenv(ROOT / ".env")
LOCAL_URL = os.environ["LOCAL_DB_URL"]

TABLES = [
    "order_status_log", "manpower_log", "uph_historical_summary",
    "sales_channel_dong_mapping", "alloc_session", "alloc_row",
    "alloc_dong_status", "alloc_picking_zone", "packaging_materials",
    "weight_calc_results", "inventory_master", "stock_count",
    "invalid_scan", "equipment_items", "supply_items",
    "fs_batch_codes", "fs_batch_usage_log", "amazon_url_map",
]

src = create_engine(SUPABASE_URL, connect_args={"connect_timeout": 15})
dst = create_engine(LOCAL_URL)

print(f"{'테이블':<30} {'Supabase':>12} {'로컬':>12} {'일치':>6}")
all_ok = True
for t in TABLES:
    try:
        with src.connect() as c:
            n_src = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
    except Exception as e:
        print(f"{t:<30} [Supabase 조회 실패: {e}]")
        continue
    try:
        with dst.connect() as c:
            n_dst = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
    except Exception as e:
        print(f"{t:<30} [로컬 조회 실패: {e}]")
        all_ok = False
        continue
    ok = "✅" if n_src == n_dst else "❌"
    if n_src != n_dst:
        all_ok = False
    print(f"{t:<30} {n_src:>12,} {n_dst:>12,} {ok:>6}")

print("\n전체 일치" if all_ok else "\n[경고] 불일치 테이블 있음 — 위 목록에서 ❌ 확인")
```

- [ ] **Step 4: 검증 실행**

Run:
```powershell
& "C:\Users\enclu\AppData\Local\Python\pythoncore-3.14-64\python.exe" "통합시스템\_local_db\verify_migration.py"
```
Expected: 모든 행에 ✅. ❌ 나오면 Step 2를 다시 실행하기 전에 원인부터 확인(로컬 DB를
`DROP DATABASE enclu_scm; CREATE DATABASE enclu_scm;`로 초기화 후 재시도).

- [ ] **Step 5: 박스추천프로그램의 원격 Postgres도 동일하게 이전**

Step 1~4를 박스추천프로그램의 `.env`에 있는 `DATABASE_URL`(별도 원격 PostgreSQL) 기준으로
반복. 덤프 파일명은 `boxrec_dump.sql`로 구분. 박스추천프로그램의 테이블은 Supabase와
스키마가 겹치지 않으므로(별도 서버였음) 같은 `enclu_scm` DB에 그대로 복원 가능 — 복원 전
`psql -U enclu_app -h localhost -d enclu_scm -c "\dt"`로 기존 테이블명과 충돌 없는지 먼저 확인.

- [ ] **Step 6: Commit**

```bash
git add "통합시스템/_local_db/verify_migration.py"
git commit -m "feat: Supabase/원격Postgres -> 로컬 DB 이전 검증 스크립트"
```
(`supabase_dump.sql`, `boxrec_dump.sql`은 대용량 데이터 백업 파일이라 커밋하지 않음 —
`_local_db/*.sql`을 `.gitignore`에 추가해뒀는지 확인)

---

## Phase 3 — 프로그램별 순차 전환

### Task 4: UPH 시스템 전환 (구 폴더 종료 → 신 폴더 시작, 단발 스위치)

**Files:**
- Modify: `통합시스템_로컬DB\UPH 시스템\.env`

**Interfaces:**
- Consumes: Task 3에서 검증된 로컬 DB
- Produces: 신 폴더의 `watchdog_agent.py`, `uph_download_macro.py`가 로컬 DB로 정상 동작,
  구 폴더 프로세스는 완전히 정지됨

⚠️ Global Constraints에 적힌 대로 **이 태스크는 병행 운영 없이 한 번에 스위치**한다.
사전 준비(Step 1)는 구 폴더가 계속 돌아가는 상태에서 해도 되지만, Step 3(실제 스위치)는
반드시 사용자에게 지금 진행해도 되는 타이밍인지 확인 후 실행한다 — 출고 작업 중이면
잠깐이라도 데이터 수집이 끊기므로.

- [ ] **Step 1: 신 폴더 `.env`에 로컬 DB 연결 정보 추가 (구 폴더는 안 건드림)**

`통합시스템_로컬DB\UPH 시스템\.env`에서 `DATABASE_URL` 줄을 로컬 DB로 교체:
```
DATABASE_URL=postgresql://enclu_app:<Task1 비밀번호>@localhost:5432/enclu_scm
```
(이 시점에 구 폴더 `통합시스템\UPH 시스템\.env`는 여전히 Supabase를 그대로 가리키고
있고, 구 폴더 프로세스도 계속 돌아가는 중이어야 정상)

- [ ] **Step 2: 신 폴더 쪽 무중단 드라이런 (라이브 크롤링 없이 DB 연결만 확인)**

```powershell
& "C:\Users\enclu\AppData\Local\Python\pythoncore-3.14-64\python.exe" -c "
import os
from dotenv import load_dotenv
load_dotenv(r'통합시스템_로컬DB\UPH 시스템\.env')
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    print(conn.execute(text('SELECT COUNT(*) FROM order_status_log')).scalar())
"
```
Expected: Task 3에서 확인한 것과 같은 행수 출력 (신 폴더 코드가 로컬 DB를 정상적으로
읽을 수 있음을 확인 — 아직 watchdog는 실행 안 함).

- [ ] **Step 3: (사용자 확인 후) 실제 스위치 — 구 폴더 종료, 신 폴더 시작**

**지금 진행해도 되는지 먼저 확인받는다.** 확인되면:
1. 구 폴더의 UPH 자동 제어판에서 `watchdog_agent.py`와 `uph_download_macro.py` 둘 다 종료
2. 신 폴더(`통합시스템_로컬DB\UPH 시스템\`)에서 `uph_control_panel.py` 실행,
   두 프로세스 시작

- [ ] **Step 4: 정상 동작 확인**

```powershell
Get-Content "통합시스템_로컬DB\UPH 시스템\uph_agent.log" -Tail 20
```
Expected: 연결 에러 없이 정상 폴링 로그. 몇 분 뒤 로컬 DB에서 새 라운드가 실제 반영됐는지:
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U enclu_app -h localhost -d enclu_scm `
    -c "SELECT COUNT(*), MAX(detected_at) FROM order_status_log;"
```
행수가 Step 2 때보다 늘어나 있으면 정상.

- [ ] **Step 5: 문제 생기면 즉시 롤백**

신 폴더 쪽에서 에러 나거나 이상하면: 신 폴더 프로세스 종료 → 구 폴더 `uph_control_panel.py`로
그대로 재시작 (구 폴더는 한 번도 안 건드렸으므로 즉시 원상복구됨).

- [ ] **Step 6: Commit**

```bash
cd "통합시스템_로컬DB"
git status  # .env는 git-ignored라 여기 안 걸리는지 확인
git commit --allow-empty -m "chore: UPH 시스템 로컬 DB로 스위치 완료 ($(Get-Date -Format yyyy-MM-dd))"
```

---

### Task 5: 주문파일정리 프로그램 전환

이 프로그램은 DB만 읽고 쓰므로(WMS 직접 조작 없음) 구 폴더가 계속 돌아가는 상태에서
신 폴더 쪽을 독립적으로 켜서 테스트해도 안전하다 — Task 4처럼 "정지 후 스위치"할 필요 없음.

**Files:**
- Modify: `통합시스템_로컬DB\주문파일정리 프로그램\.env`

- [ ] **Step 1: 신 폴더 `.env`의 `DATABASE_URL`을 로컬로 교체**

```
DATABASE_URL=postgresql://enclu_app:<Task1 비밀번호>@localhost:5432/enclu_scm
```
(구 폴더 `통합시스템\주문파일정리 프로그램\.env`는 그대로 Supabase — 안 건드림)

- [ ] **Step 2: 신 폴더의 `file_splitter_gui.py` 실행 후 정상 조회되는지 확인**

`통합시스템_로컬DB\주문파일정리 프로그램\file_splitter_gui.py` 실행 → "일괄 관리" 탭에서
목록이 뜨는지, "선택 수정"이 정상 동작하는지(선택 유지 기능 포함) 확인.

- [ ] **Step 3: Commit**

```bash
cd "통합시스템_로컬DB"
git commit --allow-empty -m "chore: 주문파일정리 프로그램 로컬 DB 연결 확인 완료"
```

---

### Task 6: 박스추천프로그램 전환

이 프로그램도 DB만 읽고 쓰므로 Task 5와 같은 패턴 — 구 폴더는 안 건드리고 신 폴더에서
독립적으로 진행한다.

⚠️ **사전 확인 필요**: 박스추천프로그램의 정확한 `.env` 경로는 이번 계획 작성 시점에
확인하지 못했다 — 이 태스크 시작 전에 `통합시스템_로컬DB\` 안에서 해당 폴더를 찾아
`.env` 위치를 먼저 확인한다 (`Get-ChildItem -Recurse -Filter .env` 등으로 검색).

**Files:**
- Modify: 박스추천프로그램의 `.env` (신 폴더 기준, 정확한 경로는 Step 1에서 확인)

- [ ] **Step 1: 박스추천프로그램 폴더 및 `.env` 경로 확인**

```powershell
Get-ChildItem "통합시스템_로컬DB" -Recurse -Filter ".env" | Select-Object FullName
```

- [ ] **Step 2: 찾은 `.env`의 `DATABASE_URL`을 로컬로 교체** (Task 5 Step 1과 같은 값)
- [ ] **Step 3: 프로그램 실행 후 정상 동작 확인** — 박스 추천 계산 1건 실행해서 결과 나오는지 확인
- [ ] **Step 4: Commit** (Task 5 Step 3과 동일한 패턴)

---

## Phase 4 — `app.py` 로컬 서빙 전환

### Task 7: Streamlit 로컬 실행 전환

**Files:**
- Modify: `통합시스템\웹으로 진행 중인 건\.env`
- Create: `통합시스템\웹으로 진행 중인 건\start_local_server.bat`

**Interfaces:**
- Consumes: Task 3의 로컬 DB, Task 4~6에서 검증된 `.env` 전환 패턴
- Produces: 사내망에서 `http://<이 PC의 LAN IP>:8501`로 접속 가능한 `app.py`

- [ ] **Step 1: `.env` 백업 후 로컬 DB로 교체** (Task 4와 동일 패턴)

- [ ] **Step 2: 로컬 실행용 배치파일 작성**

`통합시스템\웹으로 진행 중인 건\start_local_server.bat`:
```bat
@echo off
chcp 65001 > nul
cd /d "%~dp0"
"C:\Users\enclu\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m streamlit run app.py ^
    --server.port 8501 ^
    --server.address 0.0.0.0 ^
    --server.headless true
pause
```
`--server.address 0.0.0.0`이 핵심 — 이게 있어야 localhost 말고 사내망의 다른 기기에서도
이 PC의 IP로 접속 가능해짐.

- [ ] **Step 3: 로컬 실행 및 접속 확인**

Run: `통합시스템\웹으로 진행 중인 건\start_local_server.bat` 더블클릭 실행

이 PC 브라우저에서:
```
http://localhost:8501
```
Expected: 허브 화면 정상 로딩, DB 용량 배너에 "저장 용량 XXX MB" 정상 표시(로컬 DB 값).

- [ ] **Step 4: 같은 와이파이의 다른 기기(폰)에서 접속 테스트**

이 PC의 LAN IP 확인:
```powershell
ipconfig | findstr IPv4
```
폰 브라우저(같은 와이파이)에서 `http://<위에서 확인한 IP>:8501` 접속.
Expected: 정상 로딩됨. 안 되면 Windows 방화벽에서 포트 8501 인바운드 허용 필요:
```powershell
New-NetFirewallRule -DisplayName "Streamlit Local 8501" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow
```

- [ ] **Step 5: 시작 프로그램 등록 (PC 재부팅 시 자동 실행)**

Win+R → `shell:startup` → 해당 폴더에 `start_local_server.bat`의 바로가기 생성.

- [ ] **Step 6: Commit**

```bash
git add "웹으로 진행 중인 건/start_local_server.bat"
git commit -m "feat: app.py 로컬 서빙용 실행 스크립트 추가"
```
(이 커밋은 `ENCLU-LMS` 저장소 — `웹으로 진행 중인 건` 폴더 안에서 별도로 git 명령 실행해야 함)

---

## Phase 5 — Tailscale 원격 접속

### Task 8: Tailscale 설치 및 설정

**Files:** 없음 (인프라 설정 작업)

- [ ] **Step 1: 서버 PC에 Tailscale 설치**

tailscale.com에서 Windows용 설치, 계정으로 로그인(개인 계정 또는 팀 계정).

- [ ] **Step 2: Tailscale IP 확인**

Run:
```powershell
tailscale ip -4
```
Expected: `100.x.x.x` 형태의 IP 출력 — 이게 외부에서 이 PC에 접속할 때 쓸 주소.

- [ ] **Step 3: 폰에 Tailscale 앱 설치, 같은 계정으로 로그인**

App Store/Play Store에서 "Tailscale" 설치 → 로그인 → 서버 PC와 같은 tailnet에 연결됨 확인
(Tailscale 앱 안에서 서버 PC 이름이 목록에 뜨는지 확인).

- [ ] **Step 4: 외부망(와이파이 끄고 데이터망)에서 접속 테스트**

폰에서 와이파이 끄고 데이터망으로 전환 → Tailscale 앱 켜진 상태로 브라우저에서
`http://<Task 2의 Tailscale IP>:8501` 접속.
Expected: 사내망 밖인데도 정상 로딩됨.

- [ ] **Step 5: 다른 PC도 동일하게 Tailscale 설치·연결**

---

## Phase 6 — PWA 레이어

### Task 9: Web App Manifest + 아이콘

**Files:**
- Create: `통합시스템\웹으로 진행 중인 건\static\manifest.json`
- Create: `통합시스템\웹으로 진행 중인 건\static\icon-192.png`
- Create: `통합시스템\웹으로 진행 중인 건\static\icon-512.png`
- Modify: `통합시스템\웹으로 진행 중인 건\app.py`

**Interfaces:**
- Produces: 브라우저가 "홈 화면에 추가"를 인식하는 PWA 매니페스트

- [ ] **Step 1: 아이콘 2개 준비**

기존 로고/아이콘 파일이 있으면 192x192, 512x512 PNG로 리사이즈해서
`통합시스템\웹으로 진행 중인 건\static\` 아래 저장. 없으면 간단한 정사각 로고 이미지 준비.

- [ ] **Step 2: manifest.json 작성**

`통합시스템\웹으로 진행 중인 건\static\manifest.json`:
```json
{
  "name": "ENCLU SCM 시스템",
  "short_name": "ENCLU SCM",
  "start_url": ".",
  "display": "standalone",
  "background_color": "#0f1117",
  "theme_color": "#4a90e2",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 3: Streamlit 정적 파일 서빙 활성화**

Streamlit은 기본적으로 `static/` 폴더 서빙이 꺼져있다 — 설정 파일로 명시적으로 켜야 한다.

`통합시스템\웹으로 진행 중인 건\.streamlit\config.toml` 파일이 없으면 새로 생성,
있으면 아래 섹션을 추가:
```toml
[server]
enableStaticServing = true
address = "0.0.0.0"
port = 8501
```
(`address`/`port`를 여기 넣으면 Task 7의 배치파일 `--server.address`/`--server.port`
옵션은 생략 가능 — 둘 다 있어도 무방하며 command-line 값이 우선 적용된다)

이렇게 하면 `static/manifest.json`이 `http://<서버>:8501/app/static/manifest.json`
경로로 서빙된다 — 별도 서버 코드는 필요 없다.

- [ ] **Step 4: `<head>`에 manifest 링크 + 커스텀 HTML 삽입**

`app.py`의 맨 처음 `st.set_page_config(...)` 호출 직후에 추가:
```python
st.markdown("""
<link rel="manifest" href="./app/static/manifest.json">
<meta name="theme-color" content="#4a90e2">
<link rel="apple-touch-icon" href="./app/static/icon-192.png">
""", unsafe_allow_html=True)
```

- [ ] **Step 5: 브라우저에서 manifest 인식 확인**

로컬 서버 실행 중 상태에서 브라우저 개발자도구 → Application 탭 → Manifest 항목 확인.
Expected: 이름/아이콘이 정상 표시됨, 에러 없음.
안드로이드 Chrome에서는 자동으로 "앱 설치" 배너가 뜨는지 확인.
iOS Safari는 수동으로 공유 버튼 → "홈 화면에 추가"로 테스트.

- [ ] **Step 6: Commit**

```bash
git add "웹으로 진행 중인 건/static/" "웹으로 진행 중인 건/app.py"
git commit -m "feat: PWA manifest 추가 (홈화면 설치 지원)"
```

---

## Phase 7 — 병행 운영 및 정리

### Task 10: 병행 운영 체크리스트 + Supabase 해지

**Files:**
- Create: `통합시스템\_local_db\cutover_checklist.md`

- [ ] **Step 1: 체크리스트 작성**

`통합시스템\_local_db\cutover_checklist.md`:
```markdown
# 로컬 DB 전환 후 병행 운영 체크리스트

전환일: ____
최소 2주간 아래 항목 매일 확인:

- [ ] 로컬 DB 백업이 `_local_db/backups/`에 매일 생성되는지
- [ ] UPH watchdog 로그에 연결 에러 없는지
- [ ] app.py가 재부팅 후에도 자동으로 다시 떠 있는지 (Task 7 Step 5 확인)
- [ ] Tailscale 외부 접속이 계속 되는지
- [ ] 이 PC가 예기치 않게 재부팅/절전 모드로 안 빠지는지 (전원 설정에서 절전 끄기 확인)

2주간 문제 없으면:
- [ ] Supabase 프로젝트 백업(최종 pg_dump) 1회 더 받아서 별도 보관 후 프로젝트 삭제/해지
- [ ] 박스추천프로그램의 원격 PostgreSQL 서버도 동일하게 최종 백업 후 해지
```

- [ ] **Step 2: Windows 전원 설정에서 절전모드 비활성화**

Run:
```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
```
(서버 역할을 하는 PC가 절전모드로 빠지면 전체 시스템이 멈추므로 필수)

- [ ] **Step 3: Commit**

```bash
git add "통합시스템/_local_db/cutover_checklist.md"
git commit -m "docs: 병행 운영 체크리스트 추가"
```

- [ ] **Step 4: (2주 후, 별도 승인 받고 진행) Supabase/원격 Postgres 해지**

이 단계는 반드시 사용자에게 실행 시점에 다시 확인받고 진행한다 — 되돌릴 수 없는 작업.
