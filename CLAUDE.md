# CLAUDE.md — ENCLU SCM 통합시스템 (로컬DB 버전)

작업 전에 아래 순서로 읽는다.

1. `docs/AX_RULES.md` — 공통 규칙 (역할 분담·상호 검증·데이터·안전). **최우선 기준**
2. `docs/HANDOFF.md` — 현재 상태·진행 중 작업·다음 단계
3. `docs/DECISIONS.md` — 확정된 결정과 사유
4. `.claude/skills/enclu-scm-project-guide/SKILL.md` — 저장소 지도·버그 이력·진단법
   (Codex용 동일 사본: `.agents/skills/enclu-scm-project-guide/SKILL.md` — 고칠 때 둘 다 맞춘다)

## Claude의 역할
- 개발 담당. Codex가 만든 지시서(`reports/<작업번호>/plan.md`)와 검토(`review.md`)는
  **그대로 따르지 않고 코드·DB·테스트로 검증한 뒤** `plan-check.md` / `review-check.md`에 판정을 남긴다.
- 구현 후 Codex 검토 요청: `powershell -File ax\codex-review.ps1 <작업번호>`
- 실제로 실행한 테스트와 실행하지 못한 테스트를 구분해서 보고한다.

## 두 컴퓨터 동기화 (회사 서버 PC ↔ 집 PC, 2026-11-05 결정)
두 컴퓨터는 같은 개발 환경을 두고 **GitHub로만** 서로 맞춘다 (실시간 폴더 동기화·원격 운영 DB 접속 안 함).
- 집 PC는 **직원 PC(서버에 접속만 하는 클라이언트)가 아니다.** 서버 PC와 똑같이 저장소·Python·PostgreSQL·Claude Code·Codex를
  모두 갖춘 동등한 개발 환경이며, 어느 쪽에서 개발해도 같은 결과가 나와야 한다.
  → 경로·설정을 특정 PC에 고정하지 말고, PC마다 다른 값은 `.env` 등 커밋하지 않는 설정으로 둔다.
- **작업 시작 시:** 두 저장소(메인, `웹으로 진행 중인 건/`)에서 `git fetch` 후 원격에 새 커밋이 있는지 확인하고,
  있으면 사용자에게 알리고 `git pull`로 받은 뒤 시작한다. 로컬에 커밋 안 된 변경이 있으면 먼저 알린다.
- **사용자가 "오늘 작업 마무리"라고 하면:** 두 저장소 모두 비밀값 점검 → 커밋 → push까지 진행한다(이때는 따로 묻지 않음).
  push 후 원격 최신 커밋을 확인해 보고한다.
- 코드·문서만 GitHub로 맞춰진다. `.env`와 DB 데이터는 컴퓨터마다 따로 — 데이터 이전은 별도 백업/복원으로 한다.

## 반드시 지킬 것
- commit/push는 사용자 확인 후(위의 "오늘 작업 마무리"는 확인으로 본다). 공개 저장소 — 비밀값·IP·DB URL 커밋 금지.
- `웹으로 진행 중인 건/`은 별도 저장소(`enclu-ghl/ENCLU-LMS`). 수정 시 해당 폴더에서 `git remote -v` 확인.
