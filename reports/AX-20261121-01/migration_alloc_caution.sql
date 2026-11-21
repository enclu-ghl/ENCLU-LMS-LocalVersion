-- AX-20261121-01 재고할당 '주의' 표시 (행사 기간 로케이션 겹침 표시용)
-- 업로드 파일에 '주의' 열이 있고 값이 '주의'인 행을 현장 작성 화면에 빨간 '주의'로 보여준다.
-- 기본값 FALSE라 기존 행·평소 파일(열 없음)은 동작 변화 없음.
-- 롤백: ALTER TABLE public.alloc_row DROP COLUMN caution;

ALTER TABLE public.alloc_row
    ADD COLUMN IF NOT EXISTS caution BOOLEAN NOT NULL DEFAULT FALSE;
