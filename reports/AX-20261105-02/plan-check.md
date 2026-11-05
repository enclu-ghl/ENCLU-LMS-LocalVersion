# AX-20261105-02 plan-check (Claude, 2026-11-05)

참고: 지시서 3-2 끝과 3-3 일부가 일본어로 작성됨(Codex 출력 이상). 내용은 이해 가능해 그대로 검증했다.

## 사실 확인 (운영 DB, 2026-11-05)
- equipment_items 1 · supply_items 0 · supply_check 0 · supply_receipt 0 · packaging_materials 23(name UNIQUE, id integer) — 이전할 소모품 데이터 없음.
- supply_check.counted_qty/prev_qty/used_qty = integer, supply_items.current_qty = numeric.
- packaging_materials는 무게구간 화면(등록·수정·삭제)과 weight_calc_results.packaging_name(이름 문자열)이 참조.

## 판정
| 항목 | 판정 | 근거·조치 |
|---|---|---|
| supply_items에 item_kind(소모품/포장재) + packaging_material_id(FK·UNIQUE) | 수용 | 포장재 이름은 마스터에서 JOIN. 포장재 행은 name 미사용 |
| is_active, reorder_qty(표준 발주량), lead_time_days | 수용 (질문 3) | 선택 입력. 미설정이면 권장 주기 "발주량 설정 필요" |
| 품목 수정에서 재고 직접 덮어쓰기 제거 → 입고/실사 체크로만 | 수용 | |
| 입고·체크·제작에 request_id UNIQUE | **거부** | 기존 화면의 저장 후 입력 초기화(clear_inputs)+rerun 패턴 유지. 과함 |
| 과거 체크 수정·감사 이력·후속 구간 재계산 | **보류** | 현재 체크 수정 기능 자체가 없음. 잘못된 체크는 삭제 후 재입력으로 충분 — 필요해지면 AX-20261105-01 이력표에 붙여 별도 작업 |
| 제작 박스 표 | **수정** | `made_box_stock`(박스명·위치·파렛트 수량 numeric·최소 재고선·is_active) + 기록 표 하나 `made_box_log`(구분 제작/조정·수량 증감·기록자·메모·시각). 조정 표를 따로 두지 않음. 0.5파렛트 허용(질문 1). 제작 수량만 제작 주기에 사용 |
| 포장재 이름 변경·삭제 보호 | 수용 (질문 5) | 재고 연결(FK)이 있으면 삭제 차단, 계산 결과에 쓰인 이름은 변경 차단 + 안내 |
| 분석 산식(가중 일평균 = ΣU/ΣD, 입고일 간격 평균, 권장 주기 = Q/v) | 수용 | 기존 supply_consumption_stats와 비교해 같은 정의로 정리. 입고 간격은 "실제 입고 간격(발주 간격 대용)"으로 표기(질문 4) |
| 기본 소비 분석 = 최근 체크 6건 | 수용 | |
| 정수 수량 (질문 2) | 수용 | 기존 체크 컬럼이 정수 |
| 메뉴 | 수용 | 기존 5개 문자열 유지, 화면 안 탭으로 소모품/포장재 분리, 새 메뉴 "🏭 제작 완료 박스 관리" 끝에 추가 |
| 격리 DB 백업 복원 시험 | 수정 | 앱 계정 CREATEDB 없음 → 운영 DB 트랜잭션 시험 후 ROLLBACK + pg_dump 백업 |

## 사용자 추가 요구 (2026-11-05, 지시서 이후)
- 비품 **구매일**: 정확히 확인하기 어려움 → 빈 값이면 기본값 **2026-01-23**(고양 창고 이동일). DB 컬럼 DEFAULT도 같은 값으로, 화면에서 비워 두면 이 값으로 저장.
- 비품 **구매가**: 지금 다 찾기 어려움 → **NULL 허용**, 화면에서 비우면 NULL(현재 화면은 숫자 입력 기본 0이라 0원으로 저장되는 문제).
- 현재 DB: purchase_date·purchase_price 모두 이미 NULL 허용 컬럼. 기존 비품 1행의 구매일이 비어 있으면 2026-01-23으로 채우는지는 적용 전 행 값 확인 후 보고.
