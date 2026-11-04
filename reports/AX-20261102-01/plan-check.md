# AX-20261102-01 plan-check (Claude, 2026-11-02)

근거: 코드 대조(`웹으로 진행 중인 건/app.py`, `UPH 시스템/watchdog_agent.py`), 운영 DB 읽기 전용 조회(`default_transaction_read_only=on`), 챗봇 폴더 검색.

## 인용 검증
- app.py 줄 인용 14곳(327·348·370·377·609·638·652·693·1253·5005·5014·5065·5080·6868·6923·6996·7010) 모두 실제 내용과 일치.
- watchdog 189~214 `DongMappingCache` 일치: 갱신 실패 시 기존 매핑 유지, 빈 결과는 빈 매핑으로 교체(이미 그렇게 동작).
- 운영 DB: PostgreSQL 16.15, public 스키마 사용자 트리거 0·뷰 0, `sku_daily_shipment.product_code` 컬럼 주석 없음.
- 권한: 테이블 권한 보유 역할 `enclu_app`(웹앱)·`scm_uph`(watchdog)·`scm_box`·`scm_splitter` — **지시서에 신규 표 GRANT가 빠져 있음**(아래 수정 4).
- 챗봇(`SCM-AX-챗봇/`): `sku_daily_shipment`·`order_status_log`는 설계 문서에만 나오고 코드 사용처 없음 → 이름 변경 보류(주석만) 판단은 유지하되 "챗봇 미확인" 위험은 해소.

## 사실 정정
- **옵션 중복은 2종(4행)**이다. 요청서의 "3건"은 빈 문자열 옵션 묶음까지 센 값. 빈 옵션 44행은 별도(매핑 대상 제외).

## 항목별 판정
| # | 지시서 항목 | 판정 | 근거 |
|---|---|---|---|
| 1 | 동 표 2개 분리(`uph_dong_code`/`alloc_dong_code`), F동 동일 건물로 간주 안 함 | **수용** | 두 체계 값이 다르고(A/B/F vs C/D/F, 판매처 기준 vs 로케이션 기준) 같은 컬럼명 FK로 섞이면 오연결. `alloc_dong_of()`가 `{첫글자}동`이 목록에 있는지로 판정하므로 코드 표에 접두 컬럼이 따로 필요 없음 |
| 1-1 | 할당 동 색·이모지 제안값 | 수용(표시 변경 없음) | 현재 할당 화면은 동 색을 쓰지 않음 — 값은 저장만 |
| 2 | 판매처 매핑 `is_active` + watchdog `WHERE is_active` 필터 + 삭제→비활성화 | **거부(보류)** | 매핑은 이력이 아닌 설정값이고, 과거 로그는 `dong` 문자열을 이미 갖고 있어 매핑 물리 삭제로 잃는 것이 없음. 반면 이 변경은 가동 중인 수집기(watchdog)·두 저장소 동시 배포를 요구해 위험 대비 이득이 작음. 매핑→동 FK(RESTRICT)는 물리 삭제와 무관하게 동작 |
| 3 | 상품 마스터 새 표(`scm_product` + `scm_product_option` N:M) | **수용** | 피킹존은 위치 생명주기(전부 지우기)와 묶여 있어 마스터로 승격하면 상품이 함께 지워짐 |
| 3-1 | 백필 시 단일 대응도 전부 `pending`, `confirmed`만 연결에 사용 | **수정** | 3,550여 옵션을 사람이 일일이 확정해야 연결이 시작돼 사실상 쓸 수 없음. 단일 대응은 `confirmed`(출처 `alloc_picking_zone_initial`), 중복 2종만 `ambiguous` |
| 4 | 피킹존 `is_active`(소프트 삭제)·개별 삭제→비활성화 | **보류** | 상품 정보가 `scm_product`에 남으면 피킹 위치 행은 물리 삭제해도 상품을 잃지 않음. 조회 함수 전부에 필터를 넣는 변경 범위 대비 이득 작음 |
| 4-1 | "전부 지우고" 삭제·업로드 원자성 | **수용 — 선행 구현함** | 실제 버그 확인: app.py 6866~6874에서 DELETE를 먼저 커밋하고 upsert를 따로 실행 → upsert 실패 시 피킹존이 빈 채로 남음. 스키마 변경 없이 고칠 수 있어 먼저 반영(아래) |
| 5 | `sku_daily_shipment.product_code` 이름 유지 + COMMENT | 수용 | app.py·watchdog INSERT/충돌키 사용처 다수, 챗봇 코드 사용 없음 |
| 6 | FK 대상: 매핑→uph 동, 옵션→상품, 피킹존→상품. 로그·집계 표 FK 없음 | 수용 | watchdog 쓰기 경로에 FK를 걸면 미등록 값 하나로 청크 저장 실패. `NOT VALID`가 신규 쓰기를 막지 않는다는 설명 정확 |
| 6-1 | 22행·3,596행 표에 `NOT VALID` → `VALIDATE` 2단계 | 수정(단순화) | 표가 작아 일반 `ADD CONSTRAINT`로 충분. 잠금 시간 제한(`lock_timeout`)만 유지 |
| 7 | 범위 제외(products·inventory_master·stock_count·invalid_scan, ship_*) | 수용 | 전부 0행 |
| 8 | NULL 동 5행 자동 보정 안 함 | 수용 | 2026-10-06 매핑 없는 판매처 1곳. 별도 확인 후 보정 |
| 9 | 테스트 계획 | 수용 | 시험 DB 복원 확인은 승인 단계에서 |

## 수정 사항 (구현 시 반영)
1. 2번(매핑 비활성화·watchdog 수정) 제외 → **이번 작업은 웹앱 저장소만 변경**, watchdog 무변경.
2. 백필: 단일 대응 `confirmed`, 중복 2종 `ambiguous`, 빈 옵션 제외.
3. FK는 작은 표라 한 번에 추가(`lock_timeout` 유지).
4. 신규 표 GRANT: `enclu_app`에 SELECT/INSERT/UPDATE(삭제 권한은 주지 않음). `scm_uph` 등 다른 역할은 사용 시점에 추가.
5. 지시서 일부 일본어 문구(초안 제목)는 의미 영향 없음 — 구현 문서에서 한국어로.

## 수정한 실행 순서
| 단계 | 내용 | DB 변경 | 상태 |
|---|---|---|---|
| A | 피킹존 "전부 지우고" 원자성 | 없음 | **구현·테스트 완료(로컬), 운영 반영 전** |
| B | 동 코드 표 2개 + 웹앱 하드코딩(`DONG_LIST`·`DONG_META`·`ALLOC_DONG_LIST`·사이드바 색)을 표 조회로, 장애 시 기존 상수로 대체 | 표 2개 생성 | 승인·백업 대기 |
| C | `scm_product`·`scm_product_option` 생성·백필 + 피킹존 업로드 시 같은 트랜잭션에서 상품·옵션 upsert | 표 2개 생성 | 승인·백업 대기 |
| D | FK 3개(매핑→uph 동, 옵션→상품, 피킹존→상품) + `sku_daily_shipment.product_code` COMMENT | 제약 추가 | C 이후 |

## A단계 구현·테스트 (실행함)
- 변경: `alloc_bulk_upsert_zone(..., replace_all=False)` — `replace_all=True`면 같은 연결에서 DELETE + 일괄 upsert 후 한 번만 commit, 예외 시 rollback. 화면의 별도 DELETE 트랜잭션 제거.
- 테스트(실행): 함수만 AST로 꺼내 가짜 연결로 검증 4건 통과 — 전체 대체 시 DELETE→청크 3개→commit 1회 / 두 번째 청크 실패 시 commit 없이 rollback / 추가 모드는 DELETE 없음 / 빈 추가는 아무것도 안 함. `py_compile` 통과, 기존 `tests/` 통과.
- 실행 못 함: 실제 PostgreSQL에서의 실패 재현(시험 DB 없음), 화면 조작 테스트.
