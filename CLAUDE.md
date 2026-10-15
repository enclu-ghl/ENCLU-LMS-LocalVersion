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

## 반드시 지킬 것
- commit/push는 매번 사용자 확인 후. 공개 저장소 — 비밀값·IP·DB URL 커밋 금지.
- `웹으로 진행 중인 건/`은 별도 저장소(`enclu-ghl/ENCLU-LMS`). 수정 시 해당 폴더에서 `git remote -v` 확인.
