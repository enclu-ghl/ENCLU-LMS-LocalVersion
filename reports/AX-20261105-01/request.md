# AX-20261105-01 요청 — 데이터 정정 페이지 (직원이 직접 수정 + 변경 이력)

## 목적 (사용자, 2026-11-05)
숫자가 틀렸을 때 지금은 DB를 직접 고치거나 Claude에게 말해야 해서 직원이 못 고친다.
직원이 웹앱에서 직접 작성·수정할 수 있는 정정 페이지를 만든다.

## 범위 (사용자 선택)
1. 인원 기록 `manpower_log` — 동·업무일별 시작/변경/중지/마감 이벤트의 시각·인원. 마감 누락 보완(행 추가), 잘못 누른 행 삭제·수정.
2. UPH 일별 요약 `uph_historical_summary` — 날짜·동별 완료 건수·주문 수·인원·UPH·시작/종료 시각. (현재는 엑셀 업로드·자동 채우기만 있고 행 단위 수정 화면 없음)
3. 판매처→동 매핑 `sales_channel_dong_mapping` — 화면 있음(app.py "⚙️ 판매처 매핑 관리"), 변경 이력 없음.
4. 피킹존 로케이션 `alloc_picking_zone` — 화면 있음(app.py "🗺️ 피킹존 로케이션 관리", 쓰기는 `alloc_bulk_upsert_zone` 한 경로), 변경 이력 없음.

## 제약·결정
- 계정(로그인)은 **나중에** 한다(사용자 결정). 지금은 수정 시 **수정자 이름 입력 필수** + 사유(선택) → 변경 이력 표에 남긴다. 나중에 계정이 생기면 이름 대신 계정 id로 바꿀 수 있게 설계.
- 변경 이력: 표·행 키·변경 전/후 값(JSON)·수정자·사유·시각. 이력은 삭제하지 않는다.
- 운영 DB = 서버 PC 로컬 PostgreSQL(`enclu_scm`). 표 소유자는 웹앱 계정 `enclu_app`. 스키마 변경은 백업(pg_dump) 후, 시험 실행(ROLLBACK) 후 적용.
- FK 현황(2026-11-05): manpower_log.dong·uph_historical_summary.dong·sales_channel_dong_mapping.dong → uph_dong_code, alloc_picking_zone.product_code → scm_product. 정정 화면의 동 선택은 코드 표에서 읽는다.
- 피킹존 쓰기는 반드시 `alloc_bulk_upsert_zone`(상품 마스터 동기화 포함)을 거친다.
- UPH 인시 계산 `uph_calc_man_hours`(app.py)는 event_time 순으로 계산하며 마감/중지는 인원 0 취급. 정정 후 해당 날짜 UPH가 어떻게 바뀌는지 저장 전 미리보기가 있으면 좋다.
- 수기 입력 요약행은 `start_time`이 있는 행(`_MANUAL_SUMMARY`) — 자동 채우기(dong_summary_fill)가 덮어쓰지 않음. 정정 화면에서 자동 행을 고치면 다음 월 정리 때 덮어써질 수 있는 점을 처리해야 함.
- 메뉴 문자열은 기존 것을 바꾸지 않는다(새 메뉴 추가만). 대량 쓰기는 일괄 처리. Streamlit 1.64(`width="stretch"`).
- watchdog(UPH 수집기)는 이 표들 중 매핑만 읽는다(메모리 캐시) — 매핑 변경 반영 시점 안내 필요.

## 지시서에 필요한 것
변경 이력 표 DDL, 화면 구성(어느 시스템 메뉴에 둘지), 표별 수정 흐름과 검증 규칙, 기존 화면(매핑·피킹존)에 이력 남기기를 붙이는 위치, 테스트 계획, 롤백.
