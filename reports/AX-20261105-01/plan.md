# AX-20261105-01 — 데이터 정정 페이지 작업 지시서

## 1. 목적 / 완료 조건

직원이 웹앱에서 인원 기록과 UPH 일별 요약을 정정하고, 기존 판매처 매핑·피킹존 관리 화면에서도 변경 이력을 남긴다.

완료 조건:

- 수정자 이름 필수, 사유 선택. 로그인·계정 구현은 제외한다.
- 추가·수정·삭제마다 대상 표, 행 키, 변경 전후 JSON, 수정자, 사유, 시각을 저장한다.
- **업무 데이터 변경과 이력 저장은 같은 트랜잭션**으로 처리한다. 이력 저장 실패 시 업무 변경도 취소한다.
- 이력 조회만 제공하며 수정·삭제 기능은 제공하지 않는다.
- 인원 정정 전후 인시·UPH와 마감 상태를 저장 전에 비교한다.
- 정정한 요약행은 월별 자동 채우기에서 보존된다.
- 기존 메뉴 문자열을 유지하고 새 메뉴만 추가한다.
- 피킹존의 등록·수정·삭제·전체 교체를 공통 저장 경로에서 처리한다.
- 임시 PostgreSQL·화면 테스트 후 Codex 검토를 받는다.

본 지시서는 파일 열람을 근거로 작성했다. **운영 DB의 실제 컬럼형·PK·제약·권한은 미확인**이며, 파일 수정·DB 접속·테스트 실행은 하지 않았다.

## 2. 영향 파일·함수

아래 `app.py`는 모두 `웹으로 진행 중인 건/app.py`를 뜻한다. 웹앱은 루트와 별도 Git 저장소이므로 변경·검토·커밋 대상을 구분한다.

| 실제 확인 위치 | 영향 |
|---|---|
| `웹으로 진행 중인 건/app.py:407` — `alloc_bulk_upsert_zone` | 자체 raw connection·commit 사용. 같은 연결에서 이력 저장하도록 확장 |
| `웹으로 진행 중인 건/app.py:447` — `alloc_sync_product_master` | 피킹존과 상품·옵션 마스터의 기존 원자성 유지 |
| `웹으로 진행 중인 건/app.py:853` — `_MANUAL_SUMMARY` | 현재 `start_time` 존재 여부로 수기행 판정 |
| `웹으로 진행 중인 건/app.py:856` — `dong_summary_check` | 정정 보호행을 자동 비교·삭제 대상에서 제외 |
| `웹으로 진행 중인 건/app.py:895` — `dong_summary_fill` | 정정 보호행 덮어쓰기 방지 |
| `웹으로 진행 중인 건/app.py:956` — `uph_get_manpower_rows` | 현재 `event_time`만 정렬. 동일 시각 처리 검토 |
| `웹으로 진행 중인 건/app.py:966` — `uph_calc_man_hours` | 정정 전후 미리보기 계산 재사용 |
| `웹으로 진행 중인 건/app.py:1727` | DB 관리 시스템 메뉴에 정정·이력 메뉴 추가 |
| `웹으로 진행 중인 건/app.py:1742` | 기존 UPH 메뉴 문자열 유지 |
| `웹으로 진행 중인 건/app.py:4219` | 키오스크에서도 인원 이벤트 추가. 정정 저장과 동시 실행 가능 |
| `웹으로 진행 중인 건/app.py:4766` | 요약행 조회·수기 판정·실시간 자료와 병합 |
| `웹으로 진행 중인 건/app.py:4840` | 일별 인시·UPH 계산 및 과거 마감 누락 처리 |
| `웹으로 진행 중인 건/app.py:5030` | 기존 요약 엑셀 저장에도 수정자·이력 처리 연결 |
| `웹으로 진행 중인 건/app.py:5066` | 기존 요약 날짜별 삭제에도 이력 처리 연결 |
| `웹으로 진행 중인 건/app.py:5117` | 매핑 등록·upsert |
| `웹으로 진행 중인 건/app.py:5168` | 매핑 삭제 |
| `웹으로 진행 중인 건/app.py:5183` | 매핑 동 변경 |
| `웹으로 진행 중인 건/app.py:6974` | 피킹존 파일 반영·전체 교체 |
| `웹으로 진행 중인 건/app.py:7022` | 피킹존 단건 등록·덮어쓰기 |
| `웹으로 진행 중인 건/app.py:7085` | 피킹존 수정 |
| `웹으로 진행 중인 건/app.py:7093` | 피킹존 삭제가 공통 함수를 우회하는 경로 |
| `UPH 시스템/watchdog_agent.py:78` | 매핑 캐시 기본 갱신 주기 300초 |
| `UPH 시스템/watchdog_agent.py:189` — `DongMappingCache` | 판매처명 공백 제거 후 매핑 |
| `UPH 시스템/watchdog_agent.py:477` | 변경 감지에 동 값이 포함되지 않아 매핑 수정만으로 기존 로그는 재분류되지 않음 |

신규 정정 서비스·화면 함수, 마이그레이션 SQL, 테스트 파일은 **신규 생성 제안이며 현재 존재 미확인**이다. 위 목록의 검색 일치 위치와 함수 본문을 Claude가 다시 대조하고 `plan-check.md`에 기록한다.

## 3. 작업 단계

### 3-1. 착수 검증과 DB 사전 조사

1. `reports/AX-20261105-01/plan-check.md`에 지시 항목별 수용·수정·거부와 근거를 작성한다.
2. 루트와 웹앱 각각 `git status --short`, `git remote -v`로 작업 대상을 확인한다. 접속정보는 보고서에 복사하지 않는다.
3. 읽기 전용 트랜잭션에서 네 표의 컬럼형, 기본값, PK·UNIQUE·FK, 트리거, 소유자와 앱 권한을 확인한다.
4. 특히 인원행 식별키, 요약의 `(work_date, dong)` 유일성, 날짜·시각 저장형을 확정한다. 행 식별에 화면 순번이나 PostgreSQL `ctid`를 사용하지 않는다.
5. 시험 DB에서 구현·DDL·롤백을 먼저 검증한다. 운영 적용 SQL과 예상 영향량을 준비한 뒤 운영 변경 승인을 받는다.

### 3-2. 변경 이력 DDL

다음은 **신규 DDL 제안**이다. 실제 스키마·권한 조사 후 확정한다.

```sql
CREATE TABLE public.data_change_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL,
    table_name text NOT NULL CHECK (table_name IN (
        'manpower_log',
        'uph_historical_summary',
        'sales_channel_dong_mapping',
        'alloc_picking_zone'
    )),
    row_key jsonb NOT NULL
        CHECK (jsonb_typeof(row_key) = 'object'),
    operation text NOT NULL
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    before_value jsonb,
    after_value jsonb,
    actor_name text NOT NULL CHECK (btrim(actor_name) <> ''),
    actor_account_id text,
    reason text,
    source text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (request_id, table_name, row_key),
    CHECK (
        (operation = 'INSERT'
            AND before_value IS NULL AND after_value IS NOT NULL)
        OR
        (operation = 'UPDATE'
            AND before_value IS NOT NULL AND after_value IS NOT NULL
            AND before_value IS DISTINCT FROM after_value)
        OR
        (operation = 'DELETE'
            AND before_value IS NOT NULL AND after_value IS NULL)
    )
);

CREATE INDEX data_change_history_time_idx
    ON public.data_change_history (changed_at DESC, id DESC);

CREATE INDEX data_change_history_row_idx
    ON public.data_change_history (table_name, row_key, changed_at DESC);

CREATE FUNCTION public.reject_data_change_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '変更履歴の更新・削除は禁止されています';
    RETURN NULL;
END;
$$;

CREATE TRIGGER data_change_history_append_only
BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.data_change_history
FOR EACH STATEMENT
EXECUTE FUNCTION public.reject_data_change_history_mutation();
```

트리거 예외 문구는 구현 시 한국어로 작성한다. 이력표·시퀀스의 소유자와 `enclu_app`의 SELECT·INSERT 권한을 명시하고, UPDATE·DELETE·TRUNCATE는 허용하지 않는다.

단, **테이블 소유자는 트리거를 해제할 수 있다.** 앱 계정이 이력표까지 소유하면 관리자 수준의 변조를 막는 보장은 없다. 가능하면 이력표는 별도 관리 소유자로 두고 앱에는 필요한 권한만 부여한다. 계정 추가·권한 변경은 운영 적용안에 포함해 확인받는다.

설계 규칙:

- `actor_name`은 당시 입력 이름을 영구 보존한다. 향후 계정 도입 시 `actor_account_id`를 채우며 과거 이름을 덮어쓰지 않는다.
- UUID는 저장 요청마다 생성한다. 동일 요청 재전송은 업무 변경까지 중복 실행되지 않도록 트랜잭션 시작에서 직렬화하고 기존 이력을 확인한다.
- 전후 값은 서버가 읽은 실제 행과 저장 결과를 사용한다. 클라이언트가 보낸 변경 전 값을 그대로 이력에 넣지 않는다.
- 변경 없는 저장은 업무 UPDATE와 이력을 생략한다.
- 날짜·시각·Decimal·NULL을 일관된 JSON 표현으로 직렬화한다.
- 한 요청에서 같은 행은 최종 변경 한 건으로 묶는다.

### 3-3. 요약행 정정 보호

시각을 모르는 행에 가짜 `start_time`을 넣어 보호하지 않는다. 다음 컬럼 추가를 권장한다.

```sql
ALTER TABLE public.uph_historical_summary
ADD COLUMN correction_locked boolean NOT NULL DEFAULT false;
```

보존 판정을 **기존 수기 판정 OR `correction_locked`**로 확장한다.

- 기존 `start_time` 기반 수기행의 동작은 유지한다.
- 정정 화면에서 추가·수정한 요약행은 `correction_locked=true`로 저장한다.
- `dong_summary_check`, `dong_summary_fill`, 분석 화면의 수기/자동 분류를 함께 수정한다.
- 기존 엑셀 업로드가 보호행을 덮어쓸 때도 명시적인 확인과 전후 이력을 남긴다. 보호값을 암묵적으로 해제하지 않는다.
- 원본 조회와 채우기 사이에 정정이 들어와도 보호행이 삭제·갱신되지 않도록 저장 시점 조건과 잠금을 검증한다.
- 초기 작업에서는 기존 요약행 전체를 일괄 갱신하지 않는다.

### 3-4. 화면 구성·공통 저장 흐름

기존 DB 관리 시스템에 새 메뉴 **`✏️ 데이터 정정`**, **`🕘 변경 이력`**을 추가한다.

정정 화면은 인원 기록·UPH 요약 탭으로 구성하고, 판매처 매핑·피킹존은 기존 메뉴로 이동하도록 안내한다. 기존 관리 화면에도 대상 행 이력 조회를 붙인다.

공통 흐름:

1. 날짜·동 또는 행 키로 조회한다.
2. 행 선택 → 수정자 이름·사유 입력 → 변경값 입력.
3. 전후 차이와 영향 지표를 미리 본다.
4. 삭제·덮어쓰기는 대상과 건수를 명시해 확인한다.
5. 저장 트랜잭션에서 대상 재조회·잠금 및 원본 비교를 수행한다.
6. 조회 이후 타인이 바꿨으면 저장을 거부하고 재조회시킨다.
7. 업무 변경·이력을 함께 커밋한 뒤 관련 캐시와 화면을 갱신한다.

동 목록 조회 실패 시 기본 동 목록으로 저장하지 말고 정정 저장을 중단한다. 표·컬럼은 고정 허용 목록, 값은 바인딩 SQL로 처리한다. `width="stretch"`를 사용한다.

### 3-5. 표별 수정·검증

| 대상 | 흐름·검증 규칙 |
|---|---|
| `manpower_log` | 업무일·동의 전체 이벤트를 조회하고 행 추가·수정·삭제. 이벤트는 기존 실제 값인 시작·변경·중지·마감·재시작을 확인해 허용. 인원은 유한한 0 이상 정수, 시작·변경·재시작은 양수. 중지·마감은 계산상 0이며 기존 기록용 인원을 무조건 덮어쓰지 않음 |
| `uph_historical_summary` | 날짜·동별 추가·수정·삭제. 완료건수·주문량은 유한한 0 이상 정수, 인원·UPH는 유한한 0 이상 수. 실제 단위는 기존 업로드 및 집계와 대조. 날짜·동 키 이동은 초기 범위에서 막고 삭제 후 추가로 처리 |
| `sales_channel_dong_mapping` | 기존 등록·이동·삭제 모두 공통 이력 서비스 연결. 이름 공백 정리, 빈 이름 금지, DB 코드표의 동만 허용. 수집기가 모든 공백을 제거하므로 정규화 이름 충돌을 검사하고 다른 동으로 중복 매핑되지 않게 차단 |
| `alloc_picking_zone` | 상품코드는 문자열로 보존하고 앞자리 0 유지. 코드·로케이션 필수. 파일·단건·수정·삭제 모두 `alloc_bulk_upsert_zone` 경유. 상품·옵션 마스터 동기화와 이력을 같은 raw connection에서 처리 |

인원 추가 규칙:

- KST와 실제 DB 시각형을 일치시킨다. 미래 이벤트·업무일 불일치·동일 시각 충돌은 저장 전에 검사한다.
- 동일 시각 이벤트가 계산 결과를 달리 만들 수 있으므로 새 충돌은 차단하고, 기존 충돌은 표시한다. 정렬은 실제 PK 확인 후 `event_time, PK`로 안정화한다.
- 중지 후 재시작, 마감 후 재시작은 기존 지원 흐름으로 유지한다.
- 이벤트 순서가 비정상적이면 경고와 확인을 제공하되 기존 잘못된 기록을 정정할 수 있어야 한다.
- 인원 정정 저장과 정상 입력 버튼의 동시 추가도 충돌 감지에 포함한다. 행 하나만 비교하지 말고 해당 날짜·동 전체 이벤트 집합을 비교한다.

인시·UPH 미리보기:

- 기존 `uph_calc_man_hours`를 재사용한다.
- 오늘은 전후 계산에 같은 현재 시각을 사용한다. 과거는 기존 일별 분석과 같은 종료 기준을 적용한다.
- 완료건수는 기존의 **수기/정정 요약 > 실시간 로그 > 자동 요약** 순서를 따른다.
- 기간·동·완료건수·인시·UPH·마감 상태를 함께 표시한다.
- 인시 0, 완료건수 조회 실패, 과거 마감 누락은 계산 불가 또는 잠정값으로 표시한다.
- 요약의 `uph_value`는 저장된 입력값이고 현재 일별 UPH는 인원 로그로 다시 계산된다(`app.py:4840`). 두 값을 구분하며, 요약 UPH 수정만으로 분석 UPH가 바뀐다고 안내하지 않는다.

피킹존 주의:

- `alloc_bulk_upsert_zone`에 삭제 대상과 수정자 문맥을 전달할 수 있게 확장한다.
- 기존 직접 삭제 SQL을 제거하고 공통 경로로 연결한다.
- 전체 교체는 물리적 전부 삭제·재삽입 대신 최종 차이를 구해 추가·수정·삭제별 이력을 남기는 방식을 권장한다.
- 로케이션뿐 아니라 상품명·옵션 변경도 미리보기와 이력에 포함한다.
- 상품 마스터·옵션은 기존 정책대로 보존한다. 그 부수 변경은 피킹존 이력의 직접 복구 범위와 구분한다.
- 대량 처리는 업무 변경·이력 모두 일괄 처리하고 청크마다 커밋하지 않는다.

매핑 저장 후 안내:

> 수집기는 기본 300초 간격이며 실제 상품 처리 시 매핑 갱신을 확인합니다. 설정이나 조회 실패에 따라 늦어질 수 있습니다. 기존 주문 로그는 매핑 변경만으로 자동 재분류되지 않습니다.

기존 로그 재분류·수집기 캐시 초기화는 이번 작업에서 자동 수행하지 않는다.

### 3-6. 기존 경로 보완·배포·롤백

- 요약 엑셀 저장·삭제에도 이름·사유·이력을 연결해 정정 화면 밖 우회 변경을 막는다.
- 기존 정상 인원 입력·키오스크 추가와 자동 요약 생성의 이력 범위는 6번 질문에서 확정한다. 최소한 기존 행 변경·삭제에는 이력 누락이 없어야 한다.
- 이력 조회에 기간·표·수정자·행 키 필터와 페이지 단위 조회를 제공한다.
- 운영 적용은 **백업 → 시험 실행 ROLLBACK → 승인된 DDL 적용 → 호환 코드 활성화 → 표본 검증** 순서로 진행한다. 앱 시작 시 자동 DDL을 실행하지 않는다.
- 작업 결과와 미검증 사항을 HANDOFF에 기록한다.

롤백:

1. 정정 저장 기능을 중단한다.
2. 앱을 이전 버전으로 돌려도 이력표와 보호 컬럼은 유지한다.
3. 이전 코드가 정정 보호를 모르면 자동 요약 채우기·로그 정리를 함께 중단한다.
4. 데이터 복구는 이력 전후 값과 현재 값을 대조해 **새 정정 작업과 새 이력**으로 수행한다. 이후 타인의 변경을 덮어쓰지 않는다.
5. 피킹존 부수 마스터 변경은 별도 대조한다. 마스터 상품을 연쇄 삭제하지 않는다.
6. 전체 DB 복원은 이후 정상 업무 데이터까지 사라질 수 있으므로 별도 승인된 장애 복구에만 사용한다.

## 4. 검증 방법

Claude가 시험 DB에서 실행하고 명령·결과·실패 조건을 보고서에 남긴다. 아래 신규 테스트 파일은 아직 존재 미확인이다.

**스키마·권한 확인**

읽기 전용으로 컬럼과 제약을 조회한다.

```sql
BEGIN READ ONLY;

SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'manpower_log', 'uph_historical_summary',
    'sales_channel_dong_mapping', 'alloc_picking_zone'
  )
ORDER BY table_name, ordinal_position;

SELECT conrelid::regclass AS table_name,
       conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid IN (
    'public.manpower_log'::regclass,
    'public.uph_historical_summary'::regclass,
    'public.sales_channel_dong_mapping'::regclass,
    'public.alloc_picking_zone'::regclass
);

ROLLBACK;
```

DDL 시험은 UTF-8 SQL 파일과 `psql -X -v ON_ERROR_STOP=1 -f <시험SQL>`로 실행한다. 파일 안에서 `BEGIN`·DDL·검증·`ROLLBACK`을 수행한다. 접속 비밀값을 명령·로그에 노출하지 않는다.

**필수 테스트**

- 네 표의 추가·수정·삭제가 정확한 행 키와 전후 JSON을 남긴다.
- 이름 공백, 음수·NaN·무한대, 잘못된 동, 중복 키, 미래 시각을 거부한다.
- 이력 INSERT 실패 시 업무 변경과 상품 마스터 동기화가 모두 롤백된다.
- 변경 없는 저장은 이력 0건, 같은 요청 재전송은 중복 변경 0건이다.
- 두 세션의 동시 수정·삭제·인원 추가에서 오래된 화면 저장이 차단된다.
- 이력 UPDATE·DELETE·TRUNCATE가 앱 권한으로 실패한다.
- 자동 요약 정정 후 `dong_summary_check/fill`을 실행해 값이 보존되고 분석에서도 우선 적용된다.
- 기존 엑셀 업로드·삭제와 피킹존 전체 교체에도 이력이 빠지지 않는다.
- 피킹존 상품명·옵션만 변경한 경우도 감지한다.
- 대량 처리 중간 실패에서 일부 커밋이 발생하지 않는다.

**수작업 계산 표본**

합성 이벤트 `09:00 시작 2명 → 10:00 변경 3명 → 11:00 중지 → 12:00 재시작 1명 → 13:00 마감`은 **6인시**다. 완료 120건이면 UPH는 **20건/인시**다.

마감을 14:00으로 정정하면 **7인시**, UPH는 **17.1건/인시**다. 미리보기·저장 후 분석값을 비교한다. 별도로 마감 누락 보완, 중지로 종료, 마감 후 재시작, 인시 0을 시험한다.

**화면·회귀**

Streamlit AppTest와 실제 브라우저에서 이름 필수, 삭제 확인, 대상 전환 시 입력 초기화, 저장 실패, 모바일 화면, 이력 필터를 확인한다. 기존 UPH·매핑·피킹존 메뉴와 정상 저장도 재검증한다.

## 5. 위험 요소

- **운영 DB 스키마 변경 필요:** 이력표·인덱스·트리거·요약 보호 컬럼·권한. 실제 DDL과 잠금 영향을 제시하고 승인 후 적용한다.
- **대량 쓰기 발생 가능:** 피킹존 전체 교체, 요약 업로드 및 자동 처리 이력. 대상 건수·예상 이력량·트랜잭션 시간을 먼저 확인한다.
- **삭제·복구 위험:** 인원 삭제는 인시를, 매핑 삭제는 이후 분류를, 피킹존 삭제는 할당 결과를 바꾼다. 대상 확인과 원자적 이력이 필요하다.
- **계산 회귀 위험:** 요약 보호 판정은 채우기뿐 아니라 분석 우선순위에도 적용해야 한다. 저장 UPH와 계산 UPH를 혼동하면 정정 효과가 잘못 전달된다.
- **로그인 없는 이름은 본인 확인 수단이 아니다.** 입력 이름을 기록하는 수준이며 계정 도입 전까지 수정 권한을 개인별로 구분하지 못한다.
- **영구 이력에는 직원 이름·업무 데이터가 남는다.** 실제 이력·덤프·표본을 공개 Git에 올리지 않는다.
- **외부 발송은 필요 없다.** 외부 서비스 등록·메시지 전송은 구현 범위에 포함하지 않는다.

## 6. 확인이 필요한 질문

1. 정상 인원 입력·키오스크 추가와 자동 요약 채우기까지 모두 이력을 남길까요? 자동 작업은 이름 대신 `시스템`과 실행 출처를 기록하는 안을 권장합니다.
2. 시각을 모르는 요약 정정을 위해 `correction_locked` 컬럼을 추가하는 안으로 진행할까요?
3. 요약의 저장 UPH는 입력값으로 유지하고 계산 UPH를 별도 표시할까요? 인원 로그 없이 요약값만으로 분석 UPH를 보완하는 동작도 필요한가요?
4. 업무일을 넘기는 야간 작업이 있나요? 있다면 날짜·시각 검증에 사용할 업무일 경계를 확인해야 합니다.