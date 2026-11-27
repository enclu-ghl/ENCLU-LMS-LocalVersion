-- AX-20261127-01 주간 계획 프로그램 — 새 표 4개 (기존 표 변경 없음)
-- 되돌리기: DROP TABLE public.wp_activity, public.wp_check_item, public.wp_task, public.wp_member;
-- 팀원 이름은 공개 저장소에 남기지 않도록 이 파일에 넣지 않는다(화면 '팀원 관리' 또는 별도 입력).
BEGIN;

CREATE TABLE public.wp_member (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE CHECK (btrim(name) <> ''),
    is_leader   BOOLEAN NOT NULL DEFAULT FALSE,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.wp_task (
    id               SERIAL PRIMARY KEY,
    week_start       DATE NOT NULL CHECK (extract(isodow FROM week_start) = 1),
    scope            TEXT NOT NULL CHECK (scope IN ('팀', '개인')),
    title            TEXT NOT NULL CHECK (btrim(title) <> ''),
    memo             TEXT,
    owner            TEXT,
    priority         SMALLINT CHECK (priority BETWEEN 1 AND 4),
    sort_order       INTEGER NOT NULL DEFAULT 0,
    manual_done      BOOLEAN NOT NULL DEFAULT FALSE,
    carried_from_id  INTEGER REFERENCES public.wp_task(id) ON DELETE SET NULL,
    carried_to_id    INTEGER REFERENCES public.wp_task(id) ON DELETE SET NULL,
    created_by       TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
CREATE INDEX wp_task_week_idx ON public.wp_task (week_start) WHERE deleted_at IS NULL;
-- 같은 할일은 한 번만 이월(사본이 둘 생기지 않게)
CREATE UNIQUE INDEX wp_task_carried_from_uq ON public.wp_task (carried_from_id) WHERE carried_from_id IS NOT NULL;

CREATE TABLE public.wp_check_item (
    id          SERIAL PRIMARY KEY,
    task_id     INTEGER NOT NULL REFERENCES public.wp_task(id) ON DELETE CASCADE,
    content     TEXT NOT NULL CHECK (btrim(content) <> ''),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_done     BOOLEAN NOT NULL DEFAULT FALSE,
    done_by     TEXT,
    done_at     TIMESTAMPTZ,
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX wp_check_item_task_idx ON public.wp_check_item (task_id);

CREATE TABLE public.wp_activity (
    id       SERIAL PRIMARY KEY,
    at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor    TEXT NOT NULL,
    action   TEXT NOT NULL,
    task_id  INTEGER,
    detail   JSONB
);
CREATE INDEX wp_activity_at_idx ON public.wp_activity (at DESC);

COMMIT;
