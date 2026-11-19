-- AX-20261119-01 변경 이력에 order_status_log 허용 (사용자 승인 2026-11-19, 실행 전 pg_dump 백업)
-- WMS에 없는 잔여 송장 제외·되돌리기를 '🕘 변경 이력'에 남기기 위함.
-- 롤백(order_status_log 이력이 없을 때만 가능):
--   ALTER TABLE data_change_history DROP CONSTRAINT data_change_history_table_name_check;
--   ALTER TABLE data_change_history ADD CONSTRAINT data_change_history_table_name_check CHECK (table_name = ANY (ARRAY[
--     'manpower_log','uph_historical_summary','sales_channel_dong_mapping','alloc_picking_zone']));
BEGIN;
ALTER TABLE data_change_history DROP CONSTRAINT data_change_history_table_name_check;
ALTER TABLE data_change_history ADD CONSTRAINT data_change_history_table_name_check CHECK (table_name = ANY (ARRAY[
    'manpower_log', 'uph_historical_summary', 'sales_channel_dong_mapping', 'alloc_picking_zone', 'order_status_log']));
COMMIT;
