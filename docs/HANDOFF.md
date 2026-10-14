# HANDOFF — 현재 상태와 다음 단계

마지막 갱신: 2026-10-14 (Claude Code)
세션이 끝날 때마다 이 문서를 갱신한다. 비밀값·IP는 적지 않는다(공개 저장소).

## 운영 현황
- 운영 DB: 로컬 PostgreSQL `enclu_scm` (2026-10-13 Supabase 최신본으로 교체 완료). Supabase는 읽기 전용 동결.
- UPH: 이 폴더의 허브(`ENCLU-SCM-ALL-SYSTEM.bat`)로 가동 중.
- 웹앱(`웹으로 진행 중인 건/app.py`, 별도 저장소): 로컬 8501, 예약작업으로 자동 실행.
- 다른 PC용 원격 DB 접근: 프로그램별 최소권한 계정 개방. 실제 직원 PC 접속은 **미검증**.
- 최신 릴리스: v1.3.19.

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

## 남은 일 (로컬DB 전환 후속)
- 직원 접속주소 안내, PWA+HTTPS(`tailscale serve`)
- 약 1주 관찰 → PC 밖 백업 사본 + 복원 테스트 → Supabase·Cloud 앱·박스추천 원격PG 해지 (되돌릴 수 없음, 그때 재확인)
- `_local_db/verify_migration.py`가 비교 대상 URL을 별도로 받도록 수정
- 프로젝트 가이드 스킬(`.claude/skills/enclu-scm-project-guide`)의 Supabase 시절 서술 갱신

## 미해결 이슈
- `detected_at` 은 UPSERT에서 갱신되지 않음 — 건강 판단에 `MAX(detected_at)` 사용 금지 (스킬 문서 참고).
- 보류: ④ 일자별 UPH C안(시각 직접 입력 + 연속입력 경고).
