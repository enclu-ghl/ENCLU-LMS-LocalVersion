---
name: enclu-scm-project-guide
description: ENCLU SCM 물류통합시스템(허브 런처, UPH 시스템, 박스추천, 주문파일정리, 자동매칭, 웹앱 app.py) 작업 매뉴얼. 이 저장소의 파일을 읽거나 수정하기 전, 특히 git commit/push, 어느 저장소에 반영할지 헷갈릴 때, DB(로컬 PostgreSQL) 관련 버그를 조사할 때, UPH 대시보드 숫자가 이상할 때, .env·비밀번호 등 민감정보를 다룰 때 먼저 확인할 것. "통합시스템", "ENCLU", "UPH", "박스추천", "물류통합시스템", "현황판" 등이 언급되면 적극적으로 트리거해야 함.
---

# ENCLU SCM 물류통합시스템 작업 매뉴얼

공통 규칙(역할 분담·상호 검증·안전)은 `docs/AX_RULES.md`, 현재 상태는 `docs/HANDOFF.md`가 기준이다.
이 문서는 저장소 구조와 과거 버그에서 얻은 진단 지식을 담는다.

## 저장소 지도

한 폴더 안에 **서로 무관한 GitHub 저장소 두 개**가 겹쳐 있다. 한쪽에 커밋해도 다른 쪽에 반영되지 않는다.

| 로컬 폴더 | GitHub 저장소 | 내용 |
|---|---|---|
| `통합시스템_로컬DB\` (루트) | `enclu-ghl/ENCLU-LMS-LocalVersion` (**공개**) | 허브 런처(`ENCLU-SCM-ALL-SYSTEM.py`, `hub/`), UPH 시스템, 박스추천, 주문파일정리, 자동 매칭, `_local_db/`(백업·전환 도구), AX 문서 |
| `통합시스템_로컬DB\웹으로 진행 중인 건\` | `enclu-ghl/ENCLU-LMS` | 웹앱 `app.py`(재고조사·무게구간·UPH 현황판·소모품·재고 할당). 루트 저장소의 `.gitignore` 대상 |

- 수정 전 해당 폴더에서 `git remote -v`로 저장소를 확인한다 (예: `watchdog_agent.py` → LocalVersion, `app.py` → ENCLU-LMS).
- 구 폴더 `개발 진행 중인 물류 프로그램\통합시스템\`은 전환 이전 버전(롤백용)이다. 새 작업은 하지 않는다.
- 같은 내용의 Codex용 사본이 `.agents/skills/enclu-scm-project-guide/SKILL.md`에 있다 — 고칠 때 둘 다 맞춘다.

## 운영 구성 (2026-10 기준)

- **DB: 서버 PC의 로컬 PostgreSQL 16, DB `enclu_scm` 하나로 통합.** UPH·재고 할당·주문파일정리(`fs_*` 테이블)·박스추천(`box_combinations`, `products`)이 모두 여기 있다.
  - 같은 PC에 PostgreSQL 17·18 서비스도 있다 — 전환 당시 덤프 도구 버전 때문에 의도적으로 설치한 것. 운영 DB는 16.
  - 다른 PC는 프로그램별 최소권한 계정으로 사내망·Tailscale에서만 접속한다. 계정·주소는 저장소 밖 관리자 문서에만 있다.
- **웹앱:** 서버 PC에서 Streamlit 로컬 서빙(포트 8501, 예약작업으로 자동 실행). 직원은 사내망/Tailscale 주소로 접속.
  허브의 웹 카드 주소는 `config.json`의 `web_base_url` 또는 환경변수 `ENCLU_WEB_BASE_URL`.
- **백업:** `_local_db/backup_daily.py`, 매일 03:00 예약작업, 저장 위치는 `.env`의 `BACKUP_DIR`(C:와 다른 디스크).
- **릴리스:** 허브 exe는 GitHub Actions가 빌드해 Releases로 배포(`ENCLU_SCM.spec`, `version.txt`).

## git 작업 원칙

- 로컬 파일 수정은 바로 진행한다. **commit/push는 매번 사용자에게 먼저 확인한다.**
- push 전에 `git status`로 올라갈 파일을 확인한다. `.env`, `credentials.dat`, `config.json`, `venv/`, `__pycache__`, 로그(`*.log`)·캐시DB(`*.sqlite3`), 실제 업무 데이터(`UPH 시스템\Download the Uph file\*`), DB 덤프(`_local_db/*.sql`, `_local_db/backups/`), DB 서버 설정(`pg_hba.conf`, `postgresql.conf`)은 커밋하면 안 된다 — `.gitignore`에 있지만 새 파일·폴더를 추가할 때 같은 기준으로 점검한다.
- 원격이 앞서 있으면 강제로 덮어쓰지 않는다. `git fetch` → 변경 확인 → `git pull --no-edit`로 합친 뒤 push.

## 비밀정보 원칙 (공개 저장소)

- 접속정보(호스트·계정·비밀번호)·IP·DB 접속 URL을 코드나 문서에 쓰지 않는다. CI의 비밀 유출 검사가 `계정:비밀번호@` 형태의 연결 문자열을 막는다(문서 예시 포함).
- 각 프로그램은 `python-dotenv`로 폴더별 `.env`를 읽는다: UPH·주문파일정리는 `DATABASE_URL`, 박스추천은 `DB_HOST`·`DB_PORT`·`DB_NAME`·`DB_USER`·`DB_PASSWORD`.
- 허브(exe)는 각 PC에서 최초 1회 접속정보를 입력받아 DPAPI로 암호화해 `credentials.dat`에 저장한다(`hub/secrets.py`).
- 과거 `박스추천프로그램\main.py`에 운영 비밀번호가 `os.getenv()` 기본값으로 박혀 있던 사고가 있었다. 커밋 전 `password`, `postgres` 등으로 훑어본다.

## UPH 데이터 흐름

1. `uph_download_macro.py` — WMS에서 배송 파일을 주기적으로 다운로드. 회차마다 **송장입력일 기준 한 번, 배송일 기준 한 번** 조회해 파일 2개를 만든다
   (발주일 기준이 아님). 평소 회차는 오늘만, 재확인 회차(`RECON_*`, 3.5일마다)는 두 기준 각각 -21일~-1일. 첫 실행 기준선은 -21일~오늘.
   배송일 레그가 빠지면 송장일과 실배송일이 벌어진 주문이 '송장'에 멈춘다(2026-09-16 실측).
   검색조건의 **CS 필터를 "전체"로 명시 선택**한다 — 화면 기본값(정상+교환)에 조용히 걸리면 취소·보류 건이 빠져 잔여가 부풀었다(2026-09-01 발견).
2. `watchdog_agent.py` (v3, 폴링) — **아직 처리 안 한 파일 전부를 오래된 순서로** 읽는다(회차당 파일 2개가 서로 다른 행을 담으므로,
   최신 파일 하나만 처리하도록 바꾸면 한쪽 내용이 통째로 빠진다). 각 파일은 `merge_duplicate_rows()`로 (order_key, status) 단위 병합 → 캐시와 비교해 **CS·보류·수량이 바뀐 행만** `order_status_log`에 upsert(송장·배송 상태만). 바뀐 행은 `detected_at`도 갱신된다.
3. `app.py` UPH 현황판 — `uph_get_order_counts()`가 송장번호 distinct 기준으로 5개 지표 계산.

## UPH 숫자가 이상할 때 진단하는 법

추측하거나 대시보드 코드만 보고 고치지 말고, **로컬 DB를 직접 SQL로 조회해 실측한다**(읽기 전용 트랜잭션 권장).
`order_status_log`에서 해당 동·송장번호의 전체 이력을 시간순으로 찍어 보고 아래 패턴부터 확인한다.

1. **상품코드 앞자리 0 불일치** — WMS가 같은 상품을 `3727`/`03727`로 다르게 내려준다. 현황판 쿼리는 앞자리 0을 무시한 `norm_key`로 묶어 해결했다. 같은 실물인데 표기가 달라 키가 갈라지는 패턴을 의심할 것.
2. **최신 상태 역행** — `latest`를 `detected_at`만으로 고르면, 배송된 주문의 송장 행이 나중에 재저장될 때 다시 미배송으로 잡힌다(2026-08-18 실측 4건). 지금은 **배송 > 송장 우선순위로 먼저 고르고** 같은 상태 안에서만 `detected_at`을 본다. 이 정렬을 바꾸지 말 것.
3. **합포 주문** — 한 송장의 상품 중 일부만 배송으로 갱신되는 경우가 있어, 송장 안에 배송 상품이 하나라도 있으면 송장 전체를 배송완료로 본다(`invoice_shipped`).
4. **WMS 파일에 행 고유키 없음** — 부분취소·부분교환 주문은 키가 같은 줄이 수량·CS만 달리 여러 개 온다. 병합(수량은 취소분 제외 합계, 보류는 OR)을 건너뛰면 캐시가 매 회차 자기 자신과 싸우며 무한 재푸시되고 완료 수량이 적게 나온다.
5. **수집 중단 여부** — 파이프라인 건강은 `MAX(detected_at)`이 아니라(바뀐 행만 갱신되므로 조용한 시간대엔 멈춰 보임) **`uph_agent.log`의 최근 "파일 처리 시작" 시각**과 **다운로드 폴더의 최신 파일 시각**을 비교해 판단한다.

## 알려진 미해결 (감사 AX-20261014-04)

- 현황판 집계 쿼리가 예외를 삼키고 0으로 표시한다(F7) — "0건"이 DB 장애일 수 있다.
- watchdog이 읽기에 실패한 파일을 같은 프로세스에서 재시도하지 않는다(F6).
- 진행 상황은 `docs/HANDOFF.md`의 감사 수정 체크리스트 참고.
