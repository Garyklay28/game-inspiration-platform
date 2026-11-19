# game-inspiration-platform

게임 영상 크리에이터 원스톱 인스피레이션 플랫폼 — **팀 총괄 저장소**

플랫폼별 서브 슈퍼바이저 두 개와, 이를 묶는 팀 총괄 슈퍼바이저로 구성된 멀티 에이전트 Proof of Concept입니다.

| 폴더 | 담당 | 원본 저장소 | 실행 방식 |
|---|---|---|---|
| [`bilibili/`](bilibili/) | 곽우화 | [Garyklay28/bilibili-supervisor-agent](https://github.com/Garyklay28/bilibili-supervisor-agent) | Python + Anthropic SDK (슈퍼바이저 1 + 워커 7) |
| [`youtube/`](youtube/) | 장유림 | [JangYurim0607/youtube-agent-pipeline](https://github.com/JangYurim0607/youtube-agent-pipeline) | Claude Code 스킬·서브에이전트 + Python 코드 단계 |
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
         수집→정규화→점수→분석→              수집→정규화→점수→분석→기획안→
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
python -m pytest -q tests_team                 # 총괄: 라우팅·어댑터 (9)
(cd bilibili && python -m pytest -q)           # 빌리빌리 (22)
(cd youtube && python -m pytest -q)            # YouTube (14, 렌더 테스트는 libass 포함 ffmpeg 필요)
```

## 팀 intent

| 팀 intent | 빌리빌리 | YouTube |
|---|---|---|
| `trend_scan` | trend_scan | trend_scan |
| `deep_dive` | game_deep_dive | topic_deep_dive |
| `title_check` | title_check | — |
| `event_watch` | event_watch | — |
| `make_video` | — | make_video |
| `performance_review` | — | performance_review |

## 한계

- YouTube 의 LLM 단계(분석·기획·검증·대본·검수)는 Claude Code 서브에이전트라 총괄이 Python 에서 직접 실행하지 못합니다. 총괄은 Claude Code 로 만든 실행 결과를 읽어 합칩니다.
- 두 플랫폼의 점수는 기준(데이터·공식 구성)이 달라 서로 비교·정렬하지 않습니다.
- 현재 두 별칭 사전에 겹치는 게임이 없어(빌리빌리: 중국 게임 15개, YouTube: 로블록스 10개) 게임 단위 교차 분석은 아직 없습니다.
