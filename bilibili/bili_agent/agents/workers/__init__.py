"""빌리빌리 에이전트 6개 (기획안 12장 「에이전트 6개 구조도」와 같은 구성).

| # | 에이전트 | 파일 | LLM | DB(13장) |
|---|---|---|---|---|
| 1 | collector   | w1_collector.py   | O (출처 판단) | raw_snapshots |
| 2 | normalizer  | w2_normalizer.py  | O (별칭 후보) | videos, game_aliases |
| 3 | scorer      | w3_scorer.py      | X (코드만)    | topic_scores |
| 4 | analyst     | w4_analyst.py     | O             | analyses |
| 5 | planner     | w5_planner.py     | O (작성+검토) | plans |
| 6 | performance | w6_performance.py | O             | uploads, performance, score_weights |
"""
from . import w1_collector, w2_normalizer, w3_scorer, w4_analyst, w5_planner, w6_performance

WORKERS = {m.SPEC.name: m.SPEC for m in (w1_collector, w2_normalizer, w3_scorer, w4_analyst, w5_planner, w6_performance)}
