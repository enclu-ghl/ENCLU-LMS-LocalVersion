# AX-20261102-01 요청 — ERD 개선 (동 코드 → 상품 마스터 → FK) 작업 지시서

배경: 2026-10-26 ERD 정리에서 나온 개선 포인트 중 다음 순서로 진행하기로 함(사용자 제안 수락).
① 동 코드 테이블 → ② 상품 마스터 → ③ FK(외래키) 연결. 운영 DB = 서버 PC 로컬 PostgreSQL(`enclu_scm`, public).

이번 지시서는 **단계별 실행 계획**(DDL 초안·백필·코드 수정 위치·롤백·검증 SQL)을 만든다.
운영 DB 스키마 변경은 지시서 확정 → 사용자 승인 → 백업 후에만 한다(AX_RULES 6장).

## Claude 사전 조사 (2026-11-02, 운영 DB 읽기 전용 조회 — 수치는 이날 기준)
### 실제 FK 현황 (4개뿐)
- alloc_row.session_id, alloc_dong_status.session_id → alloc_session(id) ON DELETE CASCADE
- supply_check.item_id, supply_receipt.item_id → supply_items(id) ON DELETE CASCADE

### 동(dong) — 서로 다른 두 체계가 같은 컬럼명을 씀
| 테이블 | 값(행수) | 정의 위치 |
|---|---|---|
| order_status_log | A동 314,548 · B동 164,277 · F동 129,965 · NULL 5 | watchdog이 sales_channel_dong_mapping으로 판매처→동 배정 |
| sales_channel_dong_mapping | A동 12 · B동 6 · F동 4 | 웹앱 관리 화면 |
| manpower_log | A/B/F | |
| uph_historical_summary | A/B/F (각 35) | |
| alloc_row | C동 945 · D동 903 · F동 413 | 재고할당: WMS 로케이션 맨 앞 영문자로 분류 (`ALLOC_DONG_LIST`, app.py:327) |
| alloc_dong_status | C/D/F | |
- UPH 쪽 동 목록·색은 app.py:609 `DONG_LIST`/`DONG_META`에 하드코딩. watchdog(`UPH 시스템/watchdog_agent.py:190~214`)은 매핑 표를 메모리 캐시.
- NULL 5행: 2026-10-06, 매핑에 없는 판매처 1곳.
- ❓ UPH의 F동과 재고할당의 F동이 같은 건물인지 미확인 → 사용자 확인 질문에 포함할 것.

### 상품 식별 키
- `products`(박스추천) 0행, `inventory_master`·`stock_count`·`invalid_scan` 0행(재고조사 현재 미사용).
- `alloc_picking_zone` 3,596행: product_code(WMS 상품코드, 숫자 5자리, PK) ↔ option_code(판매자옵션코드, 형태 `AAAA99`·바코드13자리 등). option_code 중복 3건.
- `sku_daily_shipment.product_code`(32,194행, 1,928종) = 실제로는 **옵션코드**(`extra_data->>'옵션명'`, app.py SKU_SUMMARY_SQL). 그중 1,900종이 alloc_picking_zone.option_code와 일치, product_code와는 0 일치.
- `alloc_row.product_code` 717종 중 715종이 alloc_picking_zone.product_code에 존재.
- `weight_calc_results.option_code` 90종 중 83종이 alloc_picking_zone.option_code에 존재.
- order_status_log는 product_name(이름)만 컬럼, 코드는 extra_data JSON 안.
- 송장 설계(AX-20261029-01)의 ship_* 표도 관리번호·판매자옵션코드로 상품을 가리킬 예정.

## 지시서에서 반드시 다룰 것
1. 동: 하나의 코드 표에 용도 구분(UPH 출고동 / 재고할당 동)을 둘지, 표 두 개로 나눌지 — 장단점과 추천. 색·이모지·정렬·활성 여부 컬럼. 하드코딩(`DONG_LIST`, `DONG_META`, `ALLOC_DONG_LIST`)을 표 조회로 바꿀 범위와 DB 장애 시 대체값.
2. FK를 어디에 걸지: **수집기(watchdog)의 INSERT를 실패시켜 데이터를 잃을 위험이 있는 곳은 FK 대신 무엇으로 할지**(예: 매핑 표에만 FK, 로그 표는 NOT VALID/검증 쿼리). 60만 행 order_status_log에 제약 추가 시 잠금·시간.
3. 상품 마스터: 새 표를 만들지 vs alloc_picking_zone을 승격할지. 키(WMS 상품코드 vs 판매자옵션코드) 선택 근거, 1:N/N:1 관계, 중복 3건 처리, 마스터를 채우고 갱신하는 경로(누가·언제 업로드), 피킹존 업로드 기능과의 관계.
4. sku_daily_shipment.product_code가 실제로는 옵션코드인 이름 불일치 — 컬럼 이름 변경 여부(챗봇·웹앱·watchdog 사용처 전부 확인) 또는 문서화만.
5. 단계 나누기: 각 단계가 혼자 배포·롤백 가능해야 함. 단계마다 DDL 초안, 백필 SQL, 고칠 코드 위치(파일:줄), 롤백 SQL, 검증 SQL/테스트.
6. 비어 있는 표(products, inventory_master 등)는 이번 범위에서 제외할지.
7. 웹앱 저장소(`웹으로 진행 중인 건/`)는 별도 저장소(enclu-ghl/ENCLU-LMS), UPH watchdog은 본 저장소 — 변경이 두 저장소에 걸치는 순서.
8. 운영 원칙: 물리 삭제 없음, 행 단위 반복 INSERT 금지(일괄 upsert), 비밀값·접속정보 문서 금지, 운영 DB 변경은 승인·백업 후.
9. 사용자에게 확인할 질문 3~5개.
