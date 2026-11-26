# youtube-agent-pipeline

YouTube 게임 쇼츠(기본은 로블록스)의 소재를 고르고 기획안과 영상을 만드는 에이전트 파이프라인이다. Claude Code에서 실행한다. 팀 기획안 「게임 영상 크리에이터 인스피레이션 플랫폼」의 YouTube 파트다.

## 1. 단계

| 단계 | 하는 일 | 맡는 쪽 | 명령 |
|---|---|---|---|
| 1 수집 | 인기 차트, 키워드 검색, 채널 통계를 가져온다 | 코드 | `collect` |
| 2 정규화 | 게임 이름을 하나로 맞추고, 쇼츠 여부와 채널 평균 대비 배수를 계산한다 | 코드 | `normalize` |
| 3 점수화 | 게임별 소재 점수를 계산한다 | 코드 | `score` |
| 4 분석 | 근거 데이터를 모으고, 어떤 게임을 어떤 각도로 다룰지 정한다 | 코드, trend-analyst | `analyze` |
| 5 기획안 | 훅 3안, 구간별 대본, 제목 3개, 썸네일, 저작권 체크리스트를 만든다 | plan-writer, 이미지 생성 API | `thumbnail` |
| 6 검증 | 규칙 검사 코드와 별도 검토 에이전트가 기획안을 확인한다 | 코드, plan-validator | `validate`, `review` |
| 7 영상 생성 | 대본, 자막, edit.json, 720p 프리뷰, 검수, 최종 렌더 | script-writer, FFmpeg, qa-reviewer | `video`, `qa` |
| 8 성과 기록 | 업로드한 영상의 조회수를 기록하고 가중치 보정안을 만든다 | 코드, performance-analyst | `perf` |

단계마다 결과는 `runs/<run_id>/`에 파일로 남고, `db push`로 Supabase에도 저장한다. 기획안의 에이전트 6개와 이 단계가 어떻게 짝을 이루는지는 [docs/architecture.md](docs/architecture.md)에 있다.

원칙은 네 가지다.

1. 점수, 배수, 중앙값은 코드가 계산한다. 에이전트는 그 값을 옮기고 근거 경로를 붙인다.
2. 점수는 정렬에만 쓴다. 조회수를 예측하는 문장은 규칙 검사가 막는다.
3. 기획안 검증, 프리뷰 검수, 업로드 같은 지점에서는 사람이 승인해야 다음 단계로 넘어간다. 순서는 코드가 강제한다.
4. 업로드는 사람이 한다. 이 저장소는 게시나 공유를 하지 않는다.

## 2. 설치

```bash
brew install ffmpeg               # Windows: winget install ffmpeg
pip install -r requirements.txt   # pytest만 필요. 파이프라인은 표준 라이브러리로 돈다
cp .env.example .env              # 키는 이 파일에 직접 입력한다
python -m pytest -q               # 테스트 17개, 네트워크 없이 돈다
```

`.env`에 넣는 값:

1. `YOUTUBE_API_KEY`: 수집과 성과 기록에 쓴다.
2. `OPENAI_API_KEY`: 썸네일 이미지를 생성할 때만 쓴다. `config/pipeline.json`의 `thumbnail.provider`를 `openai`로 바꿔야 호출한다.
3. `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`: `db push`에만 쓴다. Supabase SQL Editor에서 `db/schema.sql`을 먼저 실행한다.

## 3. Claude Code에서 쓰기

```
/youtube-pipeline 로블록스 트렌드로 쇼츠 하나 기획해줘. 실제 API로 수집해줘.
/youtube-pipeline 샘플 데이터로 처음부터 끝까지 연습하자.
/video-edit shot_02 시작을 0.5초 늦춰줘
/youtube-pipeline 지난주 올린 영상 성과 기록하고 가중치 보정안 보여줘
```

| 파일 | 역할 |
|---|---|
| `AGENTS.md` | 지킬 규칙, 영상 규격, 완료 기준. `CLAUDE.md`가 불러온다 |
| `.claude/skills/youtube-pipeline/SKILL.md` | 단계 순서와 멈춤 지점 |
| `.claude/skills/video-edit/SKILL.md` | edit.json 형식, 수정 방법, 프롬프트 예시 |
| `.claude/agents/*.md` | 서브에이전트 6개의 지시문 |
| `.claude/settings.json` | 읽기 명령은 자동 허용. API 수집, 썸네일 생성, 렌더, DB 저장, 가중치 적용은 실행 전에 묻는다. `.env` 읽기와 `clips/` 수정은 금지 |
| `config/pipeline.json` | 지역, 카테고리, 가중치, 영상 규격, 썸네일, 검수 기준 |
| `config/alias_dictionary.json` | 게임 별칭 사전. 시작용 10개 |
| `db/schema.sql` | Supabase 테이블 12개와 SQL 뷰 |

Claude Code는 개발과 시험에 쓰는 도구다. 웹 서비스에서는 서버가 Claude API를 호출해 같은 에이전트를 실행한다. 자세한 내용은 [docs/architecture.md](docs/architecture.md) 3절에 있다.

## 4. 명령

```bash
python -m yt_pipeline data --source api        # 1~4 근거 팩까지. sample, file --path 도 된다
python -m yt_pipeline status                   # 어디까지 했는지, 다음 할 일
python -m yt_pipeline validate                 # 규칙 검사
python -m yt_pipeline review --file runs/<id>/review.json
python -m yt_pipeline thumbnail                # 썸네일. --background 이미지.png 로 직접 찍은 화면에 문구만 얹을 수 있다
python -m yt_pipeline video timing             # script.json 으로 타이밍, 자막, edit.draft.json 생성
python -m yt_pipeline video check              # edit.json 검사
python -m yt_pipeline video render --plan-only # ffmpeg 명령만 보기
python -m yt_pipeline video render [--final]   # 720p 프리뷰 또는 최종
python -m yt_pipeline qa --file runs/<id>/07_video/output/preview_v1.mp4 [--visual v.json]
python -m yt_pipeline db export | push         # Supabase 테이블 모양으로 저장
python -m yt_pipeline report                   # 팀 총괄용 YouTubeReport
python -m yt_pipeline perf register|fetch|manual|summary|calibrate|apply
```

## 5. 점수

```
Score_yt = w1·수요 + w2·아웃라이어 + w3·신선도 − w4·경쟁도
```

네 항목을 어떻게 0~1로 계산하는지, 가중치를 언제 어떻게 보정하는지는 [docs/scoring.md](docs/scoring.md)에 있다.

## 6. 썸네일

`thumbnail` 명령이 기획안의 `thumbnail_brief`로 이미지 프롬프트를 만든다.

1. `provider`가 `none`이면 프롬프트만 `05_thumbnails/prompt.json`에 저장한다. 기본값이다.
2. `provider`가 `openai`이면 OpenAI Images API로 배경 이미지를 만든다. 호출마다 과금된다.
3. 이미지 모델은 한글을 자주 틀리게 그린다. 그래서 문구는 FFmpeg으로 따로 얹는다.
4. 프롬프트에는 게임 로고, 실존 인물, 저작권 있는 캐릭터를 넣지 않는다.

## 7. 상업 운영 전에 바꿀 것

유료 기능을 공개하기 전에 아래 도구의 요금제를 바꾼다.

1. Vercel Hobby는 개인·비상업 용도만 허용한다. Pro로 바꾼다.
2. Supabase Free 프로젝트는 1주 동안 쓰지 않으면 일시정지된다. Pro로 바꾼다.
3. 이미지 생성 API와 vidIQ는 상업 이용 조건을 확인한다.

도구별 표는 [docs/architecture.md](docs/architecture.md) 5절에 있다.

## 8. 한계

1. 채널 평균 조회수는 채널 전체 누적값이라 최근 성과와 다를 수 있다.
2. 게임 매칭은 별칭 문자열 포함 여부로 한다. 짧은 별칭은 관계없는 영상이 섞일 수 있다.
3. 영상 전환 효과는 cut과 fadein만 있다.
4. Claude는 소리를 듣지 못한다. 무음과 클리핑은 수치로만 확인하고, 발음은 사람이 듣는다.
5. `data/sample/`은 지어낸 연습용 데이터다. 실제 수치가 아니다.

## 9. 참고

1. 세미나 3회차 「ClaudeCode 기반 영상 편집 및 최종 검수」: AGENTS.md와 SKILL.md 구조, 자막(text)과 읽기 문장(say) 분리, 완료 보고 3분할
2. `bilibili-supervisor-agent`: 단계 구성, 코드 규칙 검사와 LLM 검토, 예측 표현 차단, 계약 모양
3. 영상 편집 파이프라인 슬라이드: edit.json, 720p 프리뷰, qa-reviewer
4. 지도교수 피드백(2026-11-19 Figma 코멘트): 이미지 생성 도구를 에이전트에 포함, DB 설계, 점수 기준 설명, 에이전트 구조도와 도구 목록, 상업 이용 요금제
