-- AX-20261102-01 D단계: 관리 화면이 쓰는 표에만 FK 3개 (사용자 승인 2026-11-04, 실행 전 pg_dump 백업)
-- 수집기(watchdog)가 쓰는 order_status_log·sku_daily_shipment 등에는 걸지 않는다.
-- 표가 작아(22행·3,551행·3,595행) NOT VALID/VALIDATE로 나누지 않고 바로 검사한다.
-- 롤백: ALTER TABLE ... DROP CONSTRAINT <이름>; (아래 3개)
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.sales_channel_dong_mapping
    ADD CONSTRAINT sales_channel_dong_mapping_dong_fkey
    FOREIGN KEY (dong) REFERENCES public.uph_dong_code (code) ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE public.scm_product_option
    ADD CONSTRAINT scm_product_option_product_fkey
    FOREIGN KEY (wms_product_code) REFERENCES public.scm_product (wms_product_code) ON DELETE RESTRICT;

ALTER TABLE public.alloc_picking_zone
    ADD CONSTRAINT alloc_picking_zone_product_fkey
    FOREIGN KEY (product_code) REFERENCES public.scm_product (wms_product_code) ON DELETE RESTRICT;

COMMIT;
