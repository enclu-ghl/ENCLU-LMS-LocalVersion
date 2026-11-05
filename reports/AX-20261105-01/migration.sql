-- AX-20261105-01 데이터 정정: 변경 이력 표 + 요약 정정 보호 컬럼 (실행 전 pg_dump 백업)
-- 추가만 하는 변경(새 표·새 컬럼, 기존 행 값 변화 없음).
-- 롤백: DROP TABLE public.data_change_history; DROP FUNCTION public.reject_data_change_history_mutation();
--       ALTER TABLE public.uph_historical_summary DROP COLUMN correction_locked;
--       (구 코드로 되돌릴 때는 이 컬럼 삭제 전에 월 정리 자동 채우기를 멈출 것 — 정정 행이 덮어써질 수 있음)
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE public.data_change_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL,                       -- 한 번의 저장 묶음
    table_name text NOT NULL CHECK (table_name IN (
        'manpower_log', 'uph_historical_summary', 'sales_channel_dong_mapping', 'alloc_picking_zone')),
    row_key jsonb NOT NULL CHECK (jsonb_typeof(row_key) = 'object'),
    operation text NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    before_value jsonb,
    after_value jsonb,
    actor_name text NOT NULL CHECK (btrim(actor_name) <> ''),
    actor_account_id text,                          -- 계정 도입 후 채움
    reason text,
    source text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (
        (operation = 'INSERT' AND before_value IS NULL AND after_value IS NOT NULL)
     OR (operation = 'UPDATE' AND before_value IS NOT NULL AND after_value IS NOT NULL)
     OR (operation = 'DELETE' AND before_value IS NOT NULL AND after_value IS NULL)
    )
);
CREATE INDEX data_change_history_time_idx ON public.data_change_history (changed_at DESC, id DESC);
CREATE INDEX data_change_history_row_idx ON public.data_change_history (table_name, row_key, changed_at DESC);

-- 이력은 고치거나 지우지 않는다 (실수 방지. 표 소유자는 트리거를 끌 수 있으므로 관리자 변조까지 막지는 못함)
CREATE FUNCTION public.reject_data_change_history_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '변경 이력은 수정하거나 삭제할 수 없습니다';
END;
$$;
CREATE TRIGGER data_change_history_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON public.data_change_history
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_data_change_history_mutation();

-- 정정 화면에서 저장한 요약행: 월 정리 자동 채우기가 덮어쓰지 않고, 분석에서 수기 보정처럼 우선 적용
ALTER TABLE public.uph_historical_summary
    ADD COLUMN correction_locked boolean NOT NULL DEFAULT false;

COMMIT;
