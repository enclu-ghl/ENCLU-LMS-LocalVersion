# KSE OMS API 정리 (2026-10-30, 사용자가 붙여 준 가이드 본문 기준, 문서 버전 1.6.0)

## 공통
- 실서버 / 테스트서버 분리. 테스트서버는 자동 승인, 데이터 비정기 삭제, 상태가 30분 간격으로 자동 진행 → **개발·시험은 테스트서버로.**
- 인증: HTTP 헤더 `KSE-APIKey` 하나. 키 값은 `.env`에만.
- **셀러(브랜드)별 키 필수**: 여러 셀러를 관리하는 포워더·파트너 키로는 배송등록 불가(9903020/9903021) → 브랜드 계정마다 키 등록 설계 확정 근거.
- 시간대 UTC+09:00 고정.

## 엔드포인트 (`POST /v1/{api}/kr`)
| API | 용도 | 입력 | 한도 |
|---|---|---|---|
| createOrders | 배송등록(송장 발급) | JSON `DataList`(패키지) → `GoodsList`(상품) | 1회 500, 권장 20 |
| getOrders | 배송등록 조회 | KSE 송장번호(TrackingNo) 쉼표 목록 | 1회 500, 권장 20 |
| tracking | 배송추적 | TrackingNo 목록 | 1회 20 |
| createCustomerService / getCustomerService | CS 등록·조회 | TrackingNo 1건 | 다중 조회 불가 |
| getIssueOverview | 화물 이슈 현황 | 날짜 기준·기간(최대 100일) | |
| getInventory | 3PL 재고 | Qoo10 코드 | 해당 없음 |

## 설계에 영향 주는 사실
1. **출력용 송장 API 없음** — PDF·이미지·프린터 명령을 주는 API가 없다. 송장 라벨은 우리가 템플릿으로 그려야 함.
   TrackingNo(K+13자리)는 물류창고 입고용 **CODE128 바코드**. 응답에 현지 택배사(`LocalTrackingCompany`: JP_SAGAWA·JP_YAMATO·JP_NEKOPOS·JP_UPACK)와 현지 송장번호(`LocalTrackingNo`)가 옴.
   → 자체 라벨을 KSE·현지 택배사가 인정하는지, 라벨 필수 항목·양식이 무엇인지 KSE 확인 필요.
2. **목록/검색 API 없음** — getOrders는 송장번호를 알아야 조회 가능. OMS 화면이나 파일 업로드로 등록된 건은 API로 찾을 수 없다.
   → 우리 시스템이 createOrders로 직접 등록하면 송장번호를 모두 알게 됨. 계속 OMS 업로드로 등록하면 KSE 목록 엑셀을 받아 와야 함.
3. **삭제·취소 API 없음** — OMS에서 삭제한 건은 getOrders가 "결과 없음"(9002004/9002006)으로 돌려줄 것으로 추정(테스트서버로 확인 필요). 폐기는 상태 X99.
4. **중복 등록 방지**: 같은 PackageNo(장바구니번호) 재등록은 9903014로 거절 → 재시도해도 이중 발급 안 됨. 단 OMS에서 삭제 후 재등록 시 같은 PackageNo를 다시 쓸 수 있는지는 확인 필요.
5. **부분 성공**: 여러 건 요청 시 일부만 성공하면 9903010 + `Data`/`DataFail`로 건별 결과 → 건별로 반영해야 함.
6. **사은품**: GoodsList의 `ItemType=gift`(Market이 `gift`로 표시되기도 함). 표본 KSE 목록의 gift 행과 일치.
   → API로 등록할 때 KSE의 기프트 처리가 자동으로 붙는지, 우리가 gift를 넣어야 하는지 확인 필요(시책 검증 방식이 달라짐).
7. 등록 필수 항목: PackageNo, DeliveryServiceCode(KSE/KSE Light/SDEX), ToCountry=JP, 수취인 성명·전화·우편번호·주소, RealWeight(kg 소수 3자리), GoodsList(Title, Qty, UnitPrice, Currency, Origin).
   이지어드민 원본 43열과 대응표 필요(무게·원산지·배송서비스는 원본에 없음 → 기본값/상품 마스터 필요).
8. 처리량: 하루 3만 건 ÷ 20건/회 = 1,500회 호출. 호출 간격·소요시간은 테스트서버에서 측정.
