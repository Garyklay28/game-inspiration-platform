# Supabase

빌리빌리 전용 스키마는 없앴습니다. 세 플랫폼이 같은 테이블을 쓰는 **팀 공용 스키마**(기획안 13장 「데이터베이스 설계」)를 따릅니다.

- 스키마 원본: YouTube 파트 저장소 [JangYurim0607/youtube-agent-pipeline](https://github.com/JangYurim0607/youtube-agent-pipeline) 의 `db/schema.sql` (팀 저장소에 동기화되면 `youtube/db/schema.sql`)
- 빌리빌리가 쓰는 테이블: raw_snapshots · videos(coins, favorites 포함) · topic_scores · analyses · plans · uploads · performance (`platform = 'bilibili'`)
- 별칭 사전: games · game_aliases (`bili_agent/tools/alias_store.py` 가 읽음)
- 행 만들기·저장: `bili_agent/tools/team_db.py` (`python main.py ... --db-export` / `--db-push`)
