# AX-20261023-05 — UPH 팝업3(SweetAlert) 반복 실패 원인 수정 (긴급, Claude 직접)

## 증상
- 10/22 09:01~09:25, 10/23 11:15~11:28, 10/23 13:15~13:27: 팝업3 '다운로드 안내' 대기 45초 초과로 회차 연속 실패. WMS 탭 새로고침 3회로도 회복 안 됨. 허브 재시작이나 시간이 지나면 회복.

## 원인 (실측, 읽기 전용 CDP로 확인)
- 실패 중 DOM: `#swal2-input`은 있고 표시 상태지만 부모 `.swal2-popup`이 `opacity: 0` (`swal2-no-transition`) — 등장 애니메이션 첫 프레임에 멈춤.
- 크롬 창이 가려진 상태에서 렌더링이 멈춰 프레임이 진행되지 않음. CDP `Page.captureScreenshot` 1회 호출 직후 `opacity: 1`이 되었고, 같은 회차의 다음 시도가 팝업3을 1초 만에 통과(13:27:50).
- 8월 주석의 "서버가 요청을 씹어 팝업이 안 뜬다"는 추정은 틀렸던 것으로 보인다.

## 수정
1. `uph_download_macro.py`: `wait_visible_forcing_paint()` 추가 — 3초 간격으로 보임 여부 확인, 안 보이면 `Page.captureScreenshot`(jpeg q10)으로 프레임을 강제. 팝업3 대기에 적용.
2. `uph_control_panel.py`: 디버그 크롬 실행 옵션에 `--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`, `--disable-background-timer-throttling` 추가(다음 크롬 실행부터).
3. 테스트: 강제 그리기 대기 2건 추가, 실제 .env 웹훅 주소에 영향받던 기존 테스트를 빈 폴더 기준으로 격리.

## 검증
- 단위 테스트 86개 통과.
- 실제 매크로 적용은 제어판 정지→시작(매크로 재시작) 후 확인 필요. 크롬 옵션은 크롬 재실행 후 반영.
