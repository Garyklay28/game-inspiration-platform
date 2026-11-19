# youtube-agent-pipeline

YouTube 게임 쇼츠(기본: 로블록스)용 에이전트 파이프라인 — Claude Code 에서 돌린다.

```
1 트렌드 수집 → 2 정규화 → 3 점수화 → 4 분석 → 5 기획안 → 6 검증 → 7 영상 생성(+검수) → 8 성과 기록
   (코드)        (코드)      (코드)     (코드+에이전트) (에이전트) (코드+에이전트) (에이전트+FFmpeg+검수)  (코드+에이전트)
                                                                                         ↑                         │
                                                                                         └──── 가중치 보정안 ───────┘
```

- **숫자는 코드가, 해석은 에이전트가.** 점수·배수·중앙값은 `yt_pipeline/` 이 계산하고, 에이전트는 그 파일의 경로를 근거로 인용한다.
- **edit.json 한 파일이 편집 기준.** Claude 는 이 파일을 고치고 FFmpeg 은 이 파일대로만 실행한다.
- **렌더 결과는 Claude 가 직접 검수.** ffprobe 규격 → 프레임 추출 → silencedetect·blackdetect → qa-reviewer PASS/FAIL.
- **순서는 코드가 강제.** 검증 통과 전 렌더 금지, 프리뷰 PASS(측정+화면) 전 최종 렌더 금지, 수정 3회 초과 시 사람에게 넘김.
- 빌리빌리 파트(`bilibili-supervisor-agent`)와 같은 계약 모양(`YouTubeTask → YouTubeReport`, 기획안 `plan-v1`)이라 팀 총괄 슈퍼바이저에 바로 붙는다.

## 설치

```bash
brew install ffmpeg            # Windows: winget install ffmpeg
pip install -r requirements.txt   # pytest 만. 파이프라인은 표준 라이브러리로 동작
cp .env.example .env           # YOUTUBE_API_KEY 입력 (채팅에 붙여 넣지 않는다)
python -m pytest -q            # 14개 테스트, 네트워크 불필요
```

## Claude Code 에서 쓰기

```
/youtube-pipeline 로블록스 트렌드로 쇼츠 하나 기획해줘. 실제 API 로 수집해줘.
/youtube-pipeline 샘플 데이터로 처음부터 끝까지 연습해보자.
/video-edit shot_02 시작을 0.5초 늦춰줘
/youtube-pipeline 지난주 올린 영상 성과 기록하고 가중치 보정안 보여줘
```

| 파일 | 역할 |
|---|---|
| `AGENTS.md` | AI 가 지킬 규칙·규격·완료 기준 (CLAUDE.md 가 불러온다) |
| `.claude/skills/youtube-pipeline/SKILL.md` | 8단계 순서와 멈춤 지점 |
| `.claude/skills/video-edit/SKILL.md` | edit.json 형식, 수정 요령, 프롬프트 템플릿 |
| `.claude/agents/*.md` | trend-analyst, plan-writer, plan-validator, script-writer, qa-reviewer, performance-analyst |
| `.claude/settings.json` | 읽기 전용 명령은 자동 허용, API 수집·렌더·가중치 적용은 묻기, `.env` 읽기·clips 수정 금지 |
| `config/pipeline.json` | 모든 숫자(지역·카테고리·가중치·영상 규격·검수 기준) |
| `config/alias_dictionary.json` | 게임 별칭 사전 (시작용 10개 — 검토 후 추가) |

## 명령 (직접 돌릴 때)

```bash
python -m yt_pipeline data --source api                 # 1~4a (sample / file --path 도 가능)
python -m yt_pipeline status                            # 어디까지 했나, 다음 할 일
python -m yt_pipeline validate                          # 6 규칙 검사
python -m yt_pipeline review --file runs/<id>/review.json
python -m yt_pipeline video timing                      # script.json → timing·자막·voice.wav·edit.draft.json
python -m yt_pipeline video check                       # edit.json 검사
python -m yt_pipeline video render --plan-only          # ffmpeg 명령만 보기
python -m yt_pipeline video render [--final]            # 720p 프리뷰 / 최종
python -m yt_pipeline qa --file runs/<id>/07_video/output/preview_v1.mp4 [--visual v.json]
python -m yt_pipeline report                            # YouTubeReport (report.json)
python -m yt_pipeline perf register|fetch|manual|summary|calibrate|apply
```

## 점수 (정렬 참고용 — 조회수 예측 아님)

```
Score_yt = w1·수요 + w2·아웃라이어 + w3·신선도 − w4·경쟁도      (각 0~1, 초기 가중치 모두 1.0)
수요       시간당 조회수 합 + 인기 차트·검색 순위 가중치
아웃라이어 채널 평균 조회수 대비 배수의 중앙값 (5배 이상 = 1)  ← 1of10 방식
신선도     게시 후 경과 시간 반감기 72시간
경쟁도     풀 안 같은 주제 영상 수
```
성과가 8개 이상 쌓이면 `perf calibrate` 가 항목별 상관(72시간 조회수 로그 기준)으로 보정안을 `config/weights.proposed.json` 에 만든다. 적용은 사람이 `perf apply`.

## 데이터 수집 원칙

- YouTube Data API v3 공식 엔드포인트만: `videos.list`(인기 차트, 게임 카테고리 20, 지역 KR), `search.list`(키워드, 최근 7일, 4분 미만), `channels.list`(채널 평균). 하루 기본 쿼터 10,000 units, 1회 수집 ≈ 키워드 수×100 + 5 units.
- 다른 도구(vidIQ MCP 등) 결과는 간단형 JSON 으로 저장해 `--source file` 로 넣는다.
- `data/sample/youtube_sample.json` 은 **지어낸 연습용 데이터**다. 이걸로 만든 기획안·보정은 경고가 붙고 성과 보정에서 빠진다.

## 한계

- 채널 평균 조회수는 채널 전체 누적(총 조회수 ÷ 영상 수)이라 최근 성과와 다를 수 있다.
- 주제 매칭은 별칭 문자열 포함 여부라 짧은 별칭(예: "doors")은 오탐이 있을 수 있다.
- 전환 효과는 cut / fadein 만 지원. 크로스페이드는 아직 없다.
- Claude 는 소리를 듣지 못한다. 무음·클리핑은 수치로만 보고, 발음·억양은 사람이 듣는다.
- 업로드는 하지 않는다. 사람이 올린 뒤 `perf register` 로 연결한다.

## 참고

- 세미나 3회차 「ClaudeCode 기반 영상 편집 및 최종 검수」: AGENTS.md / SKILL.md 구조, text·say 분리, 받아쓰기 검증, 완료 보고 3분할
- `bilibili-supervisor-agent`: 수집→정규화→점수→분석→기획안→검증 흐름, 코드 규칙 검사 + LLM 검토, 예측 표현 차단, 계약 모양
- 편집 파이프라인 슬라이드: ffprobe → FFmpeg → 자막 → 사운드 → 렌더·검수, edit.json, 프리뷰 720p, qa-reviewer
