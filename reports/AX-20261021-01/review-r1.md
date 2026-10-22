AX-20261021-01 검토 결과: **높음 1건**입니다.

1. **[높음] 일반 탭을 WMS로 오인하면 복구 과정에서 로그인된 WMS 탭을 닫습니다.**
   - **위치:** `UPH 시스템/uph_download_macro.py:859`
   - **문제:** 제목에 `다운로드관리자`가 없다는 조건만으로 첫 창을 WMS로 선택합니다. 새 탭이나 다른 페이지가 WMS보다 먼저 나열되면, 현재 정상 WMS에 연결돼 있어도 다른 탭으로 이동합니다.
   - **근거:** 잘못 선택한 핸들이 새로고침 대상으로 유지됩니다. 이후 조회 실패로 복구가 실행되면 `PageRefresher._close_other_windows()`가 선택한 탭 외의 창을 모두 닫습니다(`UPH 시스템/uph_download_macro.py:952`, `:977`). 실제 WMS 탭도 닫혀 수집이 중단됩니다.
   - **재현/확인 방법:** 가짜 드라이버의 핸들을 `OTHER, W, MGR`, 현재 창을 `W`, `OTHER` 제목을 `New Tab`으로 설정합니다. `_select_wms_window()` 호출 후 `record_round(False)`와 `maybe_refresh()`를 실행합니다. 메모리에서 직접 실행한 결과는 `selected=OTHER`, `remaining=['OTHER']`, `close_attempts=['W', 'MGR']`였습니다.
   - **제안:** WMS URL·화면 요소 등으로 대상을 명시적으로 확인하고, 확인되지 않으면 `None`을 반환하도록 변경하십시오. 일반 탭이 먼저 나열되는 경우에도 실제 WMS를 선택하고 닫지 않는 회귀 테스트를 추가해야 합니다.

검증 명령 `py -B -m unittest discover -s "UPH 시스템/tests" -p test_uph_download_refresh.py -v`는 **35개 모두 통과**했습니다. 기존 테스트는 위 일반 탭 혼재 상황을 다루지 않습니다.

첨부된 변경 파일 2개, 작업 지시서와 HANDOFF, 관련 창 정리·복구 경로를 검토했습니다. 변경 범위에서 계산 오류·중복 등록·비밀정보 노출은 발견하지 못했습니다. 실제 Chrome/WMS 및 운영 DB의 수집 결과는 미검증입니다. 파일·DB는 수정하지 않았습니다.