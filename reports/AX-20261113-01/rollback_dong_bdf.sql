-- AX-20261113-01 되돌리기 (A/B/F 체계로 복귀). 실행 전 해당 시점 이후 D동으로 들어온 수집 행이 있는지 먼저 본다.
-- 정확한 원상태는 _local_db/backups/ 의 CSV(uph_dong_code_*, sales_channel_dong_mapping_*, order_status_log_A동미배송_*)
-- 또는 enclu_scm_pre_AX-20261113-01_*.dump 기준.
BEGIN;
UPDATE uph_dong_code SET is_active = TRUE, updated_at = now() WHERE code = 'A동';
UPDATE sales_channel_dong_mapping SET dong = 'A동'
 WHERE channel_name IN ('스타일셀러', '이벤트-엔클루', '비디비치', '아리얼', '라쿠텐-아리얼', '믁끄럽', '유니딧',
                        '아리얼 쇼피(대만)', '아리얼 쇼피(말레이시아)', '아리얼 쇼피(베트남)', '아리얼 쇼피(싱가폴)', '아리얼 쇼피(태국)');
-- order_status_log: 백업 CSV의 id 목록으로 dong='A동' 복원 (D동 행이 남아 있으면 D동 비활성화 전에 처리)
UPDATE uph_dong_code SET is_active = FALSE, updated_at = now() WHERE code = 'D동';
COMMIT;
