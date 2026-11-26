# 상세 구조도

팀 전체 → 플랫폼 분기 → 에이전트(단계) 하나하나까지 내려가며 그린 구조도입니다. 모든 그림은 현재 코드 기준입니다(함수·파일·프롬프트 이름 그대로).
요약 설명은 [architecture.md](architecture.md), 저장소 안내는 [README](../README.md)에 있습니다.

**목차**

0. [그림 읽는 법](#0-그림-읽는-법)
1. [전체 지도](#1-전체-지도)
2. [팀 총괄 슈퍼바이저](#2-팀-총괄-슈퍼바이저) — 처리 흐름 · intent 라우팅 · 데이터 계약 · 기획안 공통 보기
3. [빌리빌리 분기](#3-빌리빌리-분기) — 전체 · 실행 순서 · intent별 경로 · 에이전트 1~6 · 가드레일
4. [YouTube 분기](#4-youtube-분기) — 전체 · 단계표 · 기획안/검증 · 썸네일 · 영상 생성 · 성과 기록 · 점수 · 가드레일
5. [TikTok 분기 (예정)](#5-tiktok-분기-예정)
6. [팀 공용 DB](#6-팀-공용-db)
7. [플랫폼 사이 연결: 빌리빌리 → YouTube](#7-플랫폼-사이-연결-빌리빌리--youtube)

---

## 0. 그림 읽는 법

```mermaid
flowchart LR
    L1["코드<br/>(LLM 없음, 결정적 계산)"]:::code
    L2(["Claude 에이전트<br/>(LLM)"]):::llm
    L3{"사람 승인 / 판단"}:::human
    L4[("파일 · DB")]:::store
    L5{{"코드 가드레일<br/>(막는 지점)"}}:::guard
    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

- 실선 화살표: 실제 호출·데이터 이동. 점선 화살표: 선택 경로이거나 참고용 전달.
- 원칙(세 분기 공통): **숫자는 코드가, 해석은 LLM 이** · **점수는 정렬 참고용(조회수 예측 아님)** · **순서·안전장치는 코드가 강제**.

---

## 1. 전체 지도

```mermaid
flowchart TB
    U["크리에이터 / 웹 화면 (Next.js)"]:::human
    TS["팀 총괄 슈퍼바이저<br/>team_supervisor/ · 코드 라우터, LLM 없음"]:::code
    U <-->|"↓ TeamTask: intent · platforms · game · topic · title<br/>↑ TeamReport: 플랫폼별 상태 · 기획안 공통 보기 · 기회 목록 · 교차 소재"| TS

    subgraph BILI["빌리빌리 분기 (곽우화)"]
        direction TB
        BS(["서브 슈퍼바이저 (Claude API)<br/>delegate · submit_report"]):::llm
        ASIDE[("Aside 브라우저 수집<br/>data/aside/*.json · *.csv")]:::store
        B1(["1 수집<br/>collector"]):::llm
        B2(["2 정규화<br/>normalizer"]):::llm
        B3["3 점수화<br/>scorer · 코드만"]:::code
        B4(["4 분석<br/>analyst"]):::llm
        B5(["5 기획안<br/>writer + reviewer"]):::llm
        B6(["6 성과 기록<br/>performance"]):::llm
        BS --> B1 --> B2 --> B3 --> B4 --> B5
        ASIDE --> B1
        BS -.->|"performance_review 일 때만"| B6
    end

    subgraph YT["YouTube 분기 (장유림)"]
        direction TB
        YO(["오케스트레이터 스킬<br/>/youtube-pipeline (Claude Code)"]):::llm
        YAPI[("YouTube Data API v3")]:::store
        Y13["1 수집 · 2 정규화 · 3 점수화<br/>collect · normalize · score"]:::code
        Y4(["4 분석<br/>trend-analyst"]):::llm
        Y56(["5 기획안 · 6 검증<br/>plan-writer · plan-validator"]):::llm
        Y6b["6b 썸네일<br/>thumbnail"]:::code
        Y7(["7 영상 생성<br/>script-writer · qa-reviewer"]):::llm
        Y8(["8 성과 기록<br/>performance-analyst"]):::llm
        YO --> Y13 --> Y4 --> Y56 --> Y6b --> Y7 --> Y8
        YAPI --> Y13
    end

    subgraph TT["TikTok 분기 (예정)"]
        T0["TikTok 서브 슈퍼바이저<br/>(예정)"]:::code
    end

    TS <-->|"↓ BiliTask<br/>↑ BiliReport (+ 해외 트렌드 카드)"| BS
    TS <-->|"↓ runs/run_id 읽기<br/>↑ YouTubeReport"| YO
    TS -.->|"예정"| T0

    DB[("팀 공용 DB · Supabase<br/>youtube/db/schema.sql")]:::store
    B5 -->|"platform = bilibili"| DB
    Y8 -->|"platform = youtube"| DB
    T0 -.->|"platform = tiktok"| DB

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

| 분기 | 실행 방식 | 에이전트 수 | 결과 형식 | 코드 |
|---|---|---|---|---|
| 팀 총괄 | Python 코드 라우터 (LLM 없음) | 0 | `TeamReport` | [`team_supervisor/`](../team_supervisor/) |
| 빌리빌리 | Python + Anthropic SDK tool-use 루프, 모델 `claude-sonnet-5-5` | 슈퍼바이저 1 + 에이전트 6 (5 기획안은 작성·검토 2개) | `BiliReport` | [`bilibili/bili_agent/`](../bilibili/bili_agent/) |
| YouTube | Claude Code 스킬 + 서브에이전트 + Python 코드 단계 | 서브에이전트 6 | `YouTubeReport` (`runs/<id>/report.json`) | [`youtube/yt_pipeline/`](../youtube/yt_pipeline/), [`youtube/.claude/`](../youtube/.claude/) |
| TikTok | 조사 후 확정 | — | (같은 계약을 따를 예정) | — |

---

## 2. 팀 총괄 슈퍼바이저

### 2-1. 처리 흐름

`TeamSupervisor.run()` ([supervisor.py](../team_supervisor/supervisor.py)) 한 번이 하는 일입니다. 판단할 거리가 없어서 LLM 을 쓰지 않습니다. ① 플랫폼마다 보내고 상태를 정한 뒤 ② `ok` 인 보고서만 합칩니다.

**① 라우팅과 상태 결정**

```mermaid
flowchart TB
    A["TeamTask 검사<br/>intent 6개 중 하나 · platforms 는 bilibili / youtube"]:::code
    A -->|"잘못된 값"| AX{{"ValueError 로 거부"}}:::guard
    A --> L["플랫폼마다 반복"]:::code
    L --> M{"INTENT_MAP<br/>intent → 플랫폼 intent"}:::code
    M -->|"None"| S1["status = unsupported"]:::code
    M -->|"bilibili"| CB["platforms.run_bilibili<br/>BiliSupervisor.run (LLM)<br/>또는 run_dry (--bilibili-dry-run)"]:::code
    M -->|"youtube"| CY["platforms.load_youtube<br/>지정한 또는 최근 runs/run_id<br/>→ 팀원 코드 report.build"]:::code
    CB -->|"정상"| S4["status = ok"]:::code
    CB -->|"예외"| S2["status = error<br/>다른 플랫폼은 계속 진행"]:::guard
    CY -->|"정상"| S4
    CY -->|"예외"| S2
    CY -->|"실행 기록 없음"| S3["status = no_run<br/>+ 실행 안내 경고"]:::code

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

**② 보고서 병합**

```mermaid
flowchart TB
    S4[("status = ok 인 플랫폼 보고서<br/>BiliReport · YouTubeReport")]:::store
    S4 --> SM{{"YouTube 샘플 데이터면<br/>경고 추가"}}:::guard
    S4 --> NP["plan_adapter.normalize_plan<br/>plan-v1 → team-plan-view-v1"]:::code
    S4 --> OP["_opportunities<br/>플랫폼 표시를 붙여 합침<br/>점수 기준이 달라 서로 정렬하지 않음"]:::code
    S4 --> CP["_cross_platform<br/>빌리빌리 overseas_trend_cards<br/>→ YouTube 참고"]:::code
    NP --> NW{{"모르는 라벨 → unknown:이름 + 경고<br/>status ≠ validated → 검증 미통과 경고"}}:::guard
    ST["unsupported · error · no_run<br/>상태와 안내만 기록"]:::code
    NP --> R
    OP --> R
    CP --> R
    SM --> R
    NW --> R
    ST --> R
    R[("TeamReport<br/>summary_ko · platforms · plans · opportunities<br/>cross_platform · warnings")]:::store

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

| 상태 | 언제 | 보고서에 남는 것 |
|---|---|---|
| `ok` | 플랫폼 보고서를 받음 | 요약, run_id, 경고 수, 데이터 출처, 원본 보고서 |
| `unsupported` | 그 플랫폼이 이 intent 를 지원하지 않음 (예: YouTube 의 `title_check`) | 안내 문구 |
| `no_run` | YouTube 실행 폴더가 없음 | Claude Code 로 `/youtube-pipeline` 을 먼저 실행하라는 경고 |
| `error` | 실행 중 예외 (API 키 없음 등) | 예외 내용. 다른 플랫폼 결과는 그대로 보고 |

### 2-2. intent 라우팅 (`INTENT_MAP`)

```mermaid
flowchart LR
    I1["팀 trend_scan<br/>트렌드 훑기"]:::code --> I1b(["빌리빌리 trend_scan"]):::llm
    I1 --> I1y(["YouTube trend_scan"]):::llm
    I2["팀 deep_dive<br/>게임·주제 하나 깊이"]:::code --> I2b(["빌리빌리 game_deep_dive"]):::llm
    I2 --> I2y(["YouTube topic_deep_dive"]):::llm
    I3["팀 title_check<br/>제목 진단"]:::code --> I3b(["빌리빌리 title_check"]):::llm
    I3 -.-> I3y["YouTube: unsupported"]:::off
    I4["팀 event_watch<br/>공식 활동 감시"]:::code --> I4b(["빌리빌리 event_watch"]):::llm
    I4 -.-> I4y["YouTube: unsupported"]:::off
    I5["팀 make_video<br/>영상 만들기"]:::code -.-> I5b["빌리빌리: unsupported"]:::off
    I5 --> I5y(["YouTube make_video"]):::llm
    I6["팀 performance_review<br/>성과 기록"]:::code --> I6b(["빌리빌리 performance_review"]):::llm
    I6 --> I6y(["YouTube performance_review"]):::llm

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef off fill:#f2f2f2,stroke:#999,color:#555,stroke-dasharray:4 3
```

점선 회색 칸은 그 플랫폼이 지원하지 않는 조합이며, 총괄 보고서에 `unsupported` 로 남습니다.

### 2-3. 데이터 계약

```mermaid
classDiagram
    class TeamTask {
        +str intent
        +tuple platforms
        +str game
        +str topic
        +str title
        +str youtube_run_id
        +str task_id
    }
    class BiliTask {
        +str intent
        +str game
        +str user_title
        +int period_days
        +str note
        +str task_id
    }
    class YouTubeTask {
        +str intent
        +str topic
        +str source
    }
    class BiliReport {
        +str summary_ko
        +str run_id
        +list opportunities
        +list events
        +dict title_diagnosis
        +dict duration_advice
        +list overseas_trend_cards
        +list alias_candidates
        +dict plan
        +dict plan_validation
        +dict performance
        +dict agent_stages
        +list data_sources
        +list agent_trace
        +dict usage
        +list warnings
    }
    class YouTubeReport {
        +str summary_ko
        +str run_id
        +list opportunities
        +dict duration_advice
        +list alias_candidates
        +dict plan
        +dict plan_validation
        +dict video
        +dict performance
        +list data_sources
        +list agent_trace
        +list warnings
    }
    class TeamReport {
        +str task_id
        +str intent
        +str summary_ko
        +dict platforms
        +list plans
        +list opportunities
        +dict cross_platform
        +list warnings
    }
    TeamTask ..> BiliTask : INTENT_MAP 변환
    TeamTask ..> YouTubeTask : INTENT_MAP 변환
    BiliTask ..> BiliReport : 빌리빌리 분기 실행
    YouTubeTask ..> YouTubeReport : YouTube 분기 실행
    BiliReport --> TeamReport : 병합
    YouTubeReport --> TeamReport : 병합
```

### 2-4. 기획안 공통 보기 (`team-plan-view-v1`)

두 분기의 기획안(plan-v1)은 언어와 라벨이 다릅니다. [plan_adapter.py](../team_supervisor/plan_adapter.py) 가 같은 ID 로 맞춥니다.

```mermaid
flowchart LR
    BP[("빌리빌리 plan-v1<br/>간체 중국어 · 필드명 *_zh")]:::store
    YP[("YouTube plan-v1<br/>한국어")]:::store
    BP --> N["normalize_plan<br/>원본은 바꾸지 않음"]:::code
    YP --> N
    N --> CT["content_type<br/>攻略·공략 → guide<br/>实况·실황 → lets_play<br/>分析·분석 → analysis<br/>评测·리뷰 → review<br/>밈·하이라이트 → meme_highlight"]:::code
    N --> HK["hooks<br/>先看结果·결과 먼저 → result_first<br/>提问·질문 → question<br/>挑战/反转·도전/반전 → challenge_twist"]:::code
    N --> SC["sections<br/>开场·훅 → hook · 问题·문제 → problem<br/>正文·본문 → body · CTA → cta<br/>结尾·엔딩 → ending"]:::code
    N --> ETC["score.value · thumbnail(image_prompt 포함)<br/>status · data_sources<br/>나머지 원본 키 → extras 에 보존"]:::code
    N -->|"표에 없는 라벨"| UK{{"unknown:라벨 로 남기고 경고<br/>(버리지 않음)"}}:::guard

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

---

## 3. 빌리빌리 분기

기획안 12장 「에이전트 6개 구조도」를 **수직(계층형) Supervisor** 구조로 구현했습니다. 에이전트끼리는 직접 대화하지 않고, 지시는 슈퍼바이저가, 데이터는 공유 작업 공간(Workspace)이 전달합니다.

### 3-1. 전체 구조

```mermaid
flowchart TB
    IN["BiliTask<br/>intent · game · user_title"]:::code --> SUP
    SUP(["빌리빌리 서브 슈퍼바이저 · Claude<br/>prompts/supervisor.md · 최대 12단계<br/>도구: delegate · submit_report"]):::llm

    SUP -->|"delegate(worker, instruction)"| GATE
    subgraph GATE["delegate 관문 (코드)"]
        direction LR
        G1{{"requires 체인<br/>앞 단계가 끝나야 실행"}}:::guard
        G2{{"수집 영상 0개면<br/>뒤 단계 진행 금지"}}:::guard
        G3{{"같은 에이전트<br/>중복 실행 금지"}}:::guard
    end

    GATE --> W1(["1 수집 collector<br/>w1_collector.md"]):::llm
    GATE --> W2(["2 정규화 normalizer<br/>w2_normalizer.md"]):::llm
    GATE --> W3["3 점수화 scorer<br/>코드만 (run_code)"]:::code
    GATE --> W4(["4 분석 analyst<br/>w4_analyst.md"]):::llm
    GATE --> W5(["5 기획안 planner<br/>w5_plan_writer.md · w5_plan_reviewer.md"]):::llm
    GATE --> W6(["6 성과 기록 performance<br/>w6_performance.md"]):::llm

    WS[("공유 작업 공간 Workspace<br/>raw_videos · videos · keywords · aside_events<br/>data_sources · findings · cache · trace")]:::store
    W1 <--> WS
    W2 <--> WS
    W3 <--> WS
    W4 <--> WS
    W5 <--> WS
    W6 <--> WS

    SUP -->|"submit_report(summary_ko, warnings)"| G4{{"예측 표현 정규식 검사<br/>check_report_submission"}}:::guard
    G4 -->|"걸림 → 다시 쓰게 함"| SUP
    G4 -->|"통과"| BR["build_report (코드)<br/>점수·구성 요소는 코드 계산값을 붙임"]:::code
    BR --> OUT[("BiliReport → 총괄")]:::store
    WS -->|"team_db.build_rows"| DB[("팀 공용 DB<br/>--db-export / --db-push")]:::store

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

| 에이전트 | 코드 | LLM | 앞 단계(requires) | 도구 | 제출 | DB 테이블 |
|---|---|---|---|---|---|---|
| 슈퍼바이저 | [supervisor.py](../bilibili/bili_agent/agents/supervisor.py) | ✅ | — | `delegate`, `submit_report` | `summary_ko`, `warnings` | — |
| 1 수집 | [w1_collector.py](../bilibili/bili_agent/agents/workers/w1_collector.py) | ✅ | — | `load_aside`, `collect_popular_games`, `collect_trending`, `load_ranking_snapshot` | `summary_ko`, `data_quality_notes` | raw_snapshots |
| 2 정규화 | [w2_normalizer.py](../bilibili/bili_agent/agents/workers/w2_normalizer.py) | ✅ (+코드 pre_run) | collector | `list_unmatched_titles`, `resolve_game` | `summary_ko`, `alias_candidates`, `data_quality_notes` | videos, game_aliases(사람 검토 후) |
| 3 점수화 | [w3_scorer.py](../bilibili/bili_agent/agents/workers/w3_scorer.py) | ❌ | normalizer | (없음, 코드가 바로 계산) | — | topic_scores |
| 4 분석 | [w4_analyst.py](../bilibili/bili_agent/agents/workers/w4_analyst.py) | ✅ | scorer | 9개 (아래 3-7) | `opportunities`, `events`, `duration_advice`, `title_review`, `overseas_trend_cards`, `claims` | analyses |
| 5 기획안 | [w5_planner.py](../bilibili/bili_agent/agents/workers/w5_planner.py) | ✅ ×2 | analyst | 작성: `get_plan_context`, `lookup_evidence` / 검토: `get_plan`, `run_rule_checks`, `lookup_evidence` | plan-v1 / `passed`, `issues` | plans |
| 6 성과 기록 | [w6_performance.py](../bilibili/bili_agent/agents/workers/w6_performance.py) | ✅ | — (별도 경로) | `list_uploads`, `get_checkpoints`, `propose_weights` | `per_video`, `next_actions_ko`, `weight_note_ko` | uploads, performance, score_weights |

### 3-2. 실행 순서 (trend_scan · game_deep_dive)

```mermaid
sequenceDiagram
    autonumber
    participant T as 팀 총괄
    participant S as 서브 슈퍼바이저 (Claude)
    participant C as 1 수집
    participant N as 2 정규화
    participant SC as 3 점수화 (코드)
    participant A as 4 분석
    participant P as 5 기획안
    participant WS as 작업 공간

    T->>S: BiliTask(intent, game)
    S->>C: delegate(collector, 지시)
    C->>WS: load_aside → (부족하면) collect_popular_games / collect_trending
    C-->>S: summary_ko, data_quality_notes
    S->>N: delegate(normalizer)
    Note over N,WS: pre_run normalize_pool (코드)<br/>중복 제거 · 30일 초과 제외 · 별칭 최장 일치
    N->>WS: videos(game_ids), 별칭 후보
    N-->>S: summary_ko, alias_candidates
    S->>SC: delegate(scorer)
    SC->>WS: Score_bili (game_scores)
    SC-->>S: 상위 게임과 점수
    S->>A: delegate(analyst)
    A->>WS: 도구 9개로 근거 조회, claims 마다 근거
    A-->>S: opportunities, events, duration_advice, overseas_trend_cards
    S->>P: delegate(planner)
    loop 최대 2회 (첫 작성 + 수정 1회)
        P->>P: plan_writer 작성 → check_plan(코드) → plan_reviewer 검토
    end
    P-->>S: plan_id, status (validated / needs_review)
    S->>S: submit_report (예측 표현 검사 통과해야 종료)
    S-->>T: BiliReport (점수는 코드 값)
```

### 3-3. intent별 경로

슈퍼바이저(LLM)가 순서를 정하지만, 앞 단계를 건너뛰는 호출은 코드가 거부합니다. 아래는 LLM 없이 돌릴 때(`--dry-run`)의 기본 계획 `DEFAULT_PLANS` 와 같습니다.

```mermaid
flowchart TB
    subgraph P1["trend_scan · game_deep_dive"]
        direction LR
        a1["1 수집"] --> a2["2 정규화"] --> a3["3 점수화"] --> a4["4 분석"] --> a5["5 기획안"]
    end
    subgraph P2["title_check · event_watch"]
        direction LR
        b1["1 수집"] --> b2["2 정규화"] --> b3["3 점수화"] --> b4["4 분석<br/>제목 진단 / 공식 활동"]
    end
    subgraph P3["performance_review"]
        direction LR
        c6["6 성과 기록"]
    end
    P1 ~~~ P2 ~~~ P3
```

### 3-4. 1 수집 (collector)

```mermaid
flowchart TB
    AJ[("data/aside/*.json<br/>Aside 크롤러 결과")]:::store --> LA
    AC[("data/aside/*videos*.csv · *hot_keyword*.csv<br/>*event*.csv · *performance*.csv")]:::store --> LA
    LA["load_aside<br/>JSON 우선, 없으면 CSV<br/>열 이름 한·중·영 인식, 인코딩 UTF-8/GB18030/CP949 자동"]:::code
    LA --> FR{{"신선도 검사<br/>파일 나이 ≤ 48시간<br/>영상 게시 ≤ 30일"}}:::guard
    FR -->|"최근 영상 ≥ 30개"| POOL
    FR -->|"최근 영상 < 30개 또는 Aside 없음"| PG["collect_popular_games<br/>/x/web-interface/popular<br/>游戏(pid_v2=1008)만"]:::code
    PG --> POOL
    KW{"Aside 핫키워드가<br/>충분한가 (≥20)"}:::code
    LA --> KW
    KW -->|"부족"| TR["collect_trending<br/>/wbi/search/square 핫서치 30개"]:::code
    TR --> POOL
    KW -->|"충분"| POOL
    RS[("ranking_game_*.json<br/>사람이 저장한 랭킹 스냅샷")]:::store --> LR["load_ranking_snapshot"]:::code --> POOL
    BLK{{"ranking/v2(-352) · view(412) 봇 차단은<br/>쿠키 위조 등으로 우회하지 않음"}}:::guard
    POOL[("작업 공간<br/>raw_videos · keywords · aside_events<br/>data_sources: 출처(aside/live/snapshot)·파일 나이")]:::store
    POOL --> LLM(["collector (Claude)<br/>어떤 도구를 쓸지 결정 · 데이터 품질 메모"]):::llm
    LLM --> OUT["submit_findings<br/>summary_ko · data_quality_notes"]:::code

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

| 항목 | 내용 |
|---|---|
| 입력 | Aside 브라우저 수집 파일(1순위), 빌리빌리 공개 API(대체·보충), 사람이 저장한 랭킹 스냅샷 |
| 코드가 하는 일 | 파일 읽기, 열 이름·숫자(万/亿) 변환, 신선도 판정, 부족분 API 보충, 출처 기록 |
| LLM 이 하는 일 | 상황에 맞게 도구 선택, 데이터 품질 문제를 문장으로 정리 |
| 출력 | `raw_videos`, `keywords`, `aside_events`, `data_sources` → DB `raw_snapshots` |
| 막는 것 | 수집 0개면 다음 단계 진행 금지(슈퍼바이저 관문), 봇 차단 우회 안 함 |

### 3-5. 2 정규화 (normalizer)

```mermaid
flowchart TB
    RV[("raw_videos")]:::store --> NP
    subgraph NP["pre_run: normalize_pool (코드)"]
        direction TB
        n1["bvid 중복 제거"]:::code --> n2["게시 30일 초과 영상 제외<br/>출처별 제외 수 기록"]:::code
        n2 --> n3["제목 + 화제 태그에서 별칭 찾기<br/>긴 별칭 우선(최장 일치)"]:::code
        n3 --> n4["game_ids 부여"]:::code
    end
    AD[("data/alias_dictionary.json<br/>게임 18개 · 한·중·영 별칭<br/>+ 팀 DB games · game_aliases")]:::store --> n3
    EX["예: 「明日方舟：终末地」<br/>→ arknights_endfield (明日方舟 아님)"]:::code -.-> n3
    n4 --> V[("videos (game_ids 포함)")]:::store
    n4 --> LLM(["normalizer (Claude)<br/>list_unmatched_titles: 매칭 안 된 제목·태그 (조회수 순)<br/>resolve_game: 이름 → 표준 game_id"]):::llm
    LLM --> AC["alias_candidates<br/>사전에 없는 게임·별칭 후보"]:::code
    AC --> H{"사람 검토"}:::human
    H -->|"승인한 것만"| AD

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
```

| 항목 | 내용 |
|---|---|
| 입력 | `raw_videos`, 별칭 사전 |
| 코드가 하는 일 | 중복·오래된 영상 정리, 별칭 최장 일치로 게임 매칭 (`alias_store.find_in_text`) |
| LLM 이 하는 일 | 매칭 안 된 영상을 보고 새 게임·별칭 후보 제안 (사전 자동 수정 안 함) |
| 출력 | `videos` → DB `videos` (coins·favorites 포함, 길이 모르면 `is_short = null`) |
| 막는 것 | 별칭 사전은 사람이 승인한 후보만 반영 |

### 3-6. 3 점수화 (scorer, 코드만)

```mermaid
flowchart LR
    V[("videos<br/>game_ids")]:::store
    K[("keywords<br/>핫키워드 순위")]:::store
    E[("aside_events<br/>공식 활동")]:::store
    V --> D["수요 demand<br/>= (핫키워드 순위 가중 ÷ 최댓값<br/>+ 조회수 합 ÷ 최댓값) ÷ 2<br/>순위 가중: 1위 1.0 … 30위 1/30"]:::code
    K --> D
    V --> O["아웃라이어 outlier<br/>= min(게임 반응률 중앙값 ÷ 풀 중앙값 ÷ 3, 1)<br/>반응률 = 코인·즐겨찾기·좋아요·공유 ÷ 조회수"]:::code
    V --> F["신선도 freshness<br/>= 중앙값 0.5^(경과 시간 ÷ 72h)<br/>+ 공식 활동 가산 0.2, 최대 1"]:::code
    E --> F
    V --> C["경쟁도 competition<br/>= 풀 안 같은 게임 영상 수 ÷ 최댓값"]:::code
    D --> S["Score_bili<br/>= 1.0·수요 + 1.0·아웃라이어 + 1.0·신선도 − 1.0·경쟁도"]:::code
    O --> S
    F --> S
    C --> S
    S --> OUT[("game_scores → DB topic_scores<br/>仅供排序参考，非播放量预测")]:::store

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
```

- LLM 을 쓰지 않습니다. 같은 데이터면 항상 같은 점수가 나옵니다.
- 가중치는 기획안대로 처음엔 모두 1.0 ([metrics.py](../bilibili/bili_agent/tools/metrics.py) `WEIGHTS`). 바꾸는 것은 6 성과 기록의 보정안을 사람이 승인했을 때만입니다.

### 3-7. 4 분석 (analyst)

```mermaid
flowchart TB
    subgraph TOOLS["도구 9개 (코드 계산)"]
        t1["get_game_scores<br/>게임별 Score_bili·구성 요소"]:::code
        t2["get_hot_keyword_signals<br/>게임 관련 핫키워드<br/>선행 신호(풀 안 영상 ≤1개)"]:::code
        t3["get_event_signals<br/>공식 활동(mission_id) 참여 영상<br/>Aside 활동 목록"]:::code
        t4["get_engagement_ranking<br/>반응률 상위 영상<br/>중앙값 대비 배수"]:::code
        t5["get_duration_type_distribution<br/>길이 구간·유형별 개수<br/>조회수 중앙값"]:::code
        t6["get_title_benchmark<br/>인기 제목 글자 수<br/>【】《》·숫자 비율"]:::code
        t7["diagnose_title<br/>사용자 제목 ↔ 벤치마크"]:::code
        t8["get_top_titles<br/>상위 영상의 실제 제목·태그"]:::code
        t9["lookup_evidence<br/>키워드·mission_id 로<br/>원본 영상 근거 조회"]:::code
        t1 ~~~ t4 ~~~ t7
        t2 ~~~ t5 ~~~ t8
        t3 ~~~ t6 ~~~ t9
    end
    TOOLS --> A(["analyst (Claude) · w4_analyst.md<br/>숫자는 도구 값을 그대로 옮기고 해석만 함"]):::llm
    A --> O1["opportunities<br/>추천 게임 + 이유"]:::code
    A --> O2["events<br/>공식 활동 참여 제안"]:::code
    A --> O3["duration_advice<br/>길이 추천"]:::code
    A --> O4["title_review<br/>title_check 일 때"]:::code
    A --> O5["overseas_trend_cards<br/>한국어 소재 카드 → YouTube"]:::code
    A --> O6["claims<br/>주장마다 근거 영상"]:::code
    O1 ~~~ O4
    O2 ~~~ O5
    O3 ~~~ O6
    G{{"길이를 아는 영상이 10개 미만이면<br/>길이 조언 보류"}}:::guard -.-> O3
    O4 --> DB[("DB analyses<br/>summary · claims")]:::store
    O5 --> DB
    O6 --> DB

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 3-8. 5 기획안 (planner: 작성 + 검토)

```mermaid
flowchart TB
    CTX["get_plan_context (코드)<br/>점수 · 공식 활동 · 길이 분포 · 제목 벤치마크<br/>상위 제목 · 분석 결과 · 이전 검증 실패 내용"]:::code
    CTX --> WR(["plan_writer (Claude)<br/>w5_plan_writer.md<br/>근거는 lookup_evidence 로 확인"]):::llm
    WR --> DR["초안 plan-v1 (간체 중국어)<br/>plan_id = bili-run_id-game_id-vN<br/>점수·데이터 출처는 코드가 채움"]:::code
    DR --> RC{{"check_plan (코드 규칙 검사)<br/>· 내용 유형 4종 중 하나<br/>· 훅 3종 각 1개 + 선택 훅<br/>· 제목 3개 서로 다름<br/>· 구간 순서 开场→问题→正文→CTA→结尾, 시간 빈틈·겹침 없음<br/>· 썸네일 비율 16:9 / 4:3 / 9:16<br/>· 저작권 필수 항목 · 仅供排序参考<br/>· 조회수 예측 표현 금지"}}:::guard
    RC --> RV(["plan_reviewer (Claude)<br/>w5_plan_reviewer.md<br/>get_plan · run_rule_checks · lookup_evidence"]):::llm
    RV --> J{"규칙 통과<br/>AND 검토 통과?"}:::code
    J -->|"예"| OK["status = validated"]:::code
    J -->|"아니오 · 1회차"| RE["previous_validation_failed 를 넘겨<br/>다시 작성 (MAX_REVISIONS = 1)"]:::code
    RE --> WR
    J -->|"아니오 · 수정 후에도"| NR{"status = needs_review<br/>사람 검토"}:::human
    OK --> OUT[("DB plans<br/>outputs/*_plan.json · *_plan.md")]:::store
    NR --> OUT

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 3-9. 6 성과 기록 (performance)

```mermaid
flowchart TB
    UP{"사람이 빌리빌리에 업로드"}:::human --> REG["main.py register-upload<br/>--bvid BV… --report outputs/report_x.json<br/>bvid ↔ plan_id 연결"]:::code
    REG --> U[("uploads")]:::store
    CK1[("data/aside/*performance*.csv<br/>Aside 로 수집한 시점별 성과")]:::store --> CP
    CK2[("data/performance/*.csv<br/>수동 기록")]:::store --> CP
    CP["_checkpoints<br/>조회·좋아요·코인·즐겨찾기·댓글, 반응률"]:::code --> PF[("performance")]:::store
    U --> AG
    PF --> AG
    AG(["performance (Claude)<br/>list_uploads · get_checkpoints · propose_weights<br/>영상별 해석 · 다음 행동 제안"]):::llm
    AG --> PW{{"propose_weights<br/>성과 있는 영상 ≥ 8개일 때만<br/>점수 구성 요소 ↔ log1p(조회수) 상관"}}:::guard
    PW -->|"8개 미만"| NS["표본 부족 → 보정안 없음"]:::code
    PW -->|"8개 이상"| PR[("weights.proposed.json<br/>제안안만 저장")]:::store
    PR --> H{"사람이 확인 후 적용"}:::human
    H --> W[("점수 가중치<br/>score_weights")]:::store

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 3-10. 빌리빌리 가드레일 모음

| 상황 | 막는 곳 (코드) |
|---|---|
| 앞 단계 없이 뒤 단계 호출 (예: 정규화 전에 분석) | `supervisor._delegate` 의 `requires` 체인 |
| 수집 영상 0개인데 계속 진행 | `_delegate` 의 no-data 관문 |
| 같은 에이전트 중복 실행 | `_delegate` |
| 오래된 데이터(랭킹 2025-04 고정 등) 사용 | `load_aside` 신선도(48시간), `normalize_pool` 30일 필터 + API 보충 |
| 보고서·기획안의 조회수 예측 표현 (중·한) | `plan_rules.PREDICTION_PATTERNS` → `check_report_submission`, `check_plan` |
| LLM 이 점수를 잘못 옮김 | `build_report`·`assemble_plan` 이 코드 계산값을 덮어씀 |
| 검증 실패한 기획안을 통과로 표시 | 규칙 검사 AND 검토 둘 다 통과해야 `validated`, 수정 1회 상한 |
| 가중치 자동 변경 | 보정안은 파일로만, 적용은 사람 |
| 무한 루프·비용 폭주 | 슈퍼바이저 최대 12단계, 에이전트 최대 6단계, 호출별 토큰·비용 기록(`usage`) |
| 봇 차단 우회 | 하지 않음: 차단된 API 는 Aside 수집·사람 저장 스냅샷으로 대체 |

---

## 4. YouTube 분기

Claude Code 의 오케스트레이터 스킬(`/youtube-pipeline`)이 코드 단계와 서브에이전트 6개를 순서대로 부르고, 중요한 지점마다 멈춰 사람 승인을 받습니다. 상세 설계: [youtube/docs/architecture.md](../youtube/docs/architecture.md), 단계·멈춤 지점: [SKILL.md](../youtube/.claude/skills/youtube-pipeline/SKILL.md).

### 4-1. 전체 흐름

```mermaid
flowchart TB
    U["크리에이터 · Claude Code<br/>/youtube-pipeline"]:::human --> O(["오케스트레이터 스킬<br/>SKILL.md · 단계 순서와 멈춤 지점"]):::llm
    O --> Q{"API 쿼터 사용 승인<br/>(search 1회 = 100 units)"}:::human
    Q --> C1["1 수집 collect<br/>인기 차트 · 키워드 검색 · 채널 통계"]:::code
    C1 --> C2["2 정규화 normalize<br/>게임 이름 통일 · 쇼츠 여부 · 채널 평균 대비 배수"]:::code
    C2 --> HA{"별칭 후보 검토"}:::human
    HA --> C3["3 점수화 score<br/>Score_yt (코드만)"]:::code
    C3 --> C4["4 분석 analyze<br/>근거 팩 04_evidence"]:::code
    C4 --> A1(["trend-analyst<br/>주제·각도 선택 → 04_analysis"]):::llm
    A1 --> HT{"주제 선택 확인"}:::human
    HT --> A2(["plan-writer<br/>→ 05_plan.json / .md"]):::llm
    A2 --> V1{{"validate (규칙 검사)"}}:::guard
    V1 -->|"오류"| A2
    V1 -->|"통과"| A3(["plan-validator<br/>독립 검토 → review"]):::llm
    A3 -->|"수정 필요 · 첫 제출 포함 3회까지"| A2
    A3 -->|"수정 횟수 초과"| HX{"사람이 판단"}:::human
    A3 -->|"통과"| HP{"기획안 승인"}:::human
    HP --> TH["6b 썸네일 thumbnail"]:::code
    HP --> A4(["7 script-writer<br/>대본 · 자막 · edit.json"]):::llm
    A4 --> R1["video 프리뷰 렌더 720p"]:::code
    R1 --> A5(["qa-reviewer<br/>측정 + 화면 검토"]):::llm
    A5 --> HV{"프리뷰 승인"}:::human
    HV --> R2["최종 렌더"]:::code
    R2 --> HU{"업로드 · 공개 여부는 사람"}:::human
    HU --> P1["8 성과 기록 perf<br/>register · fetch · summary · calibrate"]:::code
    P1 --> A6(["performance-analyst<br/>요약 · 가중치 보정안"]):::llm
    A6 --> HW{"가중치 적용 승인<br/>perf apply"}:::human
    HW -.->|"weights 반영"| C3
    DBP{"DB push 전 승인"}:::human
    C1 -.-> DBP
    A2 -.-> DBP
    TH -.-> DBP
    DBP -->|"db export / db push"| DB[("팀 공용 DB · Supabase")]:::store

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 4-2. 단계표

| # | 단계 | 맡는 쪽 | 명령 / 에이전트 | 산출물 (`runs/<id>/`) | DB 테이블 | 사람 승인 |
|---|---|---|---|---|---|---|
| 1 | 수집 | 코드 | `data --source api` (`collect`) | `01_raw.json` | raw_snapshots | API 쿼터 사용 전 |
| 2 | 정규화 | 코드 | `normalize` | `02_normalized.json` | videos, channels | 별칭 후보 검토 |
| 3 | 점수화 | 코드 | `score` | `03_scores.json` | topic_scores | — |
| 4 | 분석 | 코드 + trend-analyst | `analyze` → 에이전트 | `04_evidence.json`, `04_analysis.json` | analyses | 주제 선택 확인 |
| 5 | 기획안 | plan-writer | 에이전트 | `05_plan.json`, `05_plan.md` | plans | — |
| 6 | 검증 | 코드 + plan-validator | `validate` → 에이전트 → `review` | `06_validation.json` | plans.status | **기획안 승인** |
| 6b | 썸네일 | 코드 + 이미지 생성 API | `thumbnail` | `05_thumbnails/thumb_vN.png/.json` | thumbnails | 비용 승인, 썸네일 선택 |
| — | DB 저장 | 코드 | `db export`, `db push` | `db/*.json`, Supabase | 전체 | push 전 |
| 7 | 영상 생성 | script-writer + 코드 + qa-reviewer | `video timing/render`, `qa` | `07_video/` | — | edit.json·프리뷰 승인, **공개 여부** |
| 8 | 성과 기록 | 코드 + performance-analyst | `perf register/fetch/summary/calibrate` | `performance/` | uploads, performance, score_weights | 가중치 적용 |

### 4-3. 5 기획안 · 6 검증

```mermaid
flowchart TB
    AN[("04_analysis.json<br/>04_evidence.json")]:::store --> PW(["plan-writer<br/>.claude/agents/plan-writer.md"]):::llm
    PW --> PL[("05_plan.json<br/>훅 3안 · 구간별 대본 · 제목 3개<br/>썸네일 브리프(image_prompt) · 저작권 체크리스트")]:::store
    PL --> VA{{"validate · plan_rules.check_plan<br/>근거 경로 존재 · 점수 = 코드 값<br/>예측 표현 금지 · 저작권 항목"}}:::guard
    VA -->|"errors 있음"| PW
    VA -->|"errors 없음"| PV(["plan-validator<br/>독립 검토"]):::llm
    PV --> RV[("06_validation.json<br/>next")]:::store
    RV -->|"수정 필요"| PW
    RV -->|"통과"| H{"05_plan.md 보여 주고<br/>사람 승인"}:::human
    RV -->|"3회 초과"| HX{"사람이 판단"}:::human

    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 4-4. 6b 썸네일

```mermaid
flowchart TB
    S{{"기획안 status = validated 인가"}}:::guard --> T["python -m yt_pipeline thumbnail<br/>thumbnail.py"]:::code
    T --> PR{"config/pipeline.json<br/>thumbnail.provider"}:::code
    PR -->|"none (기본)"| P0[("프롬프트만 저장")]:::store
    PR -->|"openai · 비용 승인 후"| G["OpenAI Images API<br/>image_prompt 로 배경 생성 (과금)"]:::code
    PR -->|"--background 경로"| BG["직접 찍은 게임 화면을 배경으로"]:::code
    G --> OV["FFmpeg drawtext<br/>썸네일 문구 합성"]:::code
    BG --> OV
    OV --> F[("05_thumbnails/thumb_vN.png + .json<br/>덮어쓰지 않고 버전 증가")]:::store
    F --> H{"사람이 확인·선택<br/>문구 잘림·로고·실존 인물 있으면 다시"}:::human

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 4-5. 7 영상 생성

```mermaid
flowchart TB
    PL[("승인된 05_plan.json")]:::store --> SW(["script-writer<br/>대본 · 자막 · edit.draft.json"]):::llm
    VO{"내레이션: 사람 녹음 또는 TTS<br/>(TTS 는 과금, 먼저 승인)"}:::human --> TM
    CL{"클립: shot_list 대로 사람이 녹화<br/>clips/shot.mp4"}:::human --> TM
    SW --> TM["video timing"]:::code
    TM --> ED{"edit.json 확정<br/>in/out · crop · BGM → 사람 승인"}:::human
    ED --> CK{{"video check<br/>CREDITS.txt 에 없는 BGM 금지"}}:::guard
    CK --> PV["video render (720p 프리뷰)"]:::code
    PV --> QA["qa (측정)<br/>edit.json 일치 확인"]:::code
    QA --> QR(["qa-reviewer<br/>화면 검토"]):::llm
    QR --> HP{"사람이 프리뷰 보고 승인"}:::human
    HP --> FG{{"측정 PASS + 화면 검토 PASS 없으면<br/>최종 렌더 금지"}}:::guard
    FG --> FR["video render --final"]:::code
    FR --> QR2(["qa-reviewer 다시"]):::llm
    QR2 --> UP{"업로드 · 공개 여부는 사람<br/>(저장소는 게시하지 않음)"}:::human

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 4-6. 8 성과 기록

```mermaid
flowchart TB
    R["perf register<br/>영상 ↔ 기획안 연결"]:::code --> F["perf fetch / perf manual<br/>24시간 · 72시간 · 7일 조회수"]:::code
    F --> S["perf summary"]:::code
    S --> PA(["performance-analyst<br/>요약 · 해석"]):::llm
    S --> CA{{"perf calibrate<br/>샘플이 아닌 영상 ≥ 8개일 때만<br/>항목 점수 ↔ log10(72시간 조회수) 상관<br/>가중치 0.2~2.0 으로 자름"}}:::guard
    CA --> PR[("config/weights.proposed.json")]:::store
    PR --> H{"팀 확인 후 perf apply"}:::human
    H --> W[("config/pipeline.json<br/>score.weights")]:::store

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef human fill:#ffe5e5,stroke:#d33,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
    classDef guard fill:#f1e8ff,stroke:#7b3fd8,color:#111
```

### 4-7. 점수 Score_yt

```mermaid
flowchart LR
    D["수요<br/>시간당 조회수 합 ÷ 최댓값 과<br/>차트·검색 순위 가중(1위 1.0 … 50위 0.02) ÷ 최댓값 의 평균"]:::code --> S
    O["아웃라이어<br/>영상 조회수 ÷ 채널 평균 조회수 의 중앙값 ÷ 5<br/>(5배 이상이면 1)"]:::code --> S
    F["신선도<br/>중앙값 0.5^(게시 후 경과 시간 ÷ 72h)"]:::code --> S
    C["경쟁도<br/>같은 게임 영상 수 ÷ 최댓값"]:::code --> S
    S["Score_yt = w1·수요 + w2·아웃라이어 + w3·신선도 − w4·경쟁도<br/>가중치 초기값 1.0 · 범위 −1~3 · 정렬 참고용"]:::code

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
```

자세한 기준: [youtube/docs/scoring.md](../youtube/docs/scoring.md). 빌리빌리 점수(3-6)와 공식 모양은 같지만 데이터가 달라 **두 플랫폼 점수는 서로 비교하지 않습니다**.

### 4-8. YouTube 가드레일 모음

| 상황 | 막는 곳 (코드) |
|---|---|
| 근거 경로가 없는 주장, 없는 근거 경로 | `plan_rules.check_analysis`, `check_plan` |
| 점수를 코드 값과 다르게 옮김 | `check_plan` 의 score_reference 검사 |
| 조회수·반응 예측 표현 | `plan_rules.PREDICTION_PATTERNS` |
| 저작권 체크리스트에 게임 화면·음악·타인 소재 항목 누락 | `check_plan` |
| 검증 통과 전 썸네일 생성·렌더 | `thumbnail.run`, `video.render` |
| 프리뷰 측정 PASS 와 화면 검토 PASS 없이 최종 렌더 | `video.render` |
| 렌더 뒤 edit.json 이 바뀐 상태로 검수 | `qa` 의 edit.json 일치 항목 |
| CREDITS.txt 에 없는 BGM | `video.check_edit` |
| 결과물 덮어쓰기 | `_next_version` |
| 샘플 데이터로 가중치 보정 | `performance.calibrate` |
| 위험한 명령 자동 실행 | `.claude/settings.json`: API 수집·썸네일 생성·렌더·DB push·가중치 적용은 실행 전에 묻고, `.env` 읽기는 금지 |

---

## 5. TikTok 분기 (예정)

담당 팀원이 합류했고 구조는 조사 후 확정합니다. 세 플랫폼이 같은 계약을 쓰도록, 붙일 자리는 이미 정해 두었습니다.

```mermaid
flowchart LR
    TS["팀 총괄 슈퍼바이저"]:::code -.->|"TikTokTask (예정)"| TT["TikTok 서브 슈퍼바이저<br/>(조사 후 확정)"]:::code
    TT -.->|"TikTokReport · plan-v1"| TS
    TT -.->|"platform = tiktok"| DB[("팀 공용 DB<br/>platform 체크 제약에 tiktok 이미 포함")]:::store

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
```

| 붙일 때 할 일 | 위치 |
|---|---|
| `PLATFORMS` 에 `tiktok` 추가, `INTENT_MAP` 에 TikTok 열 추가 | [team_supervisor/contracts.py](../team_supervisor/contracts.py) |
| 호출부 `run_tiktok` 또는 `load_tiktok` 추가 | [team_supervisor/platforms.py](../team_supervisor/platforms.py) |
| 기획안 라벨(내용 유형·훅·구간)을 공통 ID 표에 추가 | [team_supervisor/plan_adapter.py](../team_supervisor/plan_adapter.py) |
| 보고서는 `opportunities`, `plan`(plan-v1), `plan_validation`, `data_sources`, `warnings` 를 같은 이름으로 | 2-3 데이터 계약 |
| 같은 DB 테이블에 `platform = 'tiktok'` 으로 저장 | [youtube/db/schema.sql](../youtube/db/schema.sql) |

---

## 6. 팀 공용 DB

기획안 13장 「데이터베이스 설계」. 스키마 원본은 [youtube/db/schema.sql](../youtube/db/schema.sql) (Supabase · PostgreSQL)이고, 세 플랫폼이 같은 테이블에 `platform` 열로 나눠 저장합니다. 실선은 외래 키, 점선은 `run_id`·`platform`·`game_id` 로 이어지는 논리적 연결입니다.

```mermaid
erDiagram
    raw_snapshots {
        text id PK "run_id:platform"
        text run_id
        text platform "youtube bilibili tiktok"
        text source "api file aside sample"
        boolean is_sample
        timestamptz collected_at
        jsonb payload
    }
    games {
        text game_id PK
        text name_ko
        text name_en
        text name_zh
    }
    game_aliases {
        text alias PK
        text game_id PK, FK
        text platform
    }
    channels {
        text channel_id PK
        text platform PK
        text title
        bigint subscribers
        double avg_views
    }
    videos {
        text video_id PK
        text platform PK
        text run_id PK
        text_array game_ids
        text channel_id
        text title
        bigint views
        bigint likes
        bigint comments
        bigint coins "bilibili"
        bigint favorites "bilibili"
        integer duration_sec
        boolean is_short
        timestamptz published_at
        double outlier_multiple
        double views_per_hour
    }
    topic_scores {
        text run_id PK
        text platform PK
        text game_id PK
        double demand
        double outlier
        double freshness
        double competition
        double score "sorting only"
        integer videos_in_pool
    }
    score_weights {
        bigint id PK
        text platform
        double w_demand
        double w_outlier
        double w_freshness
        double w_competition
        integer samples
        text approved_by "human"
        timestamptz applied_at
    }
    analyses {
        text analysis_id PK
        text run_id
        text platform
        text game_id
        text summary
        jsonb claims "evidence_refs"
    }
    plans {
        text plan_id PK
        uuid user_id "RLS own plans"
        text run_id
        text platform
        text game_id
        jsonb plan "plan-v1"
        text status "draft validated needs_review"
    }
    thumbnails {
        text file_path PK
        text plan_id FK
        text ratio
        text source
        text prompt
        text overlay_text
    }
    uploads {
        text video_id PK
        text plan_id FK
        text platform
        timestamptz published_at
    }
    performance {
        text video_id PK, FK
        timestamptz at PK
        text source
        bigint views
        bigint likes
        bigint comments
    }

    games ||--o{ game_aliases : "alias"
    plans ||--o{ thumbnails : "thumbnail"
    plans ||--o{ uploads : "upload"
    uploads ||--o{ performance : "checkpoint"
    raw_snapshots ||..o{ videos : "run_id"
    channels ||..o{ videos : "channel_id"
    games ||..o{ topic_scores : "game_id"
    videos }o..o{ topic_scores : "run_id + game_ids"
    topic_scores ||..o{ analyses : "run_id"
    analyses ||..o{ plans : "run_id"
```

**누가 어떤 테이블에 쓰나**

| 테이블 | 빌리빌리 ([team_db.py](../bilibili/bili_agent/tools/team_db.py)) | YouTube ([db.py](../youtube/yt_pipeline/db.py)) | 비고 |
|---|---|---|---|
| raw_snapshots | ✅ 1 수집 (source: aside / live / file) | ✅ 1 수집 | 원본 그대로 jsonb |
| games, game_aliases | 읽기 (별칭 사전 보충) | — | 사람이 관리 |
| channels | — | ✅ 2 정규화 | 아웃라이어 배수 기준선 |
| videos | ✅ 2 정규화 (coins·favorites 포함) | ✅ 2 정규화 | 뷰 `v_reaction_rate` 는 빌리빌리 반응률 |
| topic_scores | ✅ 3 점수화 | ✅ 3 점수화 | 정렬 참고용 |
| analyses | ✅ 4 분석 | ✅ 4 분석 | claims 에 근거 |
| plans | ✅ 5 기획안 | ✅ 5·6 기획안·검증 | RLS: 로그인한 본인 기획안만 |
| thumbnails | — | ✅ 6b 썸네일 | |
| uploads, performance | ✅ 6 성과 기록 | ✅ 8 성과 기록 | |
| score_weights | 사람 승인 후 | 사람 승인 후 | 보정안은 파일로만 만들고 자동 적용 안 함 |

---

## 7. 플랫폼 사이 연결: 빌리빌리 → YouTube

구조는 계층형이지만 수평 연결이 한 곳 있습니다. 빌리빌리에서 반응이 좋은 소재를 한국어 카드로 옮겨 YouTube 기획에 참고로 넘깁니다(총괄을 거쳐 전달).

```mermaid
flowchart TB
    T8["get_top_titles<br/>반응률 상위 영상의 실제 제목·태그·배수 (코드)"]:::code --> AN(["빌리빌리 4 분석 analyst<br/>소재를 한국어로 정리"]):::llm
    AN --> CARD[("overseas_trend_cards<br/>source_bvid · title_zh · title_ko · why_ko")]:::store
    CARD --> BR["BiliReport"]:::code
    BR --> TS["팀 총괄 _cross_platform"]:::code
    TS --> TR[("TeamReport.cross_platform<br/>.bilibili_to_youtube")]:::store
    TR -.->|"참고용 · 그대로 복제 금지"| YW(["YouTube plan-writer / 크리에이터"]):::llm

    classDef code fill:#e8f1ff,stroke:#3b6fd8,color:#111
    classDef llm fill:#fff1e0,stroke:#e07b00,color:#111
    classDef store fill:#eaf6ea,stroke:#2e8b57,color:#111
```
