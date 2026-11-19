# 아키텍처

```mermaid
flowchart TD
    U[크리에이터 / Claude Code] -->|/youtube-pipeline| O[오케스트레이터 스킬]
    O --> C1[1 collect<br/>YouTube Data API · file · sample]
    C1 --> C2[2 normalize<br/>길이·쇼츠·별칭 통일·배수]
    C2 --> C3[3 score<br/>Score_yt]
    C3 --> C4[4a analyze<br/>근거 팩 04_evidence]
    C4 --> A1[[trend-analyst]]
    A1 -->|04_analysis| A2[[plan-writer]]
    A2 -->|05_plan| V1[6 validate<br/>코드 규칙 검사]
    V1 -->|오류| A2
    V1 -->|통과| A3[[plan-validator<br/>독립 의미 검토]]
    A3 -->|수정 필요 · 최대 2회| A2
    A3 -->|validated| H1{사람 승인}
    H1 --> A4[[script-writer]]
    A4 -->|script.json| T[video timing<br/>자막·voice.wav·edit.draft]
    T --> H2{edit.json 승인}
    H2 --> R1[render 720p 프리뷰]
    R1 --> Q[qa 측정<br/>ffprobe · 프레임 · silence · black]
    Q --> A5[[qa-reviewer<br/>프레임 시트 판정]]
    A5 -->|FAIL: edit.json 값 하나 수정 → _v2| R1
    A5 -->|PASS| H3{프리뷰 승인}
    H3 --> R2[render final → qa]
    R2 --> H4{공개 여부 · 업로드는 사람}
    H4 --> P1[8 perf register / fetch]
    P1 --> A6[[performance-analyst]]
    A6 -->|weights.proposed.json| H5{가중치 적용 승인}
    H5 -->|perf apply| C3
```

## 계약 (팀 총괄 슈퍼바이저 연결)

| 방향 | 형태 | 비고 |
|---|---|---|
| 총괄 → YouTube | `YouTubeTask(intent, topic, source)` | intent: trend_scan / topic_deep_dive / make_video / performance_review |
| YouTube → 총괄 | `YouTubeReport` (`runs/<id>/report.json`) | opportunities, duration_advice, alias_candidates, **plan(plan-v1)**, plan_validation, video, performance, data_sources, agent_trace, warnings |

빌리빌리 `BiliReport` 와 같은 모양이다. 기획안 필드 구조도 plan-v1 로 같고, 텍스트 필드 이름만 `_zh` 대신 접미사 없는 한국어(`line`, `points`, `text`, `style`)다.

## 코드가 막는 것 (가드레일)

| 상황 | 막는 곳 |
|---|---|
| 근거 경로가 없는 주장, 존재하지 않는 근거 경로 | `plan_rules.check_analysis / check_plan` |
| 점수를 코드 값과 다르게 옮김 | `check_plan` (score_reference.topic_score) |
| 조회수·반응 예측 표현 | `plan_rules.PREDICTION_PATTERNS` |
| 저작권 체크리스트 누락(게임 화면·음악·타인 소재) | `check_plan` |
| 검증 통과 전 렌더 | `video.render` (plan status) |
| 프리뷰 측정 PASS + 화면 검토 PASS 없이 최종 렌더 | `video.render` (같은 edit_hash 의 qa.json) |
| 렌더 후 edit.json 이 바뀌었는데 검수 | `qa` (edit.json 일치 항목) |
| CREDITS.txt 에 없는 BGM | `video.check_edit` |
| 결과물 덮어쓰기 | `_next_version` (_v1, _v2 …) |
| 샘플 데이터로 가중치 보정 | `performance.calibrate` (is_sample_data 제외) |
