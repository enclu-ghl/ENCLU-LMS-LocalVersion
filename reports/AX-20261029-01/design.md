# 송장 시스템 설계서 v0.1 (AX-20261029-01)

작성: Claude, 2026-10-30. 근거: `plan.md`(Codex), `plan-check.md`, `sample-waybill-upload.md`, `kse-api-notes.md`, DECISIONS 2026-10-29.
상태 표기: ✅ 확정 · ⏳ 차후 진행(게이트) · ❓ 확인 필요

## 1. 확정된 방향
| 항목 | 내용 |
|---|---|
| ✅ 출력 | A안 — 우리 시스템(웹앱 또는 GUI)이 라벨을 직접 그려 출력 |
| ✅ 등록 | **우리 시스템이 KSE API(createOrders)로 직접 배송등록** (KSE 화면 업로드 대체) |
| ✅ 계정 | 브랜드별 KSE 계정·API 키, 브랜드별 조회 + 전체 통합 조회. 키는 `.env` |
| ✅ 범위 1차 | 일본 배송·KSE만. 배송사 코드 기준으로 확장 가능 |
| ✅ 연결키 | 이지어드민 관리번호 = KSE 목록 L열 판매자코드. 송장번호 = KSE TrackingNo(C열 접수번호, `K`+13자리) |
| ✅ 이지어드민 반영 | KSE 목록 26열 형식, 헤더 없이 엑셀 생성 → 사용자가 업로드 |
| ✅ 출력 횟수 | 송장별 출력 횟수 + 재출력 경고 모달 + 사유. 담당자 식별 불필요 |
| ✅ 라벨 | 커스터마이징 필요(현행 KSE 라벨 L10 기준, 아래 4장) |
| ✅ 배송서비스 | 담당자가 배치(또는 행) 단위로 `KSE`/`KSE Light` 선택. **물량이 많으면 전부 KSE Light**로 일괄 지정 가능 — 규격 초과 Light는 배송사가 KSE로 걸러냄(반대는 안 됨). 기본값은 화면에서 고르고 행별 변경 허용 |
| ⏳ 라벨 배치·크기 | 사용자가 정확한 변경점 공유 예정 |
| ❓ 사은품 | API 등록 시 KSE 기프트 자동 처리 여부 미확인 → 4-2 두 경로 모두 설계, KSE 확인 후 선택 |

## 2. 흐름
```
이지어드민 주문 다운로드(.xls)
 → [가져오기] 파일찢기 정리 규칙 재사용(clean_qoo10 등) + 검증
 → [출력 전 검수] 필수값·중복·시책·라벨 미리보기
 → [KSE 등록] 브랜드 계정 키로 createOrders (20건 단위, 부분 성공 건별 반영)
 → [라벨 출력] 자체 템플릿, 출력 횟수 기록 / 재출력 모달
 → [이지어드민 엑셀] 관리번호 + 송장번호 → 사용자 업로드
 → [상태 동기화] getOrders / tracking 주기 조회 (삭제·폐기·이슈 감지)
```

## 3. 데이터 모델 (1차, 신규 표 — 운영 DB 생성은 구현 단계에서 승인·백업 후)
| 표 | 핵심 컬럼 |
|---|---|
| `ship_account` | account_id PK, carrier_code(`KSE`), brand, kse_seller_id, env_key_name(키 이름만), active |
| `ship_import_batch` | batch_id PK, account_id, 원본 파일 해시, 업로더 입력명, 시각, 행수·오류수 |
| `ship_order_line` | line_id PK, batch_id, account_id, **관리번호**, 주문번호, 장바구니번호, 판매자옵션코드, 상품명, 수량, 금액, 수취인 정보(원본 문자열) |
| `ship_waybill` | waybill_id PK, account_id, **tracking_no(text)**, package_no(장바구니), generation(세대), status(KSE 상태코드), local_company, local_tracking_no, region, 등록·동기화 시각, active |
| `ship_waybill_line` | waybill_id, line_id, item_type(main/set/gift/seeding) |
| `ship_print_log` | id PK, waybill_id, 출력 시각, 출력 위치/프린터(자유 텍스트), is_reprint, reason_code, counted(bool) |
| `ship_reprint_reason` | reason_code PK, 이름, 장소(동/사무), counted 기본값 — 값은 ⏳ |
| `ship_promo_rule` | rule_id PK, brand, 기간, 유형(전체/금액/수량/코드), 조건 코드, 증정 코드, 한정 수량 — ⏳ |
| `ship_sync_event` | id PK, waybill_id, 이전→이후 상태, 출처(API/엑셀), 시각 |

제약: UNIQUE(account_id, tracking_no, generation) · UNIQUE(account_id, package_no) where active · 이력 물리 삭제 금지 · 일괄 upsert(행 단위 INSERT 금지).

## 4. 라벨 (현행 KSE L10, 90×60mm, 표본 PDF 1장)
현행 라벨 구성(위→아래):
1. 주문번호 / 장바구니번호 (n/m)
2. 배송서비스(`KSE`/`KSE Light`) 크게 + **TrackingNo CODE128 바코드**와 숫자, 우측 `L10-3`
3. 상품 줄: `[순번] [로케이션] 상품명 … 수량` — 사은품 줄 포함 (로케이션 예: `FE-06-02-01`)
4. 하단: 브랜드 법인명 · 마켓 표시명(큐텐) · 페이지(1/1) · 날짜 · 지역 박스(`E`/`W`) · 마켓 로고(qoo10jp) · KSE Express

수취인 주소가 없는 **출고·입고용 라벨**(현지 택배 라벨은 KSE가 별도 부착하는 것으로 보임 ❓) → 자체 제작 부담이 상대적으로 작음.
- 로케이션은 우리 `alloc_picking_zone`(상품코드→로케이션)으로 채울 수 있음.
- ⏳ 커스터마이징 항목·배치: 사용자와 확정. 60×40 라벨, A4 4장형·8장형 템플릿도 같은 데이터로.
- ❓ KSE 창고가 자체 라벨 바코드(CODE128 TrackingNo)를 그대로 읽는지, `L10-3`의 의미.

### 4-1. 출력 방식
- 프린터: XP-D4601B, XP-DT427B, TTP-384MT (사무동 XPRINT 8·TSC 2, 동별 XPRINT 1).
- 1차 후보: 서버가 라벨 PDF(90×60 등 정확한 mm 크기) 생성 → 출력 PC에서 인쇄. 직접 명령(TSPL 등)·로컬 출력 에이전트는 시험 후 결정 ⏳.

### 4-2. 사은품(시책) — 두 경로
- **경로 A (KSE 결과 확인):** KSE가 기프트를 붙이면, 등록 후 getOrders로 GoodsList의 gift 행을 받아 시책 규칙과 대조.
- **경로 B (우리가 직접 적용):** 등록 요청에 `ItemType=gift` 행을 우리가 넣음 → 시책은 "검증"이 아니라 "적용 + 적용 결과 기록".
- ❓ KSE에 확인 후 선택. 어느 쪽이든 `ship_promo_rule`(구조화된 시책 등록) 필요.

## 5. 동기화·예외
- 등록: 같은 장바구니번호 재등록은 KSE가 9903014로 거절 → 이중 발급 방지. 응답 단절 시 getOrders로 확인 후 재시도.
- 부분 성공(9903010): 건별 결과로 성공만 반영, 실패는 사유와 함께 재처리 목록.
- 삭제·재등록: API 없음. getOrders "결과 없음"이면 비활성 후보(❓ 테스트서버로 동작 확인). 재등록 시 새 세대, 이전 출력 이력 보존.
- 취소: OMS 삭제 반영만. 반품은 범위 밖.
- 이슈: getIssueOverview로 통관 보류·파손 등 일 1회 요약(2차).

## 6. 단계와 게이트
| 단계 | 내용 | 시작 조건(게이트) |
|---|---|---|
| 0 | 설계 확정 | ✅ 진행 중 |
| 1 | 가져오기·검수·라벨 미리보기·이지어드민 엑셀 (API 없이 KSE 목록 엑셀로) | 라벨 커스터마이징 항목 확정 |
| 2 | KSE API 등록·조회 | ⏳ **테스트서버 계정·API 키 준비** (사용자 진행 예정) |
| 3 | 직접 출력·출력 횟수·재출력 모달 | 프린터 1대 시험 출력 |
| 4 | 시책 규칙 등록·대조 | ⏳ KSE 사은품 처리 방식 회신, 재출력 사유 기준 |
| 5 | 실서버 전환, 브랜드 계정 확대, 다른 배송사 | 2~4 운영 검증 |

## 7. 남은 확인 (❓)
1. KSE: API 등록 시 기프트 자동 처리 여부 / 자체 라벨 인정 여부·필수 항목 / OMS 삭제 건의 getOrders 응답 / 삭제 후 같은 장바구니번호 재등록 가능 여부.
2. 사용자: 라벨 배치·크기 변경점(공유 예정), 재출력 사유·카운트 기준, 무게·원산지 기본값(이지어드민 원본에 없음).
3. KSE 문의 초안: `kse-inquiry-draft.md` (미발송, 사용자가 직접 발송). Light→KSE 변경 시 TrackingNo 유지 여부도 포함.
