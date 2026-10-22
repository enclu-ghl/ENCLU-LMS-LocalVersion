# AX-20261022-01 — UPH 제어판 종료 기록·닫기 확인·접근 코드 분리 + 잔여 정리 (Claude 작성, 사용자 승인 10/22)

> 사용자 지시: "전부 진행 후 푸시". Claude가 지시서를 직접 작성했고 Codex는 사후 검토한다.
> 이번 diff에는 아직 커밋하지 않은 AX-20261021-01(WMS 탭 선택)과 그 후속("이지WMS" 제목 인정)도 함께 들어 있다.

## 배경
- 10/19 16:20, 10/20 00:53, 10/20 13:18, 10/21 17:55, 10/22 13:00 — 매크로와 watchdog이 **오류 출력 없이 동시에** 사라짐. 허브·웹앱은 생존.
- 제어판 창(허브 Toplevel)을 닫으면 `App.on_close()`가 두 프로세스를 `taskkill /T /F`로 함께 종료 → 모양이 일치. 그러나 "종료 요청됨" 기록이 화면에만 남아 원인 확정 불가.
- 제어판 접근 코드가 공개 저장소 소스에 평문으로 있음.

## 수정 범위
1. `UPH 시스템/uph_control_panel.py`
   - `log_panel_event()` → `uph_panel_events.log`(gitignore `*.log`)에 제어판 열림·시작(PID)·종료(사유: 종료 버튼/창 닫기, taskkill 결과, 종료 확인 여부)·예상치 못한 종료(종료코드, stderr 마지막 줄)·외부 프로세스 종료·창 닫기/취소·창 소멸을 기록. 기록 실패는 무시.
   - `App.on_close()`: 실행 중이면 확인 창. '아니오'면 그대로 계속(기록만). 실행 중이 아니면 묻지 않고 닫음.
   - 접근 코드: 소스의 평문 제거 → 환경변수 `UPH_PANEL_ACCESS_CODE`(허브가 개발 PC는 `UPH 시스템/.env`, exe는 DPAPI 저장값으로 채움). 단독 실행 시 옆 `.env`에서 직접 읽음. 설정이 없으면 절대 열지 않음. 비교는 `hmac.compare_digest`.
2. `hub/secrets.py`: `UPH_PANEL_ACCESS_CODE` 항목 추가, `uph_panel` 필수 항목에 포함 → exe PC는 처음 열 때 1회 입력.
3. `UPH 시스템/watchdog_agent.py`: stdout/stderr를 UTF-8(errors=replace)로 재설정 — cp949 콘솔 핸들러의 `UnicodeEncodeError` 경고 홍수 제거(재현: 수정 전 stderr 509바이트 → 수정 후 0).
4. `UPH 시스템/uph_download_macro.py` (AX-20261017-01 미해결 2건)
   - 재확인 일정: 마지막 재확인 조회(배송일)까지 시작해야만 3.5일 미룸.
   - `UPH_EXHAUSTED_LOOP_INTERVAL_SEC`·`UPH_REFRESH_AFTER_SEC` 검증(비숫자·0·음수 → 기본값, 늘림 간격은 최소 평소 간격 90초).
   - (AX-20261021-01 포함분) WMS 탭 선택·다운로드관리자 창만 정리·"이지WMS" 제목 인정.

## 수용 기준
- 기존 테스트 전부 통과, 새 테스트는 수정 전 코드에서 실패.
- 저장소 소스에 접근 코드 평문 없음(이력에는 남음 — 사용자에게 코드 변경 권고).
- 운영 PC(.env)에서는 기존 코드로 그대로 입장 가능.

## 운영 반영 주의
- 제어판(`uph_control_panel.py`)·`hub/secrets.py` 변경은 **허브 재시작 후** 적용(허브가 모듈을 한 번만 import). 매크로·watchdog 변경은 제어판에서 재시작하면 적용.
- 범위 밖: Supabase 해지(외부 계정 작업 — 사용자 직접).
