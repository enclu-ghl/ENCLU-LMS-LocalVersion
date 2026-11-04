# AX-20261102-01 review-check (Claude, 2026-11-04)

대상: Codex `review.md` (웹앱 `app.py` B·C단계 변경 + `migration_bc.sql`).

| # | 지적 | 판정 | 근거·조치 |
|---|---|---|---|
| 1 | [높음] 피킹존 INSERT 후 상품 마스터를 만들어, D단계 피킹존→상품 FK(즉시 검사) 적용 시 신규 상품 등록 실패 | **타당** (현재는 FK 없어 잠재 위험) | `alloc_sync_product_master()` 호출을 피킹존 upsert **앞**으로 옮김(전체 대체 시 DELETE 다음). 시험: TEMP 표에 같은 FK를 걸고 새 상품코드 등록 → 성공(test_8) |
| 2 | [중간] 두 연결이 같은 신규 옵션을 다른 상품에 동시에 붙이면 둘 다 `confirmed`로 남을 수 있음 | **타당** (피킹존 편집자는 사무 인원 소수라 발생 가능성은 낮음) | 동기화 시작 시 `pg_advisory_xact_lock(hashtext('scm_product_master_sync'))`로 마스터 동기화 전체를 직렬화. READ COMMITTED에서 뒤 트랜잭션은 잠금 획득 후의 문장에서 앞 트랜잭션 커밋 행을 봄. **동시성 재현 시험은 못 함**(TEMP 표는 세션 전용이라 두 연결이 공유 불가, 운영 표에 시험 쓰기는 하지 않음) |

## 실행한 테스트
- 실제 PostgreSQL(운영 서버, 운영 표를 복사한 TEMP 표, 끝에 ROLLBACK) 8건 통과: 신규 상품 / 옵션 변경 시 이전 옵션 비활성 / 빈 상품명·옵션은 마스터 유지 / 같은 옵션 두 상품 → ambiguous, shared는 유지 / 전체 대체해도 마스터 유지 / 3,000행 일괄 / 피킹존→상품 FK 상태에서 신규 등록 / 운영 표 무변경.
- 가짜 연결 4건 통과: 호출 순서 DELETE→동기화→청크 upsert→commit 1회, 실패 시 rollback.
- 시험 포트(8599)로 웹앱 실행: 홈, UPH 전체 현황(A·B·F 카드·UPH), 판매처 매핑(A 12·B 6·F 4 탭) 정상 표시 — 동 목록이 새 표에서 읽힘.
- `py_compile`, 기존 `tests/` 통과. 실행 후 운영 표 행수 확인(scm_product 3,595 · 옵션 3,551 · 피킹존 3,595).

## 못 한 테스트
- 동시 등록 경합 재현, 재고할당 화면에서의 실제 피킹존 업로드·단건 등록·수정(운영 데이터 쓰기라 사용자 확인 후).

## plan-check 정정
- 수정 4(신규 표 GRANT): 운영 DB의 표 24개 소유자가 웹앱 계정이고 새 표도 같은 계정으로 만들었으므로 웹앱용 GRANT 불필요. watchdog 계정(`scm_uph`)은 새 표를 쓰지 않음.

## 운영 DB 적용 기록 (2026-11-04, 사용자 승인 "다른 프로그램에 문제 없으면 진행")
- 다른 프로그램 영향 확인: 새 표·대상 표를 쓰는 다른 프로그램 없음(watchdog은 `sales_channel_dong_mapping` 읽기만).
- 백업: `pg_dump -Fc` 22.9MB, `pg_restore -l`로 표 24개 확인(백업 폴더, 파일명 `enclu_scm_pre_AX-20261102-01_*`).
- `migration_bc.sql`을 같은 트랜잭션으로 먼저 실행 후 ROLLBACK(시험) → 결과 확인 후 COMMIT.
- 결과: uph_dong_code A/B/F, alloc_dong_code C/D/F, scm_product 3,595, scm_product_option confirmed 3,549 · shared 2(바노바기 시딩), 고아 참조 0(피킹존→상품, 매핑→동, 할당 행→동), 출고 요약 옵션 1,949종 상품 연결 가능.
- 피킹존 05131(스타일셀러 사본) 1행 삭제(사용자 지시). 다른 기존 표 행수 무변화.
