---
name: youtube-pipeline
description: 유튜브 게임 쇼츠를 트렌드 수집 → 정규화 → 점수화 → 분석 → 기획안 → 영상 생성 → 성과 기록 8단계로 만든다. "트렌드 보고 쇼츠 기획해줘", "로블록스 쇼츠 하나 만들어줘", "파이프라인 돌려줘", "업로드한 영상 성과 기록해줘" 요청에 사용.
allowed-tools: Read, Write, Edit, Bash(python -m yt_pipeline *), Bash(python -m pytest *), Bash(ffprobe *), Bash(ffmpeg *), Task
---

# YouTube 쇼츠 에이전트 파이프라인

규칙은 `AGENTS.md`. 모든 명령은 저장소 루트에서 `python -m yt_pipeline …`. 결과는 JSON 으로 나온다(`ok:false` 면 error 를 읽고 고친다).
어디까지 했는지 모르면 `python -m yt_pipeline status` 부터.

## 단계와 멈춤 지점

| # | 단계 | 누가 | 명령 / 에이전트 | 산출물 | 멈춤(사람 승인) |
|---|---|---|---|---|---|
| 1 | 트렌드 수집 | 코드 | `data --source api` | 01_raw | API 쿼터 사용 전 (search 1회=100 units) |
| 2 | 정규화 | 코드 | (data 에 포함) | 02_normalized | 별칭 후보 검토 |
| 3 | 점수화 | 코드 | (data 에 포함) | 03_scores | |
| 4 | 분석 | 코드 + trend-analyst | (data 에 포함) → 에이전트 | 04_evidence, 04_analysis | 주제 선택 확인 |
| 5 | 기획안 | plan-writer | 에이전트 | 05_plan.json/.md | |
| 6 | 검증 | 코드 + plan-validator | `validate` → 에이전트 → `review` | 06_validation | **기획안 승인** |
| 7 | 영상 생성 | script-writer + 코드 + qa-reviewer | `video timing/render`, `qa` | 07_video/ | edit.json 승인, 프리뷰 승인, **공개 여부** |
| 8 | 성과 기록 | 코드 + performance-analyst | `perf register/fetch/summary/calibrate` | performance/ | 가중치 적용 |

## 1~4a. 데이터 (코드)

```bash
python -m yt_pipeline data --source api                    # YouTube Data API (.env 의 YOUTUBE_API_KEY)
python -m yt_pipeline data --source api --keywords "로블록스,99밤"
python -m yt_pipeline data --source file --path data/raw/vidiq_20261119.json   # 다른 도구로 모은 데이터
python -m yt_pipeline data --source sample                 # 연습용 가짜 데이터
```
- 출력의 `run_id` 를 이후 모든 단계에 쓴다.
- **vidIQ MCP 가 연결돼 있으면**: `vidiq_trending_videos`·`vidiq_outliers` 결과를 간단형 `{"items":[{video_id,title,channel_id,channel_title,views,likes,comments,duration_sec,published_at,tags,channel_avg_views}]}` 로 `data/raw/` 에 저장한 뒤 `--source file` 로 넣는다. 크레딧이 드는 호출은 먼저 사용자에게 묻는다.
- 정규화 결과의 `alias_candidates` 는 사용자에게 보여 주고, 승인한 것만 `config/alias_dictionary.json` 에 추가한다. 추가했다면 `normalize → score → analyze` 를 다시 실행.

## 4b. 분석 → 5. 기획안 → 6. 검증 (에이전트 루프)

1. **trend-analyst** 에이전트에게 run_id 전달 → `04_analysis.json`.
   사용자에게 고른 주제·각도 후보를 보여 주고 확인받는다(다른 주제를 원하면 analysis 의 selected_topic_id 만 바꿔 다시).
2. **plan-writer** → `05_plan.json`. 에이전트가 `validate` 의 errors 가 빌 때까지 고친다.
3. **plan-validator** (독립 검토) → `review --file`.
4. `06_validation.json` 의 `next` 를 따른다:
   - `통과` → `05_plan.md` 를 사용자에게 보여 주고 **승인받는다**.
   - `plan-writer 가 오류를 고쳐…` → 2로 (issues 를 그대로 전달). 첫 제출 포함 3회까지.
   - `수정 횟수 초과` → 멈추고 사람에게 판단을 넘긴다.

## 7. 영상 생성

편집 세부 규칙은 `/video-edit` 스킬. 순서만 요약:
1. **script-writer** → `07_video/script.json` + `video timing` (음성 없으면 길이 추정).
2. 내레이션: 사용자가 녹음하거나 TTS(예: ElevenLabs MCP — 호출마다 과금, 먼저 승인)로 `07_video/voice/<id>.wav` 를 만든다. 만든 뒤 `video timing` 다시.
3. 클립: shot_list 대로 `clips/<shot>.mp4` 를 사용자가 녹화해 넣는다(AI 생성 클립은 크레딧 승인 후).
4. `edit.draft.json` 을 보고 in/out·crop_x·BGM 을 정해 `edit.json` 으로 저장 → `video check` → **edit.json 을 보여 주고 승인**.
5. `video render --plan-only` 로 명령 확인 → `video render` (720p 프리뷰).
6. **qa-reviewer** → 측정 + 화면 검토. FAIL 이면 edit.json 값 하나 고쳐 다시 5.
7. 사용자가 프리뷰를 직접 보고 승인 → `video render --final` → qa-reviewer 다시.
8. `python -m yt_pipeline report` → report.json.

## 8. 성과 기록 (업로드는 사람이 한다)

```bash
python -m yt_pipeline perf register --run <run_id> --video-id <유튜브 영상 ID>
python -m yt_pipeline perf fetch          # 24h·72h·7d 무렵 실행 (scheduled task 로 걸어도 됨)
python -m yt_pipeline perf manual --video-id <ID> --views 1234 --likes 56 --comments 7   # API 없이
```
그다음 **performance-analyst** → 요약과 가중치 보정안. 적용(`perf apply`)은 사용자 승인 후에만.

## 완료 보고
- 측정으로 확인한 것 / 확인하지 못한 것 / 사람이 확인해야 할 것 — 세 부분으로 나눈다.
- 샘플 데이터로 돌렸다면 첫 줄에 적는다.
