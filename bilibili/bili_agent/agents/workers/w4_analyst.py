"""에이전트 4 · 분석 (기획안 12장 '4 분석', 08장 빌리빌리 모드 기능 전부)

08장 기능 → 도구
  이벤트 레이더·공식 이벤트 태그   get_event_signals (mission_id + Aside 공식 활동)
  핫키워드 선행 신호               get_hot_keyword_signals
  반응률 정렬                       get_engagement_ranking
  영상 길이 제안·유형 분포          get_duration_type_distribution
  제목 진단                         get_title_benchmark, diagnose_title
  YouTube 모드 연결(중→한 소재)     get_top_titles
  근거 확인                         lookup_evidence
LLM: 위 숫자를 해석해 기회·이벤트·길이 제안·제목 진단·해외 트렌드 카드를 쓰고, 주장마다 근거를 단다.
DB(13장): analyses
"""
from typing import Any, Dict, Optional

from ...tools import metrics
from ...workspace import Workspace
from ..base import GAME_ID_PROP, STR_LIST, WorkerSpec, submit, tool


def _labels(ws: Workspace, v: Dict):
    return [g["ko"] for g in metrics.games_of(v, ws.alias)]


def h_get_game_scores(ws: Workspace, top: int = 8) -> Dict:
    return {"note": "3 점수화 에이전트가 계산한 값. 정렬 참고용", "games": (ws.cache.get("game_scores") or [])[:top]}


def h_get_hot_keyword_signals(ws: Workspace) -> Dict:
    sig = metrics.hot_keyword_signals(ws.keywords, ws.videos, ws.alias)
    ws.cache["hot_keyword_signals"] = sig
    return {"total_keywords": len(ws.keywords), "game_related": len(sig), "signals": sig}


def h_get_event_signals(ws: Workspace) -> Dict:
    ev = metrics.event_signals(ws.videos, ws.alias)
    ws.cache["event_signals"] = ev
    aside = [dict(e, games_ko=[g["ko"] for g in ws.alias.find_in_text(e["name"])]) for e in ws.aside_events[:15]]
    share = sum(r["videos"] for r in ev) / max(len(ws.videos), 1)
    return {"mission_video_share": round(share, 3), "mission_events": ev[:10], "aside_official_topics": aside}


def h_get_engagement_ranking(ws: Workspace, game_id: Optional[str] = None, top: int = 10) -> Dict:
    return metrics.rank_by_engagement(ws.videos_for(game_id), top=top)


def h_get_duration_type_distribution(ws: Workspace, game_id: Optional[str] = None) -> Dict:
    dist = metrics.duration_and_type_distribution(ws.videos_for(game_id))
    ws.cache["distribution:%s" % (game_id or "all")] = dist
    return dist


def h_get_title_benchmark(ws: Workspace, game_id: Optional[str] = None) -> Dict:
    bench = metrics.title_benchmark(ws.videos_for(game_id))
    ws.cache["title_benchmark"] = bench
    return bench


def h_diagnose_title(ws: Workspace, title: str) -> Dict:
    bench = ws.cache.get("title_benchmark") or metrics.title_benchmark(ws.videos)
    diag = metrics.diagnose_title(title, bench)
    ws.cache["title_diagnosis"] = diag
    return diag


def h_get_top_titles(ws: Workspace, n: int = 10, game_id: Optional[str] = None) -> Dict:
    pool = ws.videos_for(game_id)
    ranked = metrics.rank_by_engagement(pool, top=n)
    by_bvid = {v["bvid"]: v for v in pool}
    rows = []
    for r in ranked["top"]:
        v = by_bvid[r["bvid"]]
        rows.append({"bvid": r["bvid"], "title": r["title"], "view": r["view"],
                     "engagement_multiple": round(r["engagement_multiple"], 2), "type": metrics.classify_type(r["title"]),
                     "games_ko": _labels(ws, v), "tags": (v.get("tags") or [])[:5],
                     "in_official_activity": bool(v.get("mission_id"))})
    return {"pool_size": len(pool), "titles": rows}


def h_lookup_evidence(ws: Workspace, keyword: Optional[str] = None, mission_id: Optional[int] = None) -> Dict:
    """원본 데이터에서 근거를 직접 조회 (분석·기획안·검토 에이전트가 같은 데이터를 본다)."""
    if not keyword and mission_id is None:
        raise ValueError("keyword 또는 mission_id 중 하나는 필요합니다")
    pool = ws.videos_for(None)  # 정규화 전이면 수집 원본
    pool_med = metrics.rank_by_engagement(pool, top=0)["median_engagement_rate"] or 1e-9
    out: Dict[str, Any] = {"pool_size": len(pool), "pool_median_engagement_rate": round(pool_med, 4),
                           "note": "multiple_vs_pool = 전체 풀 중앙값 대비, multiple_vs_game = 같은 게임 중앙값 대비"}
    if keyword:
        game_meds: Dict[str, float] = {}
        rows = []
        for v in pool:
            if keyword.lower() in (v["title"] + " " + " ".join(v.get("tags") or [])).lower():
                e = metrics.engagement(v)["engagement_rate"]
                row = {"bvid": v["bvid"], "title": v["title"], "view": v["view"], "engagement_rate": round(e, 4),
                       "multiple_vs_pool": round(e / pool_med, 2), "mission_id": v.get("mission_id"),
                       "games_ko": _labels(ws, v)}
                gids = v.get("game_ids") or []
                if gids:
                    if gids[0] not in game_meds:
                        game_meds[gids[0]] = metrics.rank_by_engagement(
                            ws.videos_for(gids[0]), top=0)["median_engagement_rate"] or 1e-9
                    row["multiple_vs_game"] = round(e / game_meds[gids[0]], 2)
                rows.append(row)
        out["videos"] = sorted(rows, key=lambda r: -r["view"])[:10]
        out["found"] = len(rows)
    if mission_id is not None:
        out["activity"] = [e for e in metrics.event_signals(pool, ws.alias) if e["mission_id"] == int(mission_id)]
    return out


LOOKUP_EVIDENCE = tool("lookup_evidence", "원본 데이터에서 근거 조회: keyword 가 제목·태그에 들어간 영상, 또는 mission_id 공식 활동.",
                       {"keyword": {"type": "string"}, "mission_id": {"type": "integer"}})

SPEC = WorkerSpec(
    name="analyst", stage="4 분석", db_tables=["analyses"], prompt_file="w4_analyst.md", requires="scorer",
    tools=[
        tool("get_game_scores", "3 점수화 결과(게임별 Score_bili·구성 요소).", {"top": {"type": "integer"}}),
        tool("get_hot_keyword_signals", "핫키워드 중 게임 관련 키워드와 선행 신호(풀 안 영상 ≤1개) 여부."),
        tool("get_event_signals", "공식 활동(mission_id) 참여 영상 묶음 + Aside 공식 활동·화제 목록."),
        tool("get_engagement_ranking", "반응률 상위 영상과 중앙값 대비 배수.", {**GAME_ID_PROP, "top": {"type": "integer"}}),
        tool("get_duration_type_distribution", "길이 구간·유형별 개수와 조회수 중앙값.", GAME_ID_PROP),
        tool("get_title_benchmark", "인기 제목 통계(글자 수 중앙값, 【】·《》·숫자 사용 비율).", GAME_ID_PROP),
        tool("diagnose_title", "제목 하나를 벤치마크와 비교.", {"title": {"type": "string"}}, ["title"]),
        tool("get_top_titles", "반응률 상위 영상의 실제 제목·태그·배수.", {"n": {"type": "integer"}, **GAME_ID_PROP}),
        LOOKUP_EVIDENCE,
    ],
    handlers={"get_game_scores": h_get_game_scores, "get_hot_keyword_signals": h_get_hot_keyword_signals,
              "get_event_signals": h_get_event_signals, "get_engagement_ranking": h_get_engagement_ranking,
              "get_duration_type_distribution": h_get_duration_type_distribution,
              "get_title_benchmark": h_get_title_benchmark, "diagnose_title": h_diagnose_title,
              "get_top_titles": h_get_top_titles, "lookup_evidence": h_lookup_evidence},
    submit_tool=submit({
        "opportunities": {"type": "array", "items": {"type": "object", "properties": {
            "game_zh": {"type": "string"}, "game_ko": {"type": "string"}, "reason_ko": {"type": "string"}},
            "required": ["game_zh", "reason_ko"]}},
        "events": {"type": "array", "items": {"type": "object", "properties": {
            "game_zh": {"type": "string"}, "kind": {"type": "string", "enum": ["official_activity", "hot_keyword", "leading_signal"]},
            "evidence": {"type": "string"}, "recommendation_ko": {"type": "string"}},
            "required": ["kind", "evidence", "recommendation_ko"]}},
        "duration_advice": {"type": "object", "properties": {"recommended_bucket": {"type": "string"},
                                                             "reason_ko": {"type": "string"}}},
        "title_review": {"type": "object", "properties": {"issues_ko": STR_LIST, "rewrite_suggestions_zh": STR_LIST}},
        "overseas_trend_cards": {"type": "array", "items": {"type": "object", "properties": {
            "source_bvid": {"type": "string"}, "title_zh": {"type": "string"}, "title_ko": {"type": "string"},
            "slang_note_ko": {"type": "string"}, "why_ko": {"type": "string"}, "adapt_tip_ko": {"type": "string"}},
            "required": ["source_bvid", "title_zh", "title_ko", "why_ko"]}},
        "claims": {"type": "array", "description": "분석 주장 목록 (DB analyses.claims). 주장마다 근거 필수", "items": {
            "type": "object", "properties": {"claim_ko": {"type": "string"}, "evidence": STR_LIST},
            "required": ["claim_ko", "evidence"]}},
    }, ["opportunities", "events", "claims"]),
)
