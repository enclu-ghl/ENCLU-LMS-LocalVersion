# DECISIONS — 확정 결정과 사유

새 결정은 위에 추가한다. 형식: 날짜 · 결정 · 사유 · (대안/롤백)

## 2026-10-14 · AX 개발 환경
- **역할: Codex = 지시 + 검토, Claude = 개발 + Codex 결과 검증, Hermes = 순차 전달(보류)**
  사유: 구현과 검토를 다른 모델로 분리해 한쪽의 오류를 다른 쪽이 잡도록 함. Codex 결과도 Claude가 검증해야 한다는 사용자 요구.
- **AX 설정은 운영 저장소의 `ax/setup-v2` 브랜치에서 진행**, 확인 후 main 병합.
  사유: 이미 Git + Claude Code로 운영 중이라 별도 clone은 동기화 부담만 늘어남.
- **Codex는 Windows 네이티브(npm 전역 설치)**, 호출은 `codex exec --sandbox read-only`.
  사유: WSL 없이 바로 사용 가능. read-only는 로컬 명령 샌드박스일 뿐 외부 MCP 쓰기까지 막지 않으므로 검토용 Codex에는 쓰기 MCP를 연결하지 않는다.
- **Codex 전역 설정 `~/.codex/config.toml`의 `[windows] sandbox`를 `elevated` → `unelevated`로 변경** (사용자 승인, 백업 `config.toml.bak_20261014`).
  사유: elevated 샌드박스가 미설정이라 Codex 플러그인(`/codex:review`)·CLI의 셸 도구가 실패. Codex 데스크톱 앱도 이 설정을 공유함. 롤백: 백업 파일로 복원.
  `ax/*.ps1`은 추가로 `--ignore-user-config`를 써서 검토 시 앱 플러그인(브라우저·컴퓨터 제어)을 싣지 않는다.
- **Hermes는 WSL2 위에 설치** (Windows 네이티브 미지원).
- 비용: Claude Pro / ChatGPT Plus 구독 로그인만 사용, 추가 API 지출 0원. 한도 도달 시 유료 대체로 자동 전환하지 않음.

### 설치 기록
| 날짜 | 도구 | 버전 | 범위 | 비고 |
|---|---|---|---|---|
| 2026-10-14 | Codex CLI (`@openai/codex`) | 0.162.1 | npm 전역 | ChatGPT 계정 로그인 |
| (기존) | Claude Code | 2.1.232 | 사용자 | |
| (기존) | Git 2.54 / Node 24.19 / Python 3.14 (`py`) | | | `python` 명령은 MS Store 스텁 — `py` 사용 |

## 이전 결정 (요약)
- 2026-09-18 · app.py에 물린 프로그램(UPH, 재고 할당)은 app.py 전환 때 한 번에 이동 — 개별 전환 시 대시보드 멈춤 사고.
- 2026-08-19 · 시책 대조 검증은 프로그램 개발 취소, 수동 엑셀 체크.
- 대량 DB 쓰기는 행 단위 INSERT 대신 일괄 upsert.
- commit/push는 매번 사용자 확인 후.
