-- AX-20261105-02 비품·소모품·포장재 분리, 제작 박스 관리 (실행 전 pg_dump 백업)
-- 2026-11-05 기준 supply_items·supply_check·supply_receipt 0행, equipment_items 1행(구매일·구매가 비어 있음).
-- 롤백:
--   DROP TABLE public.made_box_log; DROP TABLE public.made_box_stock;
--   ALTER TABLE public.supply_receipt DROP COLUMN recorder;
--   ALTER TABLE public.supply_items DROP CONSTRAINT supply_items_kind_chk,
--       DROP COLUMN item_kind, DROP COLUMN packaging_material_id, DROP COLUMN is_active,
--       DROP COLUMN reorder_qty, DROP COLUMN lead_time_days;
--   ALTER TABLE public.equipment_items ALTER COLUMN purchase_date DROP DEFAULT;
--   (비품 구매일 채운 1행은 그대로 둬도 무방)
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

-- ① 비품: 구매일을 모르면 고양 창고 이동일(2026-01-23), 구매가는 모르면 NULL(이미 NULL 허용)
ALTER TABLE public.equipment_items ALTER COLUMN purchase_date SET DEFAULT DATE '2026-01-23';
UPDATE public.equipment_items SET purchase_date = DATE '2026-01-23' WHERE purchase_date IS NULL;

-- ② 소모품·포장재: 같은 재고 표, 구분 컬럼. 포장재는 무게구간 포장재(packaging_materials) 한 품목에 하나만 연결
ALTER TABLE public.supply_items
    ADD COLUMN item_kind text NOT NULL DEFAULT 'consumable'
        CHECK (item_kind IN ('consumable', 'packaging')),
    ADD COLUMN packaging_material_id integer UNIQUE
        REFERENCES public.packaging_materials (id) ON DELETE RESTRICT,
    ADD COLUMN is_active boolean NOT NULL DEFAULT true,
    ADD COLUMN reorder_qty numeric CHECK (reorder_qty > 0),          -- 표준 발주량(권장 주기 계산용, 선택)
    ADD COLUMN lead_time_days numeric CHECK (lead_time_days >= 0),   -- 조달 소요일(선택)
    ADD CONSTRAINT supply_items_kind_chk CHECK (
        (item_kind = 'consumable' AND packaging_material_id IS NULL)
     OR (item_kind = 'packaging'  AND packaging_material_id IS NOT NULL));

ALTER TABLE public.supply_receipt ADD COLUMN recorder text NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS supply_receipt_item_time_idx ON public.supply_receipt (item_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS supply_check_item_time_idx ON public.supply_check (item_id, occurred_at, id);

-- ③ 제작 완료 박스: 박스·위치별 파렛트 재고 + 기록(제작·사용·조정)
CREATE TABLE public.made_box_stock (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    box_name text NOT NULL CHECK (btrim(box_name) <> ''),
    location text NOT NULL DEFAULT '',
    pallet_qty numeric(10,2) NOT NULL DEFAULT 0 CHECK (pallet_qty >= 0),
    min_pallet_qty numeric(10,2) CHECK (min_pallet_qty >= 0),
    note text,
    is_active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX made_box_stock_name_loc_uq
    ON public.made_box_stock (lower(btrim(box_name)), lower(btrim(location)));

CREATE TABLE public.made_box_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stock_id bigint NOT NULL REFERENCES public.made_box_stock (id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('제작', '사용', '조정')),
    qty_delta numeric(10,2) NOT NULL,          -- 제작 +, 사용 −, 조정 = 새 수량 − 이전 수량
    qty_after numeric(10,2) NOT NULL CHECK (qty_after >= 0),
    recorder text NOT NULL CHECK (btrim(recorder) <> ''),
    note text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((kind = '제작' AND qty_delta > 0) OR (kind = '사용' AND qty_delta < 0) OR kind = '조정')
);
CREATE INDEX made_box_log_stock_time_idx ON public.made_box_log (stock_id, occurred_at, id);

COMMIT;
