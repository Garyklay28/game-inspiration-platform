-- Supabase(PostgreSQL) 스키마. 기획안 13장 「데이터베이스 설계」와 같은 테이블이다.
-- 세 플랫폼 데이터를 같은 테이블에 넣고 platform 열로 나눈다.
-- Supabase 대시보드 > SQL Editor 에 붙여 넣어 한 번 실행한다.

create table if not exists raw_snapshots (
  id            text primary key,              -- <run_id>:<platform>
  run_id        text not null,
  platform      text not null check (platform in ('youtube','bilibili','tiktok')),
  source        text not null,                 -- api / file:<이름> / sample / aside
  is_sample     boolean not null default false,
  collected_at  timestamptz not null,
  payload       jsonb not null
);

create table if not exists games (
  game_id   text primary key,
  name_ko   text, name_en text, name_zh text
);

create table if not exists game_aliases (
  alias     text not null,
  game_id   text not null references games(game_id),
  platform  text,
  primary key (alias, game_id)
);

create table if not exists channels (
  channel_id   text not null,
  platform     text not null,
  title        text,
  subscribers  bigint,
  avg_views    double precision,                -- 아웃라이어 배수의 기준선
  updated_at   timestamptz not null default now(),
  primary key (platform, channel_id)
);

create table if not exists videos (
  video_id       text not null,
  platform       text not null,
  run_id         text not null,
  game_ids       text[] not null default '{}',
  channel_id     text,
  title          text,
  views          bigint, likes bigint, comments bigint,
  coins          bigint, favorites bigint,      -- 빌리빌리 전용
  duration_sec   integer,
  is_short       boolean,
  published_at   timestamptz,
  outlier_multiple double precision,
  views_per_hour   double precision,
  primary key (platform, video_id, run_id)
);

create table if not exists score_weights (
  id          bigserial primary key,
  platform    text not null,
  w_demand double precision, w_outlier double precision, w_freshness double precision, w_competition double precision,
  samples     integer,
  approved_by text,                             -- 사람이 승인한 경우에만 채운다
  applied_at  timestamptz
);

create table if not exists topic_scores (
  run_id       text not null,
  platform     text not null,
  game_id      text not null,
  demand double precision, outlier double precision, freshness double precision, competition double precision,
  score        double precision not null,       -- 정렬 참고용, 조회수 예측 아님
  videos_in_pool integer,
  primary key (run_id, platform, game_id)
);

create table if not exists analyses (
  analysis_id    text primary key,              -- <run_id>
  run_id         text not null,
  platform       text not null,
  game_id        text,
  summary        text,
  claims         jsonb not null,                -- 각 주장에 evidence_refs 가 붙어 있어야 한다
  created_at     timestamptz not null default now()
);

create table if not exists plans (
  plan_id     text primary key,
  user_id     uuid,                             -- 웹 서비스에서 채움 (auth.users)
  run_id      text not null,
  platform    text not null,
  game_id     text,
  plan        jsonb not null,                   -- plan-v1
  status      text not null check (status in ('draft','validated','needs_review')),
  created_at  timestamptz not null default now()
);

create table if not exists thumbnails (
  file_path   text primary key,                 -- Supabase Storage 경로 또는 저장소 상대 경로
  plan_id     text references plans(plan_id),
  ratio       text,
  source      text,                             -- openai:<모델> / user_image
  prompt      text,
  overlay_text text,
  created_at  timestamptz not null default now()
);

create table if not exists uploads (
  video_id      text primary key,
  plan_id       text references plans(plan_id),
  platform      text not null default 'youtube',
  published_at  timestamptz,
  registered_at timestamptz not null default now()
);

create table if not exists performance (
  video_id   text not null references uploads(video_id),
  at         timestamptz not null,
  source     text,                              -- api / manual
  views bigint, likes bigint, comments bigint,
  primary key (video_id, at)
);

-- 채널 평균 대비 배수 (화면용 뷰)
create or replace view v_outlier_multiple as
  select v.platform, v.video_id, v.title, v.views, c.avg_views,
         case when c.avg_views > 0 then v.views / c.avg_views end as multiple
  from videos v join channels c on c.platform = v.platform and c.channel_id = v.channel_id;

-- 빌리빌리 반응률 (즐겨찾기·코인·좋아요 ÷ 조회수)
create or replace view v_reaction_rate as
  select video_id, title, views,
         favorites::float / nullif(views,0) as favorite_rate,
         coins::float     / nullif(views,0) as coin_rate,
         likes::float     / nullif(views,0) as like_rate
  from videos where platform = 'bilibili';

-- 본인 기획안만 보이게 (웹 서비스에서 사용자 로그인 시)
alter table plans enable row level security;
drop policy if exists "own plans" on plans;
create policy "own plans" on plans for select using (auth.uid() = user_id);
