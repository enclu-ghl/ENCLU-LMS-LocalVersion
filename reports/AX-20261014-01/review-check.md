# AX-20261014-01 검토 검증 (Claude)

대상: AX 환경 구축 파일(CLAUDE.md, AGENTS.md, docs/*, ax/*, reports/README.md) — Codex 첫 연결 시험

| # | Codex 지적 | 판정 | 근거 | 조치 |
|---|---|---|---|---|
| 1 | git 실패 시 일부 변경이 빠진 채 검토 진행 | **타당** | `git diff NOPE_BASE...HEAD` → exit 128 재현. 스크립트가 종료코드를 확인하지 않음 | `Invoke-Git`로 종료코드 확인, 실패 시 중단. 재시험: `-Base NOPE_BASE` → Codex 호출 전 중단, review.md 미생성 확인 |
| 2 | git 출력 캡처 시 한글 깨짐 | **부분 타당** | Claude 실행 환경은 콘솔이 utf-8이라 재현 안 됨. 단 Codex 샌드박스에서 `ks_c_5601-1987`(cp949) 관측 — 한국어 Windows 기본 터미널에서는 발생 가능 | 두 스크립트에 `[Console]::OutputEncoding = UTF8` 추가. 사용자 터미널(cp949)에서의 실제 한글 diff 전달은 **미검증** |

## 연결 시험 결과 (실제 실행)
- 1차: `~/.codex/config.toml`(Codex 데스크톱 앱 설정, `windows.sandbox="elevated"`)로 인해 Codex 셸 도구 시작 실패 → Codex가 "검토 불가, 문제없음 판정 아님"으로 정직하게 보고.
- 해결: `--ignore-user-config -c windows.sandbox=unelevated` → 읽기(git status, Get-Content) 통과, 파일 생성은 PermissionDenied로 차단 확인.
- 2차: 전체 검토 정상 완료, Codex에 의한 파일 변경 없음 확인.

## Codex 플러그인(`/codex:review`) 재검토
- 1차: 전역 설정 `windows.sandbox="elevated"` 때문에 동일 오류(`setup refresh had errors`)로 검토 불가.
- 사용자 승인 후 `~/.codex/config.toml`을 `unelevated`로 변경(백업 `config.toml.bak_20261014`).
- 2차: 명령 5개 모두 exit 0, 미추적 파일 13개 검토 완료 — "확실한 결함 없음". 파일 변경 없음 확인(13개 그대로).
- Claude 판정: Codex가 밝힌 미검증 영역(실제 Codex 호출, cp949 한글 전달)은 위 연결 시험·아래 미검증 항목과 일치. 추가 조치 없음.

## 미검증
- `ax\codex-plan.ps1` 실제 지시서 생성 (다음 실제 과제에서 시험)
- cp949 사용자 터미널에서의 한글 diff 전달
