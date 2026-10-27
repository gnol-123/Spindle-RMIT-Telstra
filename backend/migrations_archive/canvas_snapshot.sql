-- When the frontend last uploaded a canvas screenshot for the project card.
-- Apply after previews.sql. Re-runnable.
alter table public.projects add column if not exists canvas_snapshot_at timestamptz;
