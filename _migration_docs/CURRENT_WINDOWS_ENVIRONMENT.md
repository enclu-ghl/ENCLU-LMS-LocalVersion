# 현재 Windows 운영환경 조사 보고서

조사일: 2026-08-03 / 조사 대상 PC: EN-A020 (192.168.0.46)
조사 방식: 읽기 전용 (설치/변경 없음)

범례: **[확인]** 실제 조회로 확인된 사실 / **[추정]** 정황상 추정 / **[미확인]** 추가 확인 필요

---

## 1. 현재 시스템 구성

### 1.1 OS
- **[확인]** Windows 11 Pro, Version 10.0.26200 (Build 26200), 64-bit
- **[확인]** 설치일 2025-07-16, 설치 유형: 일반 설치(업그레이드/클린 여부는 SerialNumber만으로는 미확인)
- **[확인]** 워크그룹(WORKGROUP) 구성 — Active Directory 미가입, 로컬 계정만 사용
- **[확인]** 시간대: (UTC+09:00) Seoul, NTP(time.windows.com)로 자동 동기화 중, w32time 서비스 Running/Automatic, 최근 동기화 2026-08-03

### 1.2 하드웨어
- **[확인]** CPU: AMD Ryzen 5 5600X, 6코어 12스레드
- **[확인]** 메모리: 총 16,309MB(약 16GB), 조사 시점 가용 4,152MB — 여유가 많지 않은 편
- **[확인]** 디스크
  | 드라이브 | 총용량 | 여유공간 |
  |---|---|---|
  | C: | 476GB | 323.6GB |
  | D: (시스템 예약) | 0 | 0 |
  | E: | 232.3GB | 135.7GB |

### 1.3 네트워크
- **[확인]** 호스트명 EN-A020, 이더넷 IPv4 192.168.0.46
- **[미확인]** 기본 게이트웨이 / DNS 서버 — PowerShell CIM 출력이 인코딩 문제로 판독 불가했음. 필요 시 `ipconfig /all` 재조회 권장 (승인 불필요, 단순 재조회)
- **[확인]** NAS/네트워크 드라이브 매핑 없음 (`Get-SmbMapping`, `net use` 모두 빈 목록)

### 1.4 LISTEN 포트 (조사 시점 스냅샷)
- **[확인]** 이 PC 고유 SCM 프로그램이 상시 리스닝하는 포트는 없음 (박스추천/UPH제어판/파일찢기는 GUI 프로세스이며 네트워크 포트를 열지 않음)
- **[확인]** 조사 시점에 chrome/chromedriver 포트(9222, 4826 등)가 열려 있었음 → Selenium 자동화 세션이 활성 상태였던 것으로 보임 **[추정]**
- **[확인]** 그 외 포트는 OS 기본 서비스(svchost, lsass, spoolsv 등)와 이 PC에 설치된 각종 한국형 보안/인증 프로그램(AnySign4PC, veraport-x64, delfino, OZWebLauncher, UniCRSLocalServer, MaEPSBrokerIros 등) — **SCM 프로젝트와 무관한 범용 업무 PC 소프트웨어로 추정 [추정]**

### 1.5 보안 상태
- **[확인]** Windows Defender: 사용중, 실시간 보호 On, 변조 방지 On, 시그니처 최신(2026-08-03)
- **[확인]** 방화벽: Domain/Private/Public 3개 프로필 모두 사용중, 기본 동작은 Windows 기본값(인바운드 차단/아웃바운드 허용) 상태
- **[확인]** 자동 로그인(AutoAdminLogon) 레지스트리 설정 없음 — 다만 실제 운영은 사람이 매일 로그인해 수동으로 프로그램을 켜는 방식에 의존함 (§3 참고)

---

## 2. 애플리케이션 구성도

프로젝트 경로: `C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템`

```
통합시스템 (허브: ENCLU-SCM-ALL-SYSTEM.py, Tkinter 데스크톱 앱)
 ├─ 박스추천프로그램/main.py         [데스크톱 GUI, subprocess 실행]
 ├─ 자동 매칭 프로그램/               [데스크톱 GUI+Selenium, subprocess 실행, 자체 venv]
 ├─ UPH 시스템/                      [데스크톱 GUI+Selenium+watchdog, subprocess 실행]
 ├─ 주문파일정리 프로그램/            [데스크톱 GUI, subprocess 실행]
 └─ 웹으로 진행 중인 건/app.py        [Streamlit 웹앱 — 실제 "SCM 웹 대시보드"]
```

- **[확인]** 허브가 직접 띄우는 것은 4개의 Windows 데스크톱 GUI 프로그램뿐이며, "웹" 카드 3개(재고조사/무게구간계산/UPH현황판)는 사실 **하나의 Streamlit 앱**을 쿼리파라미터로 구분해 브라우저로 여는 방식임.
- **[확인] 중요 발견**: 이 Streamlit 앱은 현재 이 PC가 아니라 **Streamlit Community Cloud(외부 퍼블릭 SaaS)** 에 배포되어 있음 (`https://inventory-check-st2nrle3vdoyeqgb7hqitj.streamlit.app/`). 즉 "SCM 웹 대시보드" 자체는 이미 이 Windows PC 밖에서 돌아가고 있고, 이 PC에서 실행되는 것은 그 대시보드가 읽는 **데이터를 채워 넣는 백엔드 파이프라인(UPH watchdog/매크로 등)** 임.

### 언어/런타임
- **[확인]** Python 3.14.6 (`C:\Users\enclu\AppData\Local\Python\bin\python.exe`에서 확인)
- **[확인]** 코드 내 하드코딩된 두 번째 인터프리터 경로 `C:\Users\admin\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe` 도 이 PC에 실제 존재함(True) — 다른 PC에서 옮겨온 흔적이 여전히 남아있는 것으로 추정 **[추정]**
- **[확인]** 잠금 파일(lock file) 없음 — `requirements.txt`(웹앱), `agent_requirements.txt`(UPH)만 존재, 버전 고정/해시 없음. "자동 매칭 프로그램"은 자체 venv를 갖고 있으나 그 안의 패키지 목록을 별도 requirements로 관리하지 않음
- **[확인]** Git 저장소 없음 — 프로젝트 전체 트리에서 `.git` 디렉터리를 재귀 검색했으나 하나도 발견되지 않음. 커밋/브랜치/변경 이력 개념 자체가 없고, 모든 파일이 "지금 디스크에 있는 그대로"가 유일한 버전임
- **[확인]** dev/운영 모드 구분 없음 — 별도의 환경 플래그 없이 동일 코드가 항상 같은 방식으로 실행됨

### 하드코딩된 경로 (Windows 종속성의 핵심 원인)
- **[확인]** 허브의 `FILE_PATHS`, `APP_PYTHON` 딕셔너리에 각 하위 프로그램의 절대경로와 python.exe 절대경로가 그대로 박혀 있음
- **[확인]** `.env`(UPH_WATCH_FOLDER), `settings.json`(output_folder: `C:/Users/enclu/Downloads`) 등도 특정 사용자 계정 경로에 종속됨
- 이는 OS 선택과 무관하게 마이그레이션 전 반드시 정리해야 하는 항목임 (§ WINDOWS_DEPENDENCY_REPORT.md)

### 실제 실행 명령
- **[확인]** `ENCLU-SCM-ALL-SYSTEM.bat` 더블클릭 → 허브 실행 → 카드 클릭 시 `subprocess.Popen`으로 각 프로그램 실행
- **[확인]** 개별 실행도 각 폴더의 `.bat` 더블클릭 또는 `python.exe 파일명.py` 직접 실행으로 가능
- **[확인]** Streamlit 웹앱은 Streamlit Cloud가 자체적으로 `streamlit run app.py` 형태로 구동 (이 PC와 무관)

---

## 3. 실행 프로세스와 시작 순서

- **[확인]** Windows 서비스로 등록된 것 없음 (`Get-Service`에서 postgres/mysql/nginx/apache/iis/docker/redis/pm2 관련 서비스 전무)
- **[확인]** 작업 스케줄러에 이 프로젝트 관련 작업 없음 (OneDrive/NVIDIA/Google 등 OS·써드파티 기본 작업만 존재)
- **[확인]** PM2 / IIS / Docker / Apache 미설치 (`Get-Command`로 확인 시 없음)
- **[확인]** WSL 바이너리는 설치되어 있으나(`wsl.exe` 존재), 이 프로젝트가 WSL을 사용한다는 증거는 없음 **[미확인]** — 필요 시 `wsl -l -v`로 배포판 존재 여부 재확인 가능
- **[확인] 중요**: 자동 시작/장애 시 자동 재시작 메커니즘이 **전혀 없음**. 모든 프로그램은 사람이 로그인해서 수동으로 더블클릭해야 켜짐
- **[확인] 중요**: UPH 파이프라인은 사람이 매일 "디버그 크롬"을 직접 실행하고 사내 WMS("이지어드민")에 보안코드를 입력해 로그인해야만 동작 시작 가능 (`UPH 시스템/README.txt` 기준) — 사람의 로그인 세션에 강하게 종속됨

---

## 4. 데이터 및 영속 저장소

| 구분 | 내용 |
|---|---|
| Supabase (클라우드 Postgres) | UPH 시스템, 주문파일정리 프로그램이 사용. `.env`의 `DATABASE_URL`로 접속 (값 미공개) **[확인]** |
| 별도 원격 PostgreSQL | 박스추천프로그램(main.py)이 사용. 이 PC가 아닌 외부에 이미 가동 중인 서버 (설치설명서 기준) **[확인, 문서상]** / 정확한 호스트 위치(사내망/외부)는 **[미확인]** |
| 로컬 SQLite 캐시 | `UPH 시스템\uph_agent_cache.sqlite3` 약 2.6MB **[확인]** |
| 다운로드 파일 저장소 | `UPH 시스템\Download the Uph file` 약 85MB, 현재 13개 .xls 파일 누적. 자동 정리/삭제 로직 확인되지 않음 → 무한 누적 가능성 **[확인 사실 + 추정 리스크]** |
| NAS/공유폴더 | 없음 (매핑된 네트워크 드라이브 0건) **[확인]** |
| 로컬 백업 | 이 PC 상에 이 프로젝트를 위한 백업 스크립트/예약 작업 없음 **[확인]** — Supabase/원격 Postgres 자체의 백업 정책은 **[미확인]**, 복원 절차도 **[미확인]** |
| `pg_hba.conf`/`postgresql.conf` | 박스추천프로그램 폴더 안에 존재하나, 이 PC에 로컬 PostgreSQL 서비스/리스닝 포트(5432)가 없어 실제로 구동 중인 로컬 DB는 아닌 것으로 보임 — 참고용 사본으로 추정 **[추정, 사용자 확인 필요]** |

---

## 5. 내부·외부 연동

- **[확인]** 이지어드민(사내 WMS로 추정) — Selenium으로 브라우저를 직접 조작해 엑셀 파일을 다운로드하는 방식(API 아님), 사람이 보안코드로 로그인 필요
- **[확인]** Supabase — 클라우드 Postgres, 아마 REST API도 포함 (Supabase 표준 구성)
- **[확인]** 별도 원격 PostgreSQL 서버 — 위치/네트워크 경로 **[미확인]**
- **[확인]** Streamlit Community Cloud — 웹 대시보드가 현재 이곳에 공개 배포되어 있음. **접근 제어(인증) 여부는 [미확인]**
- **[미확인]** SMTP/메일 발송, 고정 IP 등록/allowlist 여부, ERP/프린터/바코드 장비 연동 — 코드 전수 검색은 하지 않았으며 추가 확인 필요

---

## 6. 요약: 확인 vs 추정 vs 미확인 하이라이트

- 확인된 핵심 사실: 서비스/스케줄러/자동시작 전무, Git 없음, 하드코딩 절대경로 다수, 웹 대시보드는 이미 외부 SaaS(Streamlit Cloud)에 있음, DB는 Supabase+별도 원격 Postgres 이원화
- 추정: pg_hba/postgresql.conf는 비활성 참고 사본, 리스닝 중이던 보안 프로그램들은 프로젝트 무관
- 미확인(추가 확인 필요): 게이트웨이/DNS, 원격 Postgres 서버 위치, WMS 도메인/네트워크 경로, Streamlit Cloud 대시보드 인증 여부, 백업/복원 절차, WSL 실사용 여부
