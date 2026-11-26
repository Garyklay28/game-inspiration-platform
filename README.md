# game-inspiration-platform

게임 영상 크리에이터 원스톱 인스피레이션 플랫폼 — **팀 총괄 저장소**

플랫폼별 서브 슈퍼바이저 두 개와, 이를 묶는 팀 총괄 슈퍼바이저로 구성된 멀티 에이전트 Proof of Concept입니다.

## 기말프로젝트 제출 안내 — 에이전트 아키텍처 · 코드 · 프롬프트

| 요구 사항 | 위치 |
|---|---|
| 에이전트 아키텍처 (Figma 기획서 추가분) | [docs/figma/](docs/figma/) — 기획서 12·13쪽 (16 팀 에이전트 아키텍처, 17 빌리빌리 서브 슈퍼바이저), [docs/architecture.md](docs/architecture.md) |
| 구조 선택: Supervisor vs 수평형 | 아래 「구조 선택」 |
| 코드 (Python, Proof of Concept) | [`team_supervisor/`](team_supervisor/) · [`bilibili/bili_agent/`](bilibili/bili_agent/) · [`youtube/yt_pipeline/`](youtube/yt_pipeline/) |
| 시스템 프롬프트 | 빌리빌리 7개 [`bilibili/bili_agent/prompts/`](bilibili/bili_agent/prompts/) · YouTube 6개 [`youtube/.claude/agents/`](youtube/.claude/agents/) |
| 실제 실행 결과 | [`bilibili/docs/example_*`](bilibili/docs/) (Claude API 실제 호출 보고서·기획안) |
| 에이전트별 PoC 데모 · 1차 결과물 | 빌리빌리 [`bilibili/docs/agent_outputs.md`](bilibili/docs/agent_outputs.md) (`cd bilibili && python demo_agents.py --agent <이름>`) |
| 팀 공용 DB 스키마 (기획안 13장) | [`youtube/db/schema.sql`](youtube/db/schema.sql) — 두 파트가 같은 테이블에 저장 (YouTube [`yt_pipeline/db.py`](youtube/yt_pipeline/db.py), 빌리빌리 [`team_db.py`](bilibili/bili_agent/tools/team_db.py), `platform` 열로 구분) |
| 점수 기준 | 빌리빌리 [`bilibili/docs/architecture.md`](bilibili/docs/architecture.md) · YouTube [`youtube/docs/scoring.md`](youtube/docs/scoring.md) |

### 구조 선택: 계층형 Supervisor

**Supervisor 구조(계층형)**를 선택했습니다. 수평형(에이전트끼리 대등하게 메시지를 주고받는 구조)이 아닙니다.

```
팀 총괄 슈퍼바이저 ─┬─ 빌리빌리 서브 슈퍼바이저 ─ 에이전트 6 (기획안 12장: 1 수집 · 2 정규화 · 3 점수화(코드) ·
                   │                                       4 분석 · 5 기획안(작성+검토) · 6 성과 기록)
                   └─ YouTube 파이프라인 ──── 서브에이전트 6 (trend-analyst · plan-writer · plan-validator ·
                                                           script-writer · qa-reviewer · performance-analyst)
```

| 기준 | Supervisor (선택) | 수평형 |
|---|---|---|
| 작업 순서 | 수집 → 분석 → 기획안 → 검증 순서가 분명해 한 곳에서 통제하기 쉬움 | 에이전트끼리 순서를 합의해야 해 흐름이 흔들림 |
| 안전장치 | 슈퍼바이저 단계에서 코드로 강제: 수집 전 분석 금지, 검증 전 제출 금지, 예측 표현 차단, 수정 횟수 상한 | 지킬 지점이 여러 에이전트에 흩어짐 |
| 맥락 관리 | 워커는 자기 도구와 지시만 받음. 원본 데이터는 공유 작업 공간에 두고 요약만 전달 | 대화가 에이전트 사이를 오가며 길어짐 |
| 팀 작업 | 플랫폼별로 서브 슈퍼바이저를 나눠 각자 개발, 계약(XxxTask → XxxReport)만 맞추면 합쳐짐 | 경계가 흐려 분담이 어려움 |
| 단점 | 슈퍼바이저가 병목·단일 실패 지점 → 플랫폼별 장애 격리, 최대 단계 수 제한으로 완화 | — |

수평형 요소는 한 곳만 둡니다: 빌리빌리 → YouTube 로 '해외 트렌드 소재 카드'를 넘기는 연결(총괄을 거쳐 전달).

| 폴더 | 담당 | 원본 저장소 | 실행 방식 |
|---|---|---|---|
| [`bilibili/`](bilibili/) | 곽우화 | [Garyklay28/bilibili-supervisor-agent](https://github.com/Garyklay28/bilibili-supervisor-agent) | Python + Anthropic SDK (슈퍼바이저 1 + 에이전트 6, 데이터는 Aside 브라우저 1순위) |
| [`youtube/`](youtube/) | 장유림 | [JangYurim0607/youtube-agent-pipeline](https://github.com/JangYurim0607/youtube-agent-pipeline) | Claude Code 스킬·서브에이전트 + Python 코드 단계 (썸네일 이미지 생성, Supabase 저장 포함) |
| [`team_supervisor/`](team_supervisor/) | 팀 공통 | (이 저장소) | 코드 라우터 + 보고서 병합 + 기획안 어댑터 |

두 파트는 원본 저장소의 커밋 히스토리(작성자 포함)를 그대로 가진 채 하위 폴더로 합쳐졌습니다(`git log -- bilibili/`, `git log -- youtube/`).

## 구조

```
                         TeamTask (intent, platforms, game/topic)
                                       │
                          ┌── 팀 총괄 슈퍼바이저 ──┐   (intent 표로 라우팅, LLM 없음)
                          ▼                         ▼
         빌리빌리 서브 슈퍼바이저            YouTube 파이프라인
         (Python, Claude API)               (Claude Code /youtube-pipeline)
         수집→정규화→점수→분석→              수집→정규화→점수→분석→기획안·썸네일→
         策划案→검증                         검증→영상 생성·검수→성과 기록
                          │                         │
                     BiliReport               YouTubeReport (runs/<id>/report.json)
                          └──────────┬──────────────┘
                                     ▼
            TeamReport: 플랫폼별 상태·요약 / 기획안 공통 보기(team-plan-view-v1)
                        / 기회 목록 / 빌리빌리 → YouTube 해외 트렌드 소재
```

자세한 설계: [docs/architecture.md](docs/architecture.md)

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

```bash
# 팀 총괄 (빌리빌리는 LLM 없이, YouTube 는 최근 실행 기록을 읽음)
python -m team_supervisor --intent trend_scan --bilibili-dry-run

# 빌리빌리 실제 실행 (bilibili/.env 에 ANTHROPIC_API_KEY 필요)
python -m team_supervisor --intent deep_dive --game 英雄联盟

# YouTube 는 youtube/ 폴더를 Claude Code 로 열어 /youtube-pipeline 으로 먼저 실행 → 그 결과를 총괄이 읽음
python -m team_supervisor --intent deep_dive --platforms youtube --youtube-run <run_id>
```

테스트 (각 파트는 자기 폴더에서):

```bash
python -m pytest -q tests_team                 # 총괄: 라우팅·어댑터 (11)
(cd bilibili && python -m pytest -q)           # 빌리빌리 (31)
(cd youtube && python -m pytest -q)            # YouTube (17, 렌더·썸네일 테스트 2개는 libass·drawtext 포함 ffmpeg 필요)
```

## 팀 intent

| 팀 intent | 빌리빌리 | YouTube |
|---|---|---|
| `trend_scan` | trend_scan | trend_scan |
| `deep_dive` | game_deep_dive | topic_deep_dive |
| `title_check` | title_check | — |
| `event_watch` | event_watch | — |
| `make_video` | — | make_video |
| `performance_review` | performance_review | performance_review |

## 한계

- YouTube 의 LLM 단계(분석·기획·검증·대본·검수)는 Claude Code 서브에이전트라 총괄이 Python 에서 직접 실행하지 못합니다. 총괄은 Claude Code 로 만든 실행 결과를 읽어 합칩니다.
- 두 플랫폼의 점수는 기준(데이터·공식 구성)이 달라 서로 비교·정렬하지 않습니다.
- 현재 두 별칭 사전에 겹치는 게임이 없어(빌리빌리: 중국 게임 15개, YouTube: 로블록스 10개) 게임 단위 교차 분석은 아직 없습니다.
