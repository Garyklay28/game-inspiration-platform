# bilibili-supervisor-agent

게임 영상 크리에이터 원스톱 인스피레이션 플랫폼 — **빌리빌리 서브 슈퍼바이저** (Proof of Concept)

- 기획안(Figma): 08장 빌리빌리 모드 *"이벤트 중심 + 커뮤니티 반응"*, 12장 「에이전트 6개 구조도」, 13장 「데이터베이스 설계」
- 담당: 곽우화 (빌리빌리 파트 전체) · 팀 저장소: [game-inspiration-platform](https://github.com/Garyklay28/game-inspiration-platform)
- 언어: Python 3.9+ / Claude API (Anthropic 공식 Python SDK, tool use 루프 직접 구현, 모델 `claude-sonnet-5-5`)

## 구조: 수직(계층형 Supervisor) + 에이전트 6개

```
팀 총괄 슈퍼바이저 ──BiliTask──▶ 빌리빌리 서브 슈퍼바이저 (Claude)
                  ◀─BiliReport──      │ delegate (에이전트끼리는 직접 대화하지 않음)
                                       ├─▶ 1 수집        collector    Aside CSV 1순위 · 공개 API 대체
                                       ├─▶ 2 정규화      normalizer   별칭 통일(제목+화제 태그) · 별칭 후보 제안
                                       ├─▶ 3 점수화      scorer       Score_bili (코드만, LLM 없음)
                                       ├─▶ 4 분석        analyst      이벤트·핫키워드·반응률·길이·제목·해외 트렌드 카드
                                       ├─▶ 5 기획안      planner      작성 → 규칙 검사(코드) → 검토, 실패 시 1회 수정
                                       └─▶ 6 성과 기록   performance  업로드 성과 해석 · 가중치 보정안(적용은 사람)
                              공유 작업 공간 ──▶ 팀 공용 DB (13장 테이블, platform='bilibili')
```

수직 구조를 고른 이유(수평 구조와 비교), 에이전트별 코드·프롬프트·도구·DB 대응표, Aside 데이터 흐름, 가드레일은
**[docs/architecture.md](docs/architecture.md)** 에 있습니다. 시스템 프롬프트: **[bili_agent/prompts/](bili_agent/prompts/)** (8개, 한국어).

| 단계 | 코드 | 프롬프트 |
|---|---|---|
| 슈퍼바이저 | `bili_agent/agents/supervisor.py` | `supervisor.md` |
| 1 수집 | `bili_agent/agents/workers/w1_collector.py` | `w1_collector.md` |
| 2 정규화 | `w2_normalizer.py` | `w2_normalizer.md` |
| 3 점수화 | `w3_scorer.py` | — (코드만) |
| 4 분석 | `w4_analyst.py` | `w4_analyst.md` |
| 5 기획안 | `w5_planner.py` | `w5_plan_writer.md`, `w5_plan_reviewer.md` |
| 6 성과 기록 | `w6_performance.py` | `w6_performance.md` |

## 데이터: Aside 브라우저

빌리빌리 랭킹·영상 상세 API 는 일반 요청에 봇 차단(-352/412)이 걸립니다. 그래서 사용자가 **Aside 브라우저**로 빌리빌리를 수집해 CSV 로 내보내고, 수집 에이전트가 그 CSV 를 1순위로 읽습니다.

1. Aside 에서 빌리빌리를 열고 영상(반응률·제목·길이·태그), 핫키워드, 공식 활동, (업로드 후) 성과를 CSV 로 내보낸다.
2. 파일을 `data/aside/` 에 둔다: `*videos*.csv`, `*hot_keyword*.csv`, `*event*.csv`, `*performance*.csv`
3. 실행하면 48시간 이내 파일은 그대로 쓰고, 없거나 오래됐으면 공개 API(종합 인기·핫서치)로 대체한다.

열 이름은 영어·한국어·중국어 모두 인식하고, 인코딩(UTF-8/GB18030/CP949)도 자동 판별합니다.

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # ANTHROPIC_API_KEY 입력
```

```bash
python main.py --intent trend_scan --dry-run                      # LLM 없이 1~4단계 데이터 파이프라인 (무료)
python main.py --intent game_deep_dive --game 英雄联盟 --db-export  # 6단계 에이전트 실행 + 팀 DB 행 저장
python main.py --intent title_check --title "BLG夺冠了！S16决赛全程回顾"
python main.py --intent event_watch
python main.py register-upload --bvid BV1xx --report outputs/report_x.json   # 올린 영상을 기획안과 연결
python main.py --intent performance_review                        # 6 성과 기록
python -m pytest -q                                               # 오프라인 테스트 (가짜 LLM)
```

### 에이전트별 데모 (1차 결과물)

```bash
python demo_agents.py --agent collector        # 에이전트 하나: 입력 → 코드가 한 일 → LLM 결과 (실제 실행 기록 재생, 비용 0)
python demo_agents.py --agent analyst --live   # 그 에이전트만 Claude 로 지금 다시 실행 (앞 단계는 코드·기록으로 준비)
python demo_agents.py --all --markdown docs/agent_outputs.md
```

6개 에이전트의 1차 결과물 정리: **[docs/agent_outputs.md](docs/agent_outputs.md)** (6 성과 기록은 아직 업로드가 없어 가상의 예시 데이터)

결과: `outputs/report_*.json`(BiliReport), `*_plan.json`(策划案, 영상 파이프라인 입력), `*_plan.md`(팀 공유 문서), `*_db_rows.json`(팀 DB 행).

## 원칙

- **숫자는 코드가, 해석은 LLM 이** — 점수·배수·중앙값은 결정적 코드. 보고서의 점수도 코드 계산값을 붙인다.
- **점수는 정렬 참고용** — 조회수 예측 표현은 정규식으로 찾아 기획안·최종 요약 모두에서 막는다.
- **순서는 LLM, 안전장치는 코드** — 1→2→3→4→5 순서, 수집 0개 진행, 검증 없는 제출, 가중치 자동 적용을 코드가 막는다.
- **출처 표시** — 모든 데이터에 aside / live / snapshot 출처와 파일 나이를 기록한다.

## 한계

- Aside CSV 의 실제 열 이름은 수업 예시 화면 기준으로 맞췄다. 새 CSV 를 받으면 별칭표(`bili_agent/tools/aside_import.py`)로 조정한다.
- 별칭 사전(15개 게임) 밖의 게임은 정규화 에이전트가 후보로만 제안하고, 사람이 검토해 반영한다.
- 이벤트 날짜(마감일)는 수집하지 않는다.
