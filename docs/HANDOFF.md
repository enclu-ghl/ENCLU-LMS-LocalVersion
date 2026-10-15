# HANDOFF — 현재 상태와 다음 단계

마지막 갱신: 2026-10-14 (Claude Code)
세션이 끝날 때마다 이 문서를 갱신한다. 비밀값·IP는 적지 않는다(공개 저장소).

## 운영 현황
- 운영 DB: 로컬 PostgreSQL `enclu_scm` (2026-10-13 Supabase 최신본으로 교체 완료). Supabase는 읽기 전용 동결.
- UPH: 이 폴더의 허브(`ENCLU-SCM-ALL-SYSTEM.bat`)로 가동 중.
- 웹앱(`웹으로 진행 중인 건/app.py`, 별도 저장소): 로컬 8501, 예약작업으로 자동 실행.
- 다른 PC용 원격 DB 접근: 프로그램별 최소권한 계정 개방. 실제 직원 PC 접속은 **미검증**.
- 최신 릴리스: v1.3.19.

## 시스템 점검 (2026-10-14 18시, Claude)
| 항목 | 상태 |
|---|---|
| 도구 | Git 2.54 / Node 24.19 / Python 3.14.6(`py`) / Claude Code 2.1.299 / Codex 0.162.1(ChatGPT 로그인, 플러그인 ready) ✅ |
| WSL·Hermes | Ubuntu 26.04.1(WSL2, 메모리 7.7G) / Hermes v0.22.0, 모델 provider `openai-codex`(구독, API 키 불필요) ✅. `hermes doctor` 경고는 미사용 선택 도구(discord·이미지 생성 등)뿐 |
| 운영 DB | PostgreSQL 서비스 16·17·18 모두 실행 중(포트 3개). `enclu_scm`은 16. 17·18은 전환 당시 기능 제한(덤프 도구 버전) 때문에 의도적으로 설치한 것 — 유지 |
| 웹앱 | 8501 health 200 ✅ (예약작업 Running) |
| UPH 수집 | 사용자가 재가동함 — 2026-10-15 다운로드 매크로·watchdog 실행, 로그 갱신 확인 ✅ |
| 백업 | 매일 03:00 E: 디스크, 10/14 정상(결과 0) ✅. PC 밖 사본은 추후(주기적 압축본 또는 사용자 노트북 셋팅) |
| 저장소 | `ax/setup-v2`: AX 커밋 2개 + F1 수정 미커밋. `main`: 미푸시 커밋 1개(`ad95fc4`). 웹앱 저장소(ENCLU-LMS) 깨끗 |
| 구 폴더 `통합시스템` | 미추적 `.agents/`, `_db_archive_backup/` 남음(롤백용, 손대지 않음) |
| 미흡 | ~~프로젝트 가이드 스킬 낡은 서술(F4)~~ 2026-10-15 정리 / CI에 테스트 단계 없음 / Hermes 전체 흐름 미검증 / 직원 PC 실접속 미검증 |

## ⚠️ 위험 — 허브 exe의 SQLAlchemy 버전 미고정 (2026-10-15 발견 → 코드 조치 완료 AX-20261015-03, **릴리스 대기**)
- 웹앱 `requirements.txt`는 `sqlalchemy<2.1`로 고정돼 있지만 **루트 `requirements.txt`(exe 빌드용)는 미고정**.
- SQLAlchemy 2.1부터 `postgresql://`의 기본 드라이버가 psycopg(v3)로 바뀜 — psycopg2만 있으면 `No module named 'psycopg'` (임시 venv에 2.1.4 설치해 재현 확인).
- exe 번들(`ENCLU_SCM.spec`)은 psycopg2만 포함. 주문파일정리는 `create_engine(DATABASE_URL)`(주소가 `postgresql://`)라 **2.1이 번들됐다면 직원 PC exe에서 파일찢기 DB 접속 실패**. 박스추천은 `postgresql+psycopg2://` 명시라 무관. 서버 PC는 소스 실행(2.0.51)이라 무관.
- v1.3.19(2026-10-13 빌드)에 실제로 2.1이 들어갔는지는 CI 로그 미확인(`gh` 없음).
- **조치(AX-20261015-03)**: 루트 `requirements.txt`에 `sqlalchemy<2.1` 고정, 자가진단 `pg_driver`가 기본 드라이버까지 확인 → CI가 exe 자가진단에서 2.1 번들을 차단. **남은 것: `version.txt` 상향 + main 푸시로 재빌드(사용자 확인)**
- (당초 조치안) 루트 `requirements.txt`에 `sqlalchemy<2.1` 고정(필요 시 파일찢기 URL을 `postgresql+psycopg2`로 정규화) → `version.txt` 상향 → main 푸시로 재빌드. **푸시·릴리스는 사용자 확인 필요.** 직원 PC 실접속 검증 전에 처리 권장.

## 운영 지식 (이전 채팅 인수인계 문서에서 취합, 2026-10-15)
원문은 저장소 밖 `개발 진행 중인 물류 프로그램\AX_인수인계\인수인계_2026-10-15.md`(내부 주소 포함 — 커밋 금지).
- 서버 PC 한 대에 DB·웹앱·UPH·백업이 모두 있다. 꺼지면 전부 멈춤. 자동 로그인 미설정.
- 웹앱은 예약작업이 창 없이 `start_local_server_task.bat` 실행(로그 `_local_db/streamlit_local.log`). 예약작업 재등록 시 `cmd.exe /c "경로"` 따옴표는 한 겹.
- **Streamlit Cloud 앱이 아직 ENCLU-LMS 저장소를 본다** — `app.py` 푸시는 Cloud에도 반영(Cloud는 읽기 전용 Supabase라 저장 불가).
- UPH: WMS 다운로드 양식 이름 **`UPH현황`에 의존**(2026-10-14 양식 이름이 사라져 매크로 68회 실패). `ad95fc4`(양식 이름 환경변수 `UPH_DOWNLOAD_FIELD_TEXT`·실패 시 목록 로그)는 미푸시, 적용하려면 매크로 재시작.
- UPH 프로세스는 **허브의 자식 프로세스** — 허브를 닫으면 UPH도 멈춤. UPH 자동화는 한 PC에서만(전용 WMS 계정).
- UPH 인시: `manpower_log`를 `event_time` 순으로 계산. **마감 누락은 UPH를 부풀린다.** 2026-10-12·13 일부 동 인원 기록 정정 필요(실제 시각·인원은 사용자 확인).
- 완료건수 이력: 주문 로그는 2026-09-01부터, 그 이전은 `uph_historical_summary`(수기 업로드).
- 함정: 한글 SQL을 `psql -c`로 넘기지 말 것(인코딩 깨짐 → UTF-8 파일 + `psql -f`) / `pg_dump`는 서버 버전 이상 클라이언트 필요(PG 17·18 설치 이유) / Bash 도구에서 `\\`가 `\`로 줄어듦 / 방화벽·계정 변경은 UAC 승인 필요.
- 보안 권장(미실행): postgres 관리자 비밀번호 변경(과거 채팅 노출). 앱 로그인 화면 없음 — 사내망/Tailscale 보호에만 의존, 8501 포트포워딩 금지.
- 기술 부채: Streamlit `use_container_width` deprecated(`width='stretch'`), `st.components.v1.html` → `st.iframe` 경고.

## 진행 중
- **AX 개발 환경 구축** (브랜치 `ax/setup-v2`): 공통 규칙·Codex 지시/검토 스크립트 추가, WSL·Hermes 설치와 연결 시험까지 완료. Hermes 전체 흐름은 미검증.
  - [x] Codex CLI 설치·ChatGPT 로그인
  - [x] Codex 검토 스크립트 연결 시험 (AX-20261014-01, `reports/AX-20261014-01/`) — 지적 2건 검증·수정
  - [x] Codex 지시 스크립트(`codex-plan.ps1`) 실제 과제로 시험 — AX-20261014-03 `plan.md` 생성(exit 0).
    단 지시서를 쓴 Codex(읽기 전용 샌드박스)의 WSL 확인 명령은 `E_ACCESSDENIED`로 거부됨 → 샌드박스 제약이며 아래 설치 확인과는 별개.
  - 주의: Codex 데스크톱 앱 전역 설정 때문에 스크립트는 `--ignore-user-config -c windows.sandbox=unelevated`로 실행
  - [x] Codex 플러그인(`/codex:review`) 검토 동작 확인 (전역 sandbox=unelevated 변경 후)
  - [x] WSL2 설치 — Ubuntu 26.04.1 LTS (Codex 오케스트레이터 확인)
  - [x] Hermes Agent 설치 — `v0.22.0+102.g5f6d683`, WSL Ubuntu 위 (Codex 오케스트레이터 확인)
  - [x] 연결 시험: Hermes → Claude → Codex 표식 세션 `20261014_154228_bd9f0f` 성공 (호출 경로 확인만, 실제 작업 아님)
  - [x] 합성 샘플 `ax-sample-02` (저장소 밖 로컬 샘플 `~/.claude/project/ax-sample-02`, 합성 데이터만, DB·네트워크 접근 없음)
    - WSL Ubuntu `python3 -B -m unittest -v` → 26개 테스트 통과(OK, exit 0)
    - CLI 리포트(2026-10-14 합성 데이터): 원본 7 / 중복 제거 6 / (날짜+ID) 그룹 5 / 완료율 50% = shipped 2 ÷ (shipped 2 + printed 1 + held 1), cancelled 제외
    - 근거: 샘플 폴더의 `plan-check.md`·`implementation.md`·`report.md`
    - 구현 진행 주체: **Codex가 Claude를 직접 호출**(보호 경로 쓰기 확인창 때문). Hermes 경유 아님
    - Hermes는 `report.md` 읽기 전용 검증만 수행(세션 `20261014_162927_98ac5b`) — 집계·완료율 공식 일치
  - [ ] **Hermes 전체 흐름**(지시→구현→검토를 Hermes가 순차 진행) — **미검증**. 연결 시험·샘플 성공을 전체 흐름 검증으로 보지 않는다
  - [ ] 첫 실제 업무 과제: 일일 보고 샘플 1건의 입력 검증·계산·초안 (위 합성 샘플은 해당 안 됨)
  - 검증 기록: `reports/AX-20261014-03/plan-check.md`, `review.md`(Codex 검토), `review-check.md`(Claude 검토 검증)

## 남은 일 (로컬DB 전환 후속, 인수인계 문서 우선순위 반영)
1. **exe 재릴리스**(SQLAlchemy 고정은 코드 반영됨, 위 위험 항목) → 그다음 **직원 PC 실접속 검증**(exe 설치 → DB 포트 연결 확인 → 접속정보 입력 → 파일찢기·박스추천 동작). 사용자가 직원 PC로 테스트 예정
2. 인원 기록 정정: 2026-10-12·13 일부 동 마감 누락·기록 없음 (실제 시각·인원은 사용자 제공 필요)
3. 미푸시 커밋 정리: `main`의 `ad95fc4`, `ax/setup-v2`의 AX 커밋들 — 병합·푸시·릴리스는 사용자 확인
4. UPH 매크로 재시작(`ad95fc4` 적용)
5. 가용성: 자동 로그인, 윈도우 업데이트 재부팅 방지, UPS, 서버 IP 고정(DHCP 예약), UPH 멈춤 알림(Hermes 후보)
6. 보안: postgres 관리자 비밀번호 변경. (PG 17·18은 사용자 결정으로 유지 — 서비스 자체는 덤프 도구만 필요하므로 중지해도 됨)
7. PWA(설치형) + HTTPS(`tailscale serve`), 직원 접속주소 안내·옛 Cloud 즐겨찾기 교체
8. 인원 입력 UI 개선(시각 직접 입력, 몇 초 내 중복·마감 누락 경고)
9. **2026-10-20 이후** 관찰 종료 → PC 밖 백업 사본(사용자: 주기 압축본 또는 노트북) + 복원 재확인 → Supabase·Cloud 앱·박스추천 원격PG 해지 (되돌릴 수 없음, 실행 시점에 재확인)
- ~~`_local_db/verify_migration.py`가 비교 대상 URL을 별도로 받도록 수정~~ — 이미 반영돼 있음(`SUPABASE_URL` 환경변수 또는 구 폴더 `.env`), 2026-10-14 확인
- 감사(AX-04) 수정: [x] F1 종료코드(AX-05, 테스트 `_local_db/tests/`) → [x] F7 현황판 조회 실패 경고·UPH 제외(AX-20261015-02, `app.py` **미커밋**, AppTest 10조건 통과) → [x] F6 watchdog 읽기 실패 재시도(AX-20261015-04: 최초 포함 3회·폴링마다 1회, 실패/미안정 파일에서 멈춰 오래된 순 반영 보장, 재시도 대기 파일은 정리 제외, 테스트 13개 `UPH 시스템/tests/`) — **UPH 재시작 전까지 운영 미반영** → [x] F2 검증기 테이블·컬럼·증가 규칙(AX-20261015-05, **대체 모드 — Codex 재검토 대기**, 테스트 17개) → [ ] F3 · [x] F4(스킬 문서) → [ ] F5
- ~~프로젝트 가이드 스킬 Supabase 시절 서술 갱신~~ — 2026-10-15 완료(Supabase 서술 제거, 로컬 PG 기준·UPH 흐름·진단법 현행화, `.agents` 사본 동기화)

## Codex 재검토 대기 (AX_RULES 2-1 대체 모드로 처리한 작업)
- AX-20261015-05 (F2 verify_migration) — 2026-10-15 Codex 사용 한도 소진(13:02 이후 재사용 가능). 지시서 Claude 작성, 검토 devops-review. 복귀 시 `powershell -File ax\codex-review.ps1 AX-20261015-05 -Base <F2 이전 커밋>`

## 미해결 이슈
- 웹앱 키오스크 '최근 완료' 티커 조회와 허브 카드 출고 수치는 DB 조회 실패 시 보호·경고가 없음(F7 범위 밖).
- 파이프라인 건강 판단에 `MAX(detected_at)` 사용 금지 — 바뀐 행만 갱신되므로 조용한 시간대엔 멈춰 보임. `uph_agent.log`·다운로드 폴더 시각으로 판단 (스킬 문서 참고).
- 보류: ④ 일자별 UPH C안(시각 직접 입력 + 연속입력 경고).
