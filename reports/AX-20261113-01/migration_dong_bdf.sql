-- AX-20261113-01 UPH 출고동 A/B/F → B/D/F (사용자 요청 2026-11-13: A동 적치 전환)
-- 실행 전 백업: uph_dong_code·sales_channel_dong_mapping 전체 + 아래 4)에서 바뀌는 order_status_log 행(id, dong).
-- 한 트랜잭션. 롤백은 rollback_dong_bdf.sql (백업 CSV 기준).
BEGIN;

-- 1) D동 추가(B 20 · D 25 · F 30 순서), A동은 출고 안 함 → 비활성(과거 실적·FK 보존용으로 행은 남김)
INSERT INTO uph_dong_code (code, emoji, color, light_color, sort_order, is_active)
VALUES ('D동', '🟠', '#e8833a', '#fdf0e6', 25, TRUE)
ON CONFLICT (code) DO UPDATE SET is_active = TRUE, updated_at = now();
UPDATE uph_dong_code SET is_active = FALSE, updated_at = now() WHERE code = 'A동';

-- 2) 판매처 재배정: 스타일셀러 → F동, 이벤트-엔클루 → B동, 나머지 A동 판매처(비디비치·아리얼 계열·믁끄럽·유니딧) → D동
UPDATE sales_channel_dong_mapping SET dong = 'F동' WHERE dong = 'A동' AND channel_name = '스타일셀러';
UPDATE sales_channel_dong_mapping SET dong = 'B동' WHERE dong = 'A동' AND channel_name = '이벤트-엔클루';
UPDATE sales_channel_dong_mapping SET dong = 'D동' WHERE dong = 'A동';

-- 3) 아직 배송 안 된 A동 송장(같은 송장번호에 배송 행이 하나도 없는 것)만 새 동으로 옮긴다.
--    수집기는 상태가 바뀐 행만 다시 쓰므로, 그대로 두면 이 주문들이 새 동 잔여에 안 잡힌다.
--    배송된 주문은 과거 실적이라 A동으로 남긴다. 판매처명은 수집기와 같게 공백을 빼고 맞춘다.
UPDATE order_status_log o
SET dong = m.dong
FROM sales_channel_dong_mapping m
WHERE o.dong = 'A동'
  AND regexp_replace(o.channel_name, '\s', '', 'g') = regexp_replace(m.channel_name, '\s', '', 'g')
  AND NOT EXISTS (SELECT 1 FROM order_status_log s WHERE s.invoice_no = o.invoice_no AND s.status = '배송');

COMMIT;
