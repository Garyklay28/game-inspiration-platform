"""에이전트 3 · 점수화 (기획안 12장 '3 점수화' — 계산 코드만 사용, LLM 없음)

Score_bili = w1·수요 + w2·아웃라이어 배수 + w3·신선도 − w4·경쟁도 (각 0~1, 초기 동일 가중치, 10장)
Aside 공식 활동 목록에 게임이 등장하면 신선도에 이벤트 가산(metrics.EVENT_BONUS)을 준다.
DB(13장): topic_scores
"""
from typing import Dict

from ...tools import metrics
from ...workspace import Workspace
from ..base import WorkerSpec


def run(ws: Workspace, llm=None, instruction: str = "") -> Dict:
    scores = metrics.score_games(ws.videos, ws.keywords, ws.alias)
    # Aside 공식 활동·화제 이름에 게임이 나오면 이벤트 가산 (mission_id 가 없는 Aside 데이터 보완)
    event_games = {g["game_id"] for e in ws.aside_events for g in ws.alias.find_in_text(e["name"])}
    for s in scores:
        if s["game_id"] in event_games and s["components"]["freshness"] < 1.0:
            bonus = min(metrics.EVENT_BONUS, 1.0 - s["components"]["freshness"])
            s["components"]["freshness"] = round(s["components"]["freshness"] + bonus, 4)
            s["score"] = round(s["score"] + metrics.WEIGHTS["freshness"] * bonus, 3)
            s["aside_event_bonus"] = True
    scores.sort(key=lambda x: -x["score"])
    ws.cache["game_scores"] = scores
    ws.findings["scorer"] = {"summary_ko": "게임 %d개 점수 계산 (상위: %s)" % (
        len(scores), ", ".join("%s %.2f" % (s["game_ko"], s["score"]) for s in scores[:3]))}
    return {"games": len(scores), "top": scores[:5],
            "formula": "Score_bili = 수요 + 아웃라이어 + 신선도 − 경쟁도 (각 0~1, 정렬 참고용·조회수 예측 아님)"}


SPEC = WorkerSpec(name="scorer", stage="3 점수화", db_tables=["topic_scores"], uses_llm=False,
                  requires="normalizer", run_code=run)
