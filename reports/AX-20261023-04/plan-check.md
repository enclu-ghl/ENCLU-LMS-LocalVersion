# AX-20261023-04 — 지시서(설계 초안 v0) 검증 (Claude)

## 확인한 것 (실제 실행)
- 인용한 코드 위치 17곳을 `grep`으로 대조 → **전부 일치**
  - `file_splitter_gui.py`: `read_wms_excel:513`, `consume_batch_codes_atomic:264`, `append_batch_usage_log:349`, `revert_batch_usage:367`, `_call_excelapi:653`, `classify_orders:931`
  - `박스추천프로그램/main.py`: `load_combination_boxes:110`, `load_products:187`, `find_best_box_and_layout:331`, `process_excel_matching:460`, `process_pdf_invoice:609`
  - `matching_macro.py`: `process_one_matching_item:599`, `run_matching_macro:859`
  - `watchdog_agent.py`: `merge_duplicate_rows:351`, `push_to_db:540`
  - `app.py`: `alloc_load_zone_map:336`, `uph_get_order_counts:643`
  - `boxrec_dump.sql`: `box_combinations:30`, `products:41`
- "합포 = 장바구니번호 **행 수** 2 이상" 주장: `file_splitter_gui.py:958-959` (`value_counts()` → `counts >= 2`)로 확인. 수량 2개짜리 1행은 합포가 아니고, 주소가 달라도 같은 장바구니면 합포로 묶인다 → 새 시스템이 이 분류를 확정 규칙으로 쓰면 안 된다는 지적이 맞다.
- `_call_excelapi`가 외부(`api.excelapi.org`)로 이름을 보낸다는 점 확인 → 새 시스템에서는 개인정보를 외부로 보내지 않는다는 원칙이 타당하다.
- 공개 저장소 점검: IP·DB 접속 주소·비밀번호·실제 거래처명 없음. 외부 링크는 공개 제품 문서(Zebra·택배API·이지어드민 안내)뿐이다.

## 판정
| 항목 | 판정 | 사유 / 수정 |
|---|---|---|
| UPH 로그와 분리한 신규 출고 원장(`ship_*`) | 채택 | `order_status_log`는 수집 로그라 상태를 덮어쓰면 UPH 집계가 깨진다 |
| 송장 발급 전에 내부 `package_id` 부여 | 채택 | 재출력·취소·부분출고를 송장번호와 떼어서 추적할 수 있다 |
| 기존 테이블은 읽기 전용으로 참조 | 채택 | 피킹존(`alloc_*`)·박스(`box_combinations`)만 읽는다 |
| 택배는 어댑터로 분리하고 계약을 확인한 뒤 선택 | 채택 | 질문 1의 답이 없으면 정할 수 없다 |
| 중앙 서비스 + 영속 작업 큐 + 출력 작업자 | **수정 채택** | 방향은 맞지만 1차에는 무겁다. 큐는 별도 제품 없이 PostgreSQL 테이블(`ship_print_job`, `SELECT … FOR UPDATE SKIP LOCKED`)로 시작한다. 중복 발급 방지는 앱 로직보다 **DB 유일 제약(포장당 유효 송장 1건, 멱등 키)**을 먼저 둔다 |
| Streamlit을 관리자 화면 후보로 | 채택(조건부) | 재실행 특성 때문에 발급·출력 버튼을 Streamlit에 직접 두지 않는다는 제안이 맞다(재고조사 작업에서 이미 겪은 문제). 검수 스테이션은 스캐너 입력이 빠른 별도 화면(웹 또는 exe)으로 정하고, 기술은 질문 3의 답을 들은 뒤 결정한다 |
| `/api/v1/shipping` API 목록 | 보류 | 서비스 기술(예: FastAPI)이 정해지기 전에는 초안으로만 둔다 |
| 인수시험 C (중복 출력·동시성·권한·장애) | 채택 | 재고조사 때 쓴 임시 PostgreSQL 흐름 시험 방식으로 그대로 검증할 수 있다 |
| 단계 0~6, 수치 목표 미기재 | 채택 | 근거 없는 처리량을 넣지 않은 점이 맞다 |

## 다음 단계
- 사용자 답변(§6 질문 5개)을 받고 v1 설계를 만든다. 특히 1·2·3번이 정해져야 택배 방식과 스테이션 기술을 고를 수 있다.
- 답변 전에는 코드를 작성하지 않는다. 운영 DB에 `ship_*` 테이블을 만들 때는 별도 승인과 백업이 필요하다.

## 미검증
- 이지어드민 공식 API 이용 가능 여부, 택배사 API 제공 여부와 요금: 공개 안내만 확인했고 실제 계약은 확인하지 못했다
- 라벨 프린터와 Zebra Browser Print 호환: 기종을 몰라 확인하지 못했다
