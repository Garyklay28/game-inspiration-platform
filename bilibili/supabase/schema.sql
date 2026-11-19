-- 빌리빌리 서브 슈퍼바이저가 사용하는 Supabase 테이블 (PoC 범위)
-- 실제 운영 스키마는 데이터·백엔드 담당과 합의해 확정한다.

-- 1) 게임 별칭 사전: 한·중·영 표기 통일 (기획안 '별칭 사전')
create table if not exists game_alias (
  game_id    text primary key,              -- 예: league_of_legends
  zh         text not null,                 -- 중국어 정식명
  ko         text not null,                 -- 한국어 정식명
  en         text not null,                 -- 영어 정식명
  aliases    text[] not null default '{}',  -- 약칭·대회명 등
  updated_at timestamptz not null default now()
);

-- 2) 수집한 빌리빌리 영상 지표 (스냅샷 단위로 누적 → 4주 누적 후 가중치 회귀 분석에 사용)
create table if not exists bili_video_snapshot (
  id           bigserial primary key,
  collected_at timestamptz not null default now(),
  source       text not null,               -- popular | ranking_v2
  origin       text not null,               -- live | snapshot
  bvid         text not null,
  title        text not null,
  game_id      text references game_alias(game_id),
  tname        text,
  pubdate      timestamptz,
  duration_sec int,
  view_cnt     bigint, like_cnt bigint, coin_cnt bigint,
  favorite_cnt bigint, share_cnt bigint,
  mission_id   bigint                       -- 공식 활동 참여 여부
);
create index if not exists idx_bvs_game_time on bili_video_snapshot (game_id, collected_at desc);

-- 3) 에이전트 보고서 (총괄 슈퍼바이저가 화면에 뿌리는 원본)
create table if not exists bili_agent_report (
  id         bigserial primary key,
  created_at timestamptz not null default now(),
  task_id    text not null,
  intent     text not null,
  report     jsonb not null                 -- BiliReport.to_dict()
);

-- 4) 별칭 후보 (collector 가 제안 → 사람이 검토 후 game_alias 로 반영)
create table if not exists game_alias_candidate (
  id             bigserial primary key,
  created_at     timestamptz not null default now(),
  zh             text not null,
  ko             text, en text,
  aliases        text[] default '{}',
  evidence_title text,
  status         text not null default 'pending'  -- pending | accepted | rejected
);

-- 반응률 뷰: (즐겨찾기+코인+좋아요+공유) / 조회수
create or replace view bili_video_engagement as
select *, (favorite_cnt + coin_cnt + like_cnt + share_cnt)::float / nullif(view_cnt, 0) as engagement_rate
from bili_video_snapshot;
