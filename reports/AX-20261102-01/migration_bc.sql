-- AX-20261102-01 B·C단계: 동 코드 표 2개 + 상품 마스터·옵션 표 (사용자 승인 2026-11-04, 실행 전 pg_dump 백업)
-- 실행 계정: 기존 표 소유자(웹앱 계정). 추가형 변경만 — 기존 표 컬럼·제약은 바꾸지 않는다.
-- 예외: 스타일셀러 사본 상품(05131) 피킹존 1행 삭제 — 사용자 지시("사본은 삭제완료, db에서도 삭제해도 됌").
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

-- ── B. 동 코드 ── UPH 출고동(판매처 기준)과 재고할당 동(로케이션 첫 글자 기준)은 체계가 달라 표를 나눈다.
CREATE TABLE public.uph_dong_code (
    code         text PRIMARY KEY,
    emoji        text,
    color        text CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    light_color  text CHECK (light_color ~ '^#[0-9A-Fa-f]{6}$'),
    sort_order   integer NOT NULL DEFAULT 100,
    is_active    boolean NOT NULL DEFAULT true,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.alloc_dong_code (LIKE public.uph_dong_code INCLUDING ALL);

INSERT INTO public.uph_dong_code (code, emoji, color, light_color, sort_order) VALUES
    ('A동', '🔴', '#e24b4a', '#fcebeb', 10),
    ('B동', '🔵', '#378add', '#e6f1fb', 20),
    ('F동', '🟢', '#639922', '#eaf3de', 30);
-- '기타'는 동이 아니라 미분류 버킷이라 넣지 않는다(app.py ALLOC_ETC).
INSERT INTO public.alloc_dong_code (code, sort_order) VALUES
    ('C동', 10), ('D동', 20), ('F동', 30);

-- ── C. 상품 마스터 ── 키 = WMS 상품코드(문자열, 앞자리 0 보존). 옵션(판매자옵션코드)은 N:M 연결표.
CREATE TABLE public.scm_product (
    wms_product_code text PRIMARY KEY CHECK (btrim(wms_product_code) <> ''),
    product_name     text NOT NULL DEFAULT '',
    is_active        boolean NOT NULL DEFAULT true,
    source           text NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now()
);
-- resolution_status: confirmed = 이 옵션은 이 상품 하나 / shared = 여러 상품이 정상 공유(사용자 확인)
--                    / ambiguous = 여러 상품에 붙었는데 미확인 → 옵션→상품 자동 연결에 쓰지 않는다
CREATE TABLE public.scm_product_option (
    wms_product_code  text NOT NULL,
    option_code       text NOT NULL CHECK (btrim(option_code) <> ''),
    is_active         boolean NOT NULL DEFAULT true,
    resolution_status text NOT NULL DEFAULT 'confirmed'
                      CHECK (resolution_status IN ('confirmed', 'shared', 'ambiguous')),
    source            text NOT NULL,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (wms_product_code, option_code)
);
CREATE INDEX scm_product_option_option_idx ON public.scm_product_option (option_code);

DELETE FROM public.alloc_picking_zone WHERE product_code = '05131' AND option_code = 'STY032';

INSERT INTO public.scm_product (wms_product_code, product_name, source)
SELECT product_code, COALESCE(product_name, ''), 'alloc_picking_zone_initial'
FROM public.alloc_picking_zone
WHERE btrim(COALESCE(product_code, '')) <> '';

INSERT INTO public.scm_product_option (wms_product_code, option_code, resolution_status, source)
SELECT product_code, btrim(option_code),
       CASE WHEN count(*) OVER (PARTITION BY btrim(option_code)) > 1 THEN 'ambiguous' ELSE 'confirmed' END,
       'alloc_picking_zone_initial'
FROM public.alloc_picking_zone
WHERE btrim(COALESCE(product_code, '')) <> '' AND btrim(COALESCE(option_code, '')) <> '';

-- 바노바기 시딩 BA2AMK00_179X: 두 상품 모두 시딩품으로 정상(사용자 확인 2026-11-04)
UPDATE public.scm_product_option SET resolution_status = 'shared' WHERE option_code = 'BA2AMK00_179X';

COMMENT ON COLUMN public.sku_daily_shipment.product_code IS
'레거시 컬럼명. WMS 상품코드가 아니라 order_status_log.extra_data의 옵션명(판매자옵션코드). 미상은 UNKNOWN. 상품 연결은 scm_product_option.option_code.';

COMMIT;
