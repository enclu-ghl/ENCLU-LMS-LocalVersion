# AX-20261022-01 — 검토 검증 (Claude)

## 변경 요약
- 제어판(`UPH 시스템/uph_control_panel.py`): 종료 기록 파일 `uph_panel_events.log`(열림·시작·종료 사유·taskkill 결과·예상치 못한 종료 코드와 stderr 마지막 줄·외부 종료·창 닫기/취소·창 소멸), 실행 중 창 닫기 확인 창, 접근 코드 소스 평문 제거(`UPH_PANEL_ACCESS_CODE`, UTF-8 바이트 비교, 미설정 시 차단, 단독 실행은 옆 `.env`).
- 허브(`hub/secrets.py`): `UPH_PANEL_ACCESS_CODE`를 UPH 제어판 필수 항목으로 추가(exe는 1회 입력·DPAPI 저장).
- watchdog: stdout/stderr UTF-8 재설정으로 cp949 `UnicodeEncodeError` 경고 제거.
- 매크로: 재확인 일정은 마지막 재확인 조회까지 시작했을 때만 미룸, 간격 환경변수 검증(최소 90초) — AX-20261017-01 미해결 2건 해소. AX-20261021-01(WMS 탭 선택)과 후속 "이지WMS" 인정 포함.
- 운영 PC의 `UPH 시스템/.env`(gitignore)에 기존 접근 코드를 넣어 입장 방식은 그대로.

## 실행한 테스트 (Claude)
- `py -B -m unittest discover -s "UPH 시스템/tests"` → **66개 통과** (제어판 14 + 매크로 39 + watchdog 13), `_local_db/tests` 19개 통과
- 수정 전 코드(제어판·매크로)로 같은 테스트 → 22개 실패/오류 → 새 테스트가 결함을 잡음
- cp949 경고 재현: 수정 전 stderr 509바이트 → 수정 후 0바이트
- `hmac.compare_digest('a','가')` → `TypeError` 직접 확인 (Codex 1회차 지적 재현)

## Codex 검토 판정
| 회차 | 지적 | 판정 | 조치 |
|---|---|---|---|
| 1 | [중간] `compare_digest(str)`는 ASCII만 — 한글 코드·입력 시 TypeError로 입장 불가 | 타당 (직접 재현) | UTF-8 바이트 비교 + 한글 일치/불일치 테스트 |
| 2 | 추가 결함 없음 | 동의 | — |

## 미검증 / 운영 반영
- 실제 Tk 창(확인 창 표시·최소화), exe의 DPAPI 입력 흐름은 화면으로 확인하지 않음.
- **제어판·허브 변경은 허브 재시작 후 적용**(허브가 모듈을 한 번만 import). 매크로·watchdog 변경은 제어판에서 재시작하면 적용.
- 접근 코드는 과거 커밋 이력에 남아 있음 → 사용자가 `.env`의 값을 새 코드로 바꾸는 것을 권장.
