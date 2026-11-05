-- AX-20261105-02 후속: 사용 중인 소모품 이름 중복을 DB에서도 막는다 (사용자 승인 2026-11-05)
-- 앱 검사(sl.consumable_name_taken)와 같은 기준: 앞뒤 공백·대소문자 무시, 사용 중(is_active)인 소모품만.
-- 되돌리기: DROP INDEX IF EXISTS supply_items_consumable_name_uq;
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS supply_items_consumable_name_uq
    ON supply_items (lower(btrim(name)))
    WHERE item_kind = 'consumable' AND is_active;
COMMIT;
