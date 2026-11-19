@AGENTS.md

## 빠른 시작

- 전체 파이프라인: `/youtube-pipeline` 스킬 (8단계, 단계마다 멈춤 지점 있음)
- 편집만: `/video-edit` 스킬
- 진행 상황: `python -m yt_pipeline status`
- 테스트: `python -m pytest -q`

## 서브에이전트

| 에이전트 | 단계 | 읽는 파일 | 쓰는 파일 |
|---|---|---|---|
| trend-analyst | 4 분석 | 03_scores, 04_evidence | 04_analysis.json |
| plan-writer | 5 기획안 | 04_analysis, 04_evidence, 06_validation(수정 시) | 05_plan.json |
| plan-validator | 6 검증 | 05_plan, 06_validation, 04_evidence | review.json → `review --file` |
| script-writer | 7 대본 | 05_plan | 07_video/script.json |
| qa-reviewer | 7 검수 | *.qa.json, 프레임 시트 | visual.json → `qa --visual` |
| performance-analyst | 8 성과 | performance/summary.json, weights.proposed.json | 보고만 (가중치 적용은 사람) |
