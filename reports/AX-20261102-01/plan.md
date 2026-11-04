# AX-20261102-01 — ERD 개선 작업 지시서

## 1. 목적 / 완료 조건

**동 코드 → 상품 마스터 → FK 순서로, 기존 수집·집계·재고할당을 유지하면서 단계별로 적용한다.**

추천 방향은 다음과 같다.

- 동: **UPH 출고동 표와 재고할당 동 표를 분리**한다. 두 체계의 F동은 동일 건물로 간주하지 않는다.
- 상품: **새 상품 마스터와 옵션 매핑 표를 만들고**, `alloc_picking_zone`은 피킹 위치 관리 역할을 유지한다.
- FK: 관리 화면에서 통제할 수 있는 표부터 적용한다. **watchdog이 기록하는 로그·집계 표에는 이번 작업에서 FK를 추가하지 않는다.**
- `sku_daily_shipment.product_code`는 이번에 이름을 바꾸지 않고, **판매자옵션코드라는 의미를 명시**한다.

완료 조건:

1. 동 목록·색·이모지·정렬·활성 여부가 DB 기준으로 표시되고, 장애 시 기존 동작으로 대체된다.
2. 상품 업로드가 상품 마스터·옵션 매핑·피킹 위치를 하나의 트랜잭션에서 일괄 반영한다.
3. 옵션 중복 때문에 출고량·중량 결과가 여러 상품에 중복 합산되지 않는다.
4. 미등록 판매처·상품 때문에 watchdog 수집이 실패하지 않는다.
5. 적용 전후 기존 행수·집계값·할당 출력 결과가 유지된다.
6. 단계별 배포·롤백·검증 기록이 남는다.

**현재는 지시서 작성 단계다. 파일·DB 변경과 테스트 실행은 하지 않았다.** 요청에 적힌 운영 수치는 2026-11-02 Claude 조사 결과이며, Codex가 운영 DB에서 재측정한 값은 아니다. 아래 SQL은 **검증·승인을 위한 초안**이다.

## 2. 영향 파일·함수

아래 위치는 실제 파일을 열어 확인했다. 줄 번호는 현재 로컬 사본 기준이다.

| 위치 | 확인한 내용 / 수정 범위 |
|---|---|
| `웹으로 진행 중인 건/app.py:327` | `ALLOC_DONG_LIST` |
| `웹으로 진행 중인 건/app.py:348` | `alloc_dong_of()` — 로케이션 첫 글자로 분류, 미등록은 `기타` |
| `웹으로 진행 중인 건/app.py:370` | `alloc_load_zone_map()` — 상품코드→피킹 위치 조회 |
| `웹으로 진행 중인 건/app.py:377` | `alloc_bulk_upsert_zone()` — `execute_values` 일괄 upsert |
| `웹으로 진행 중인 건/app.py:609` | `DONG_LIST`, `DONG_META` — 색·연한 배경색·이모지 |
| `웹으로 진행 중인 건/app.py:638` | `SKU_SUMMARY_SQL` — JSON `옵션명`을 `product_code`로 집계 |
| `웹으로 진행 중인 건/app.py:652` | `sku_summary_check()` |
| `웹으로 진행 중인 건/app.py:693` | `sku_summary_fill()` — 요약 보충·정리 |
| `웹으로 진행 중인 건/app.py:1253` | 사이드바 A/B/F 색·순서 하드코딩 |
| `웹으로 진행 중인 건/app.py:5005` | 판매처 매핑 동 선택 |
| `웹으로 진행 중인 건/app.py:5014` | 판매처 매핑 upsert |
| `웹으로 진행 중인 건/app.py:5065` | 판매처 매핑 물리 삭제 |
| `웹으로 진행 중인 건/app.py:5080` | 판매처 동 변경 |
| `웹으로 진행 중인 건/app.py:6868` | 피킹존 전체 물리 삭제 후 별도 호출로 업로드 — 원자성 개선 필요 |
| `웹으로 진행 중인 건/app.py:6923` | 피킹존 개별 추가 |
| `웹으로 진행 중인 건/app.py:6996` | 피킹존 개별 수정 |
| `웹으로 진행 중인 건/app.py:7010` | 피킹존 개별 물리 삭제 |
| `UPH 시스템/watchdog_agent.py:189` | `DongMappingCache` |
| `UPH 시스템/watchdog_agent.py:205` | 매핑 갱신, 실패 시 기존 메모리 매핑 유지 |
| `UPH 시스템/watchdog_agent.py:450` | `process_file()` |
| `UPH 시스템/watchdog_agent.py:479` | 변경 판단 대상은 CS·보류·수량 — 동 변경만으로는 재저장되지 않음 |
| `UPH 시스템/watchdog_agent.py:509` | DB 성공 후 성공한 행만 캐시에 반영하는 순서 |
| `UPH 시스템/watchdog_agent.py:540` | `push_to_db()` |
| `UPH 시스템/watchdog_agent.py:627` | `build_sku_daily_shipment()` — 옵션명 기준 일괄 집계 |
| `UPH 시스템/tests/test_watchdog_read_retry.py:4` | 실제 폴링·파일 재시도 회귀 테스트 구조 |
| `_local_db/next_dump.sql:55` | 피킹존 과거 DDL |
| `_local_db/next_dump.sql:68` | 할당 행 과거 DDL — `dong` 기본값은 `기타` |
| `_local_db/next_dump.sql:503` | 판매처 매핑 과거 DDL |
| `_local_db/next_dump.sql:535` | SKU 집계 과거 DDL |

주의:

- 덤프는 **운영 스키마의 최신 증거가 아니다**. 실제 형식·제약·인덱스·권한은 운영 읽기 전용 조회로 다시 확인한다.
- 챗봇 소스는 현재 조사한 두 저장소에서 확인하지 못했다. **챗봇 경로·SQL·배포 위치는 미확인**이다.
- `ship_*` 구현·실제 DDL은 **미확인**이다. 이번 변경에 송장 표 생성·변경을 포함하지 않는다.
- 새 마이그레이션·테스트 파일의 경로는 **신규 제안이며 아직 존재하지 않는다**.

## 3. 작업 단계

### 0단계 — 지시서 검증·기준선·승인

Claude가 먼저 수행한다.

1. `reports/AX-20261102-01/plan-check.md`에 지시서 항목별 수용·수정·거부와 근거를 기록한다.
2. 두 저장소의 작업 상태·원격 저장소를 각각 확인한다. 접속정보가 출력되는 명령·원문은 보고서에 남기지 않는다.
3. 운영 읽기 전용 조회로 컬럼 형식, PK/UNIQUE/FK, 뷰, 트리거, 실제 DB 버전을 확인한다.
4. 옵션 중복의 정확한 정의와 원본 행을 확인한다. 현재의 “중복 3건”이 코드 수인지 초과 행수인지 구분한다.
5. 챗봇의 위치와 `sku_daily_shipment` 사용 여부를 확인한다. 저장소 검색만으로 모든 소비자를 확인했다고 판단하지 않는다.
6. 단계별 DDL·예상 반영 행수·중단 조건을 확정해 사용자 승인을 받는다.
7. **승인 후, 각 운영 변경 직전에 백업하고 별도 시험 DB 복원을 확인한다.**

운영 쓰기는 이 단계에서 하지 않는다. DDL·백필·권한 부여를 앱 시작 시 자동 실행하는 방식도 금지한다.

공통 실행 원칙:

```sql
-- 운영 DDL 실행 시 트랜잭션마다 적용할 초안
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';
-- 승인된 짧은 DDL
COMMIT;
```

시간 제한은 시험 DB 실측 후 확정한다. 시간 초과·잠금 경합이면 롤백하고 보고한다. 자동 반복하지 않는다.

### 1단계 — 동 코드 표 추가

**두 표 분리를 추천한다.**

| 대안 | 장점 | 단점 |
|---|---|---|
| 단일 표 `(purpose, code)` | 공통 관리·메타데이터 재사용 | 모든 참조에 용도 구분 필요. 단순 `dong` FK로는 체계를 구별하지 못함 |
| UPH/할당 두 표 | 기존 `dong` 값으로 정확한 FK 연결 가능. F동 혼동 방지 | 표·관리 코드 일부 중복 |

현재처럼 의미가 다른 체계이고 기존 소비자가 많다면 두 표가 변경 범위와 오연결 위험을 줄인다. 같은 건물임이 확인돼도 향후 별도 건물 표로 연결하며, 지금 코드를 합치지 않는다.

**DDL 초안:**

```sql
CREATE TABLE public.uph_dong_code (
    code text PRIMARY KEY,
    display_name text NOT NULL,
    color text NOT NULL CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    light_color text NOT NULL CHECK (light_color ~ '^#[0-9A-Fa-f]{6}$'),
    emoji text NOT NULL,
    sort_order integer NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.alloc_dong_code
    (LIKE public.uph_dong_code INCLUDING ALL);
```

**初回シード兼バックフィル:**

```sql
INSERT INTO public.uph_dong_code
    (code, display_name, color, light_color, emoji, sort_order)
VALUES
    ('A동','A동','#e24b4a','#fcebeb','🔴',10),
    ('B동','B동','#378add','#e6f1fb','🔵',20),
    ('F동','F동','#639922','#eaf3de','🟢',30)
ON CONFLICT (code) DO NOTHING;

INSERT INTO public.alloc_dong_code
    (code, display_name, color, light_color, emoji, sort_order)
VALUES
    ('C동','C동','#666666','#f2f2f2','🏠',10),
    ('D동','D동','#666666','#f2f2f2','🏠',20),
    ('F동','F동','#666666','#f2f2f2','🏠',30),
    ('기타','기타','#666666','#f2f2f2','❓',90)
ON CONFLICT (code) DO NOTHING;
```

할당용 색·이모지는 **새 제안값**이다. 사용자 확인 전 기존 화면의 표시를 바꾸지 않는다. 재실행 시 관리자가 변경한 메타데이터를 덮어쓰지 않는다.

**검증:**

```sql
SELECT * FROM public.uph_dong_code ORDER BY sort_order, code;
SELECT * FROM public.alloc_dong_code ORDER BY sort_order, code;
```

**롤백:** 기존 코드가 새 표를 사용하지 않으므로 운영 동작 변화가 없다. 새 표·행은 삭제하지 않고 보존한다. 이 단계에는 기존 로그 백필·재분류가 없다.

### 1-2단계 — 동 조회 전환·매핑 비활성화

선행 DDL:

```sql
ALTER TABLE public.sales_channel_dong_mapping
    ADD COLUMN is_active boolean NOT NULL DEFAULT true;
```

백필은 기본값으로 기존 행을 활성 유지한다. 실제 PG 버전과 기존 컬럼 존재 여부를 확인한 뒤 실행한다.

수정 순서:

1. **본 저장소 watchdog 먼저**: `DongMappingCache.refresh()`에서 `WHERE is_active`를 적용한다. 성공한 조회가 빈 결과이면 빈 매핑으로 교체하고, 조회 실패일 때만 마지막 정상 매핑을 유지한다.
2. 정상 수집을 확인한 후 **별도 웹앱 저장소**를 변경한다.
3. `DONG_LIST`·`DONG_META`·`ALLOC_DONG_LIST` 생성 원천을 캐시된 표 조회로 바꾼다.
4. 사이드바 색·홈 범례·탭·선택지의 A/B/F 고정 목록도 함께 제거한다. `기타`는 할당 예외 버킷으로 별도 표시해 기존 완료 판정 방식을 보존한다.
5. 판매처 매핑 삭제를 `is_active=false`로 바꾼다. 재등록 upsert는 `is_active=true`를 복원한다.

장애 대체 정책:

- 코드 표 조회 실패: 마지막 정상 캐시 → 기존 A/B/F·C/D/F 기본값 순서로 대체한다.
- 미등록 코드 표시: 원래 값을 유지하고 중립 색으로 표시한다. 행을 숨기지 않는다.
- 선택지는 활성 코드만 사용하되, 과거 조회에는 비활성 코드도 표시한다.
- watchdog 시작부터 매핑 조회가 실패하면 임의 동을 배정하지 않는다. 기존처럼 `dong=NULL`을 허용하고 경고한다.
- 동 목록 캐시와 판매처 매핑 캐시는 별개다. **A/B/F 기본 목록으로 판매처 배정을 추정하지 않는다.**
- DB 전체 장애에서는 수집 저장을 성공한 것으로 처리하지 않는다. 기존 재시도·캐시 성공 순서를 보존한다.

**검증:** 코드 표 장애, 빈 매핑, 비활성 판매처, 비활성 동의 과거 조회, 미등록 판매처 파일을 시험 DB에서 확인한다.

**롤백:** 웹앱부터 이전 동 조회 방식으로 복귀한다. watchdog의 `is_active` 필터는 유지해도 된다. 필터까지 되돌리면 비활성 매핑이 다시 적용되므로, 해당 행과 영향을 사용자에게 확인한 후 별도로 복구한다. 컬럼·행은 삭제하지 않는다.

**과거 NULL 5행은 자동 보정하지 않는다.** 매핑 수정만으로 기존 로그가 갱신되지 않는 코드 구조이므로, 당시 판매처의 올바른 동·수정 범위를 확인한 별도 승인 작업으로 분리한다.

### 2단계 — 상품 마스터·옵션 관계 추가

`alloc_picking_zone` 승격은 간단하지만 위치 업로드·삭제와 상품 생명주기가 결합된다. 현재 전체 삭제·개별 삭제 경로도 있으므로 **새 마스터를 추천한다.**

키와 관계:

- WMS 상품코드는 문자열 PK로 사용한다. 숫자 변환·일괄 앞자리 0 제거·5자리 강제 보정은 하지 않는다.
- 옵션코드는 WMS 상품코드와 다른 식별자다.
- WMS 상품 하나에 옵션 여러 개가 올 수 있고, 현재 옵션 중복으로 반대 방향도 유일하지 않다.
- 일단 매핑 표에서 N:M 관계를 보존한다. 업무 확인 없이 옵션을 UNIQUE로 만들거나 임의로 첫 상품을 선택하지 않는다.
- 판매처·브랜드별 코드라면 해당 범위를 매핑 키에 추가해야 한다. 범위가 미확인인 상태에서 자동 상품 연결하지 않는다.

**DDL 초안:**

```sql
CREATE TABLE public.scm_product (
    wms_product_code text PRIMARY KEY,
    product_name text NOT NULL DEFAULT '',
    is_active boolean NOT NULL DEFAULT true,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(wms_product_code) <> '')
);

CREATE TABLE public.scm_product_option (
    wms_product_code text NOT NULL,
    option_code text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    resolution_status text NOT NULL DEFAULT 'pending'
        CHECK (resolution_status IN ('pending','confirmed','ambiguous')),
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (wms_product_code, option_code),
    CHECK (btrim(option_code) <> '')
);
```

FKは3단계에서 연결한다.

**백필 초안:**

```sql
INSERT INTO public.scm_product
    (wms_product_code, product_name, source)
SELECT product_code, product_name, 'alloc_picking_zone_initial'
FROM public.alloc_picking_zone
WHERE btrim(product_code) <> ''
ON CONFLICT (wms_product_code) DO NOTHING;

WITH src AS (
    SELECT DISTINCT product_code, option_code
    FROM public.alloc_picking_zone
    WHERE btrim(product_code) <> '' AND btrim(option_code) <> ''
),
marked AS (
    SELECT *,
           count(*) OVER (PARTITION BY option_code) AS product_count
    FROM src
)
INSERT INTO public.scm_product_option
    (wms_product_code, option_code, resolution_status, source)
SELECT product_code, option_code,
       CASE WHEN product_count > 1 THEN 'ambiguous' ELSE 'pending' END,
       'alloc_picking_zone_initial'
FROM marked
ON CONFLICT (wms_product_code, option_code) DO NOTHING;
```

단일 대응도 원본 업로드 담당자의 확인 전에는 `pending`으로 둔다. `confirmed`만 자동 상품 연결에 사용한다. 옵션 중복 3건은 원본을 보존하고 담당자가 오등록·정상 공유·범위 구분 필요 여부를 판정한다.

미등록 코드 처리:

- 할당의 미등록 WMS 코드 2종은 즉시 FK를 걸어 차단하지 않는다.
- 출고집계 미일치 옵션 28종·중량 미일치 옵션 7종은 검증 목록으로 관리한다.
- `UNKNOWN`, 빈 코드, 상품명만 있는 로그에 가짜 상품을 만들지 않는다.
- 옵션 조인은 매핑 후보 수와 확정 상태를 확인해 하나로 결정될 때만 수행한다.

**검증:** 원본의 유효 WMS 코드·옵션 쌍이 새 표에 모두 존재하고, 두 번 실행해도 행수가 늘어나지 않아야 한다.

**롤백:** 기존 소비자를 그대로 유지하며 신규 표를 사용하지 않는다. 신규 표·백필 행은 보존한다.

### 2-2단계 — 업로드 경로·피킹존·이름 불일치 정리

**DDL 초안:**

```sql
ALTER TABLE public.alloc_picking_zone
    ADD COLUMN is_active boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN public.sku_daily_shipment.product_code IS
'레거시 컬럼명. WMS 상품코드가 아니라 order_status_log.extra_data의 옵션명에서 추출한 판매자옵션코드. 미상은 UNKNOWN.';
```

이번에 `sku_daily_shipment.product_code`를 rename하지 않는다. 양쪽 저장소의 INSERT·충돌키·집계 비교와 미확인 챗봇이 영향을 받기 때문이다. 문서·변수·화면에서 WMS 상품코드와 구분하고 집계식은 유지한다.

상품 갱신 경로:

1. 사용자 지정 상품/전산 담당자가 최초 전체 파일을 업로드한다.
2. 이후 신규 상품·옵션·피킹 위치 변경 시 기존 피킹존 관리 화면에서 파일 또는 개별 수정으로 반영한다.
3. 업로드 누락 상품은 기본적으로 유지한다.
4. 전체 대체는 **피킹 위치만 비활성화**한다. 상품 마스터를 일괄 비활성화하지 않는다.
5. 옵션 변경 시 이전 매핑은 보존·비활성화하고, 이미 승인된 동일 매핑 상태는 유지한다. 새 매핑은 재검증한다.

코드 수정:

- `alloc_bulk_upsert_zone()`의 연결·커밋 경계를 조정해 상품→옵션→피킹존이 **동일 연결·트랜잭션**으로 처리되게 한다.
- 전체 삭제 후 별도 트랜잭션 업로드를 없앤다.
- 개별 추가·수정도 같은 서비스 함수를 사용한다.
- 피킹존 조회는 신규 할당에 활성 항목만 사용한다. 과거 할당 확인에는 비활성 항목을 구분 표시한다.
- 개별 삭제는 비활성화로 바꾸고 기존 행을 유지한다.
- 빈 선택 컬럼 때문에 기존 상품명·옵션이 지워지지 않도록 명시적 삭제와 미입력을 구분한다.
- 행 단위 반복 INSERT를 금지하고 기존 `execute_values` 방식의 일괄 upsert를 유지한다.

**백필:** 기존 피킹존은 모두 활성 유지한다. 상품 본문은 2단계 백필 결과를 사용하며 전체 출고 로그 재작성은 하지 않는다.

**롤백 SQL:**

```sql
COMMENT ON COLUMN public.sku_daily_shipment.product_code IS NULL;
```

기존 주석이 있으면 `NULL` 대신 사전 기록한 원문으로 복구한다. 신규 읽기·이중 쓰기는 기능 설정으로 중단하고 표·컬럼·행은 보존한다. 물리 삭제 UI까지 그대로 되돌리지 말고, 이전 읽기 방식에 삭제 방지 조치를 유지한다.

### 3단계 — 통제 가능한 관계부터 FK 추가

| 대상 | 이번 적용 |
|---|---|
| `sales_channel_dong_mapping.dong` → `uph_dong_code.code` | 적용 |
| `scm_product_option.wms_product_code` → `scm_product.wms_product_code` | 적용 |
| `alloc_picking_zone.product_code` → `scm_product.wms_product_code` | 업로드 원자성 전환·백필 확인 후 적용 |
| `order_status_log.dong` | FK 미적용, 검증 SQL |
| `sku_daily_shipment.product_code` | FK 미적용, 옵션 의미·미등록·중복 검증 |
| `weight_calc_results.option_code` | FK 미적용, 옵션 관계 확정 전 자동 연결 금지 |
| `alloc_row.product_code` | 미등록 2종·업로드 대응 미해결이므로 보류 |
| `alloc_row.dong`, `alloc_dong_status.dong` | `기타` 포함 쓰기 경로 검증 후 후속 적용 |
| `manpower_log`, `uph_historical_summary` | 기존 업로드·보정 경로 확인 후 후속 적용 |

**`NOT VALID`는 신규 INSERT/UPDATE 실패를 막는 방법이 아니다.** 기존 행 검사를 미룰 뿐 신규 쓰기에는 제약이 적용된다. 따라서 watchdog 원본 로그에 붙이지 않는다. FK 추가·검증의 잠금 동작은 [PostgreSQL ALTER TABLE 문서](https://www.postgresql.org/docs/16/sql-altertable.html)를 기준으로 검증한다.

**DDL 초안 — 제약별 짧은 트랜잭션으로 실행:**

```sql
ALTER TABLE public.sales_channel_dong_mapping
ADD CONSTRAINT ax1102_channel_dong_fk
FOREIGN KEY (dong) REFERENCES public.uph_dong_code(code)
ON DELETE RESTRICT NOT VALID;

ALTER TABLE public.scm_product_option
ADD CONSTRAINT ax1102_option_product_fk
FOREIGN KEY (wms_product_code)
REFERENCES public.scm_product(wms_product_code)
ON DELETE RESTRICT NOT VALID;

ALTER TABLE public.alloc_picking_zone
ADD CONSTRAINT ax1102_zone_product_fk
FOREIGN KEY (product_code)
REFERENCES public.scm_product(wms_product_code)
ON DELETE RESTRICT NOT VALID;
```

추가 후 별도 트랜잭션에서 각각 검증한다.

```sql
ALTER TABLE public.sales_channel_dong_mapping
    VALIDATE CONSTRAINT ax1102_channel_dong_fk;
ALTER TABLE public.scm_product_option
    VALIDATE CONSTRAINT ax1102_option_product_fk;
ALTER TABLE public.alloc_picking_zone
    VALIDATE CONSTRAINT ax1102_zone_product_fk;
```

**백필:** 앞 단계 데이터만 사용한다. 누락이 발견되면 원본 근거를 확인해 일괄 upsert하고 재검증한다. FK를 맞추려고 임의 상품·동을 만들지 않는다.

**롤백 SQL:**

```sql
ALTER TABLE public.alloc_picking_zone
    DROP CONSTRAINT ax1102_zone_product_fk;
ALTER TABLE public.scm_product_option
    DROP CONSTRAINT ax1102_option_product_fk;
ALTER TABLE public.sales_channel_dong_mapping
    DROP CONSTRAINT ax1102_channel_dong_fk;
```

새로 만든 제약만 제거하며 기존 FK 4개는 변경하지 않는다. 롤백 DDL도 승인 범위·잠금 제한에 포함한다.

약 60만 행 `order_status_log`에 향후 제약을 추가한다면, 일반 FK 추가는 기존 행 검사 동안 쓰기를 막을 수 있다. `NOT VALID`도 추가 시 양쪽 표에 잠금을 요구하고 신규 쓰기를 제한한다. 별도 `VALIDATE`는 더 약한 잠금을 사용하지만 전체 검사와 I/O는 필요하다. **소요 시간은 미확인**이며 복원 DB에서 동시 수집 부하로 실측하기 전 운영 적용 시간을 약속하지 않는다.

### 범위 제외 및 두 저장소 배포 순서

`products`, `inventory_master`, `stock_count`, `invalid_scan`은 이번 대상에서 제외한다. 현재 0행이라는 이유만으로 삭제·전용·FK 연결하지 않는다. `ship_*`는 향후 이 상품 식별 체계를 참조하도록 설계 의견만 전달한다.

배포 순서:

1. 본 저장소에 검증 SQL·마이그레이션 초안·시험 결과 준비.
2. 사용자 승인 → 백업·복원 확인 → 동 표·활성 컬럼 추가.
3. 본 저장소 watchdog 활성 매핑 대응 배포·재시작·수집 확인.
4. 별도 ENCLU-LMS 웹앱 동 조회·매핑 비활성화 배포.
5. 상품 표·백필 → 웹앱 원자적 업로드 전환.
6. 고아 참조 0 확인 → FK 추가 → 별도 검증.

각 단계는 이전 단계의 코드를 유지해도 동작하는 추가형 변경으로 만든다. 각 저장소의 커밋·푸시·운영 반영은 별도로 승인받고, 함께 작동한 두 버전을 인수인계에 기록한다.

## 4. 검증 방법

### 운영 읽기 전용 기준선

```sql
BEGIN READ ONLY;

SELECT current_database(), current_setting('server_version');

SELECT conrelid::regclass AS child_table,
       conname, convalidated, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE contype = 'f'
  AND connamespace = 'public'::regnamespace
ORDER BY 1, 2;

SELECT option_code, count(*) AS rows,
       count(DISTINCT product_code) AS wms_products
FROM public.alloc_picking_zone
WHERE btrim(option_code) <> ''
GROUP BY option_code
HAVING count(*) > 1;

SELECT work_date, count(*) AS rows,
       sum(shipped_qty) AS qty, sum(order_count) AS item_invoice_count
FROM public.sku_daily_shipment
GROUP BY work_date
ORDER BY work_date;

COMMIT;
```

`order_count` 합계는 상품별 송장수 합이며, 전체 고유 송장수로 해석하지 않는다.

### 단계별 무결성 검증

```sql
-- UPH 로그의 NULL·미등록 동. 원본은 변경하지 않는다.
SELECT l.dong, count(*)
FROM public.order_status_log l
LEFT JOIN public.uph_dong_code d ON d.code = l.dong
WHERE l.dong IS NULL OR d.code IS NULL
GROUP BY l.dong;

-- FK 추가 전 판매처 매핑 고아 참조: 0건이어야 함
SELECT m.id, m.dong
FROM public.sales_channel_dong_mapping m
LEFT JOIN public.uph_dong_code d ON d.code = m.dong
WHERE d.code IS NULL;

-- 피킹존 상품 백필 누락: 0건이어야 함
SELECT z.product_code
FROM public.alloc_picking_zone z
LEFT JOIN public.scm_product p
  ON p.wms_product_code = z.product_code
WHERE p.wms_product_code IS NULL;

-- 할당 미등록 상품: 이번에는 차단하지 않고 목록 관리
SELECT r.product_code, count(*)
FROM public.alloc_row r
LEFT JOIN public.scm_product p
  ON p.wms_product_code = r.product_code
WHERE p.wms_product_code IS NULL
GROUP BY r.product_code;

-- 자동 연결 불가 옵션: 중복·미확정
SELECT option_code, count(*) AS candidates
FROM public.scm_product_option
WHERE is_active
GROUP BY option_code
HAVING count(*) <> 1
    OR bool_and(resolution_status = 'confirmed') IS NOT TRUE;

-- SKU 미등록 옵션. UNKNOWN도 별도로 드러나게 유지
SELECT s.product_code, count(*)
FROM public.sku_daily_shipment s
WHERE NOT EXISTS (
    SELECT 1 FROM public.scm_product_option m
    WHERE m.option_code = s.product_code AND m.is_active
)
GROUP BY s.product_code;

SELECT conname, convalidated
FROM pg_constraint
WHERE conname IN (
    'ax1102_channel_dong_fk',
    'ax1102_option_product_fk',
    'ax1102_zone_product_fk'
);
```

대량 로그 검증은 일자 범위·시험 DB 실행 시간을 먼저 확인한다. 실제 업무 코드 목록과 원본 표본은 공개 저장소에 커밋하지 않는다.

### 시험 DB·코드 테스트

Claude가 시험 환경에서 실행한다.

```powershell
py -m unittest discover -s "UPH 시스템/tests" -v
```

추가할 의미 있는 테스트:

- 미등록 판매처·동·상품이 있어도 watchdog 원본 저장과 성공분 캐시 갱신이 유지되는지.
- 옵션 하나가 두 상품에 연결돼도 수량이 두 배로 합산되지 않는지.
- 상품·옵션·피킹존 중간 저장 실패 시 전체 업로드가 롤백되는지.
- 같은 파일을 두 번 업로드해도 중복·불필요한 상태 변경이 없는지.
- 전체 대체·개별 비활성화 후 물리 행수가 줄지 않는지.
- 두 FK 연결 표에 잘못된 값이 들어가면 관리 업로드만 명확히 거절되는지.
- 동 목록 DB 장애·빈 결과·정렬 변경 시 화면과 할당 완료 판정이 유지되는지.

수작업 표본은 정상 상품, 앞자리 0 상품, 중복 옵션, 미등록 상품, `기타` 로케이션, 비활성 상품을 포함한다. 변경 전후 UPH 동별 지표·SKU 일자별 합계·할당 최종 출력값을 동일 기준시각 또는 동일 스냅샷으로 대조한다. 실시간 증가분을 회귀로 오판하지 않는다.

## 5. 위험 요소

- **운영 DB 스키마 변경·대량 백필이 필요하다.** 지시서 확정 → 사용자 승인 → 백업·복원 확인 후에만 실행한다.
- FK 추가·검증·롤백 모두 잠금 경합 가능성이 있다. 운영 수집 지연이나 파일 재시도가 발생하면 해당 단계 진행을 중단한다.
- `NOT VALID`도 새 쓰기를 검증한다. 로그에 적용하면 미등록 값 하나로 수집 청크가 실패할 수 있다.
- 현재 피킹존 전체 삭제와 업로드가 분리돼 있다. 이번 수정에서는 반드시 같은 트랜잭션으로 바꾸고 물리 삭제를 제거한다.
- 옵션 중복을 임의 병합하거나 WMS 코드와 옵션코드를 혼용하면 수량·중량·송장 상품 연결이 잘못된다.
- 매핑·동 비활성화는 과거 로그를 변경하지 않는다. 과거 데이터 재분류는 별도 승인 없이는 하지 않는다.
- 비활성화 이후 예전 코드로 단순 복귀하면 숨겼던 매핑·피킹 위치가 다시 사용될 수 있다. 롤백 시 활성 필터를 유지한다.
- 신규 표 조회·쓰기 권한은 기존 앱별 최소권한 구조에 맞춰 확인한다. 계정·접속 문자열·비밀값은 지시서·코드·공개 보고서에 적지 않는다.
- **외부 발송은 필요하지 않으며 이번 범위에 포함하지 않는다.** KSE·Notion·메시지 발송·송장 등록도 수행하지 않는다.
- 이번 작업의 물리 삭제 금지는 동 코드·판매처 매핑·상품·옵션·피킹존에 적용한다. 기존 로그 보관·정리 정책 변경은 별도 과제다.

## 6. 확인이 필요한 질문

1. UPH의 F동과 재고할당의 F동은 같은 건물인가? 같은 건물이더라도 두 업무용 코드는 분리 유지해도 되는가?
2. 상품 원본 파일을 관리·업로드할 담당자는 누구이며, 신규 상품·옵션 변경을 언제 반영하는가? 피킹존 파일이 상품 원본으로 충분한가?
3. 중복 옵션 3건은 정상 공유인가, 오등록인가? 판매자옵션코드의 유일성 범위는 전체인가, 브랜드·판매처별인가?
4. 비활성 동·상품·피킹 위치가 진행 중인 할당에 사용 중이면 기존 세션은 유지하고 신규 선택만 막는 정책으로 진행할 것인가?
5. 챗봇 소스·배포 위치와 운영 변경 가능 시간대를 알려줄 수 있는가? 초기 NULL 5행은 당시 올바른 동을 확인한 뒤 별도 보정하는 것으로 할 것인가?