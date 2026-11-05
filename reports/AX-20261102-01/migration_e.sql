-- AX-20261102-01 E단계: 남은 동 FK 4개 (사용자 요청 2026-11-05, 실행 전 pg_dump 백업)
-- 쓰기 경로: 네 표 모두 웹앱(enclu_app)만 씀. watchdog은 쓰지 않음.
--   manpower_log·uph_historical_summary 수기 업로드는 DONG_LIST(A/B/F)로 검사,
--   자동 요약(dong_summary_fill)은 order_status_log.dong(판매처 매핑 → 이미 FK)에서 옴.
--   alloc_row·alloc_dong_status는 로케이션 첫 글자 → C/D/F, 그 밖은 '기타'로 저장됨.
-- '기타'는 alloc_dong_code에 is_active=false로 둔다: FK는 받아 주고, 웹앱 동 목록(활성만 읽음)에는 안 나온다.
-- 롤백: ALTER TABLE ... DROP CONSTRAINT <이름>; (아래 4개) + DELETE FROM alloc_dong_code WHERE code='기타';
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

INSERT INTO public.alloc_dong_code (code, emoji, color, light_color, sort_order, is_active)
VALUES ('기타', '⚪', '#888780', '#f1efe8', 90, false)
ON CONFLICT (code) DO NOTHING;

ALTER TABLE public.alloc_row
    ADD CONSTRAINT alloc_row_dong_fkey
    FOREIGN KEY (dong) REFERENCES public.alloc_dong_code (code) ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE public.alloc_dong_status
    ADD CONSTRAINT alloc_dong_status_dong_fkey
    FOREIGN KEY (dong) REFERENCES public.alloc_dong_code (code) ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE public.manpower_log
    ADD CONSTRAINT manpower_log_dong_fkey
    FOREIGN KEY (dong) REFERENCES public.uph_dong_code (code) ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE public.uph_historical_summary
    ADD CONSTRAINT uph_historical_summary_dong_fkey
    FOREIGN KEY (dong) REFERENCES public.uph_dong_code (code) ON UPDATE CASCADE ON DELETE RESTRICT;

COMMIT;
