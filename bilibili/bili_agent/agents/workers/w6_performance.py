"""에이전트 6 · 성과 기록 (기획안 12장 '6 성과 기록')

- 업로드 등록: 사람이 올린 영상(bvid)을 기획안과 연결 → data/performance/uploads.json  (main.py register-upload)
- 성과 수집: 영상 상세 API 는 봇 차단(412)이라 자동 호출하지 않는다.
  Aside 가 내보낸 *performance*.csv (data/aside/) 또는 사람이 적은 CSV (data/performance/*.csv) 를 읽는다.
- 가중치 보정안(코드): 성과가 8개 이상 쌓이면 점수 구성 요소와 log(조회수)의 상관으로 보정안을 만든다.
  적용은 사람이 승인한다(score_weights.approved_by). 이 에이전트는 제안만 한다.
LLM: 기획안 대비 성과를 해석하고 다음 행동을 제안한다.
DB(13장): uploads, performance, score_weights(보정안)
"""
import csv
import json
import math
import statistics
from datetime import datetime
from typing import Dict, List, Optional

from ... import config
from ...tools import aside_import
from ...workspace import Workspace
from ..base import STR_LIST, WorkerSpec, submit, tool

MIN_SAMPLES = 8
UPLOADS = lambda: config.PERFORMANCE_DIR / "uploads.json"  # noqa: E731


def load_uploads() -> List[Dict]:
    p = UPLOADS()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def register_upload(bvid: str, report: Dict) -> Dict:
    """BiliReport(JSON) 의 기획안과 업로드한 영상 bvid 를 연결한다."""
    plan = report.get("plan") or {}
    if not plan:
        raise ValueError("보고서에 기획안(plan)이 없습니다")
    rows = [r for r in load_uploads() if r["bvid"] != bvid]
    rows.append({"bvid": bvid, "plan_id": plan.get("plan_id"), "game_id": plan.get("game_id"),
                 "plan_status": plan.get("status"), "score": (plan.get("score_reference") or {}).get("score"),
                 "components": (plan.get("score_reference") or {}).get("components"),
                 "registered_at": datetime.now().isoformat(timespec="seconds")})
    config.PERFORMANCE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS().write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows[-1]


def _checkpoints() -> Dict[str, List[Dict]]:
    rows: List[Dict] = []
    a = aside_import.load_performance()
    if a:
        rows += [dict(r, source="aside") for r in a["rows"]]
    for p in sorted(config.PERFORMANCE_DIR.glob("*.csv")):
        data = aside_import.read_csv(p)
        rows += [{"bvid": r["bvid"], "at": r.get("collected_at", ""), "view": aside_import._num(r.get("view")),
                  "like": aside_import._num(r.get("like")), "coin": aside_import._num(r.get("coin")),
                  "favorite": aside_import._num(r.get("favorite")), "reply": aside_import._num(r.get("reply")),
                  "source": "manual"} for r in data["rows"] if r.get("bvid")]
    by: Dict[str, List[Dict]] = {}
    for r in rows:
        by.setdefault(r["bvid"], []).append(r)
    for v in by.values():
        v.sort(key=lambda r: r["at"])
    return by


def h_list_uploads(ws: Workspace) -> Dict:
    ups, cps = load_uploads(), _checkpoints()
    out = []
    for u in ups:
        c = cps.get(u["bvid"], [])
        out.append(dict(u, checkpoints=len(c), latest=c[-1] if c else None))
    ws.cache["performance_uploads"] = out
    return {"uploads": out, "with_data": sum(1 for o in out if o["checkpoints"])}


def h_get_checkpoints(ws: Workspace, bvid: str) -> Dict:
    c = _checkpoints().get(bvid, [])
    for r in c:
        v = max(r["view"], 1)
        r["engagement_rate"] = round((r["like"] + r["coin"] + r["favorite"]) / v, 4)
    return {"bvid": bvid, "checkpoints": c}


def _corr(xs: List[float], ys: List[float]) -> float:
    if len(xs) < 3 or statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    return cov / (statistics.pstdev(xs) * statistics.pstdev(ys))


def propose_weights(samples: List[Dict]) -> Dict:
    """samples: [{components:{demand,outlier,freshness,competition}, view}] → 보정안 (적용은 사람)."""
    if len(samples) < MIN_SAMPLES:
        return {"ready": False, "samples": len(samples), "needed": MIN_SAMPLES}
    y = [math.log1p(s["view"]) for s in samples]
    corr = {k: _corr([s["components"][k] for s in samples], y) for k in ("demand", "outlier", "freshness", "competition")}
    raw = {"demand": max(corr["demand"], 0), "outlier": max(corr["outlier"], 0),
           "freshness": max(corr["freshness"], 0), "competition": max(-corr["competition"], 0)}
    total = sum(raw.values()) or 1
    return {"ready": True, "samples": len(samples), "correlation_with_log_views": {k: round(v, 3) for k, v in corr.items()},
            "proposed_weights": {k: round(4 * v / total, 2) for k, v in raw.items()},
            "note": "제안만 한다. 적용은 사람이 승인(score_weights.approved_by)한 뒤 metrics.WEIGHTS 를 바꾼다."}


def h_propose_weights(ws: Workspace) -> Dict:
    samples = [{"components": u["components"], "view": u["latest"]["view"]}
               for u in ws.cache.get("performance_uploads") or h_list_uploads(ws)["uploads"]
               if u.get("components") and u.get("latest")]
    result = propose_weights(samples)
    ws.cache["weight_proposal"] = result
    if result["ready"]:
        config.PERFORMANCE_DIR.mkdir(parents=True, exist_ok=True)
        (config.PERFORMANCE_DIR / "weights.proposed.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                                      encoding="utf-8")
    return result


SPEC = WorkerSpec(
    name="performance", stage="6 성과 기록", db_tables=["uploads", "performance", "score_weights"],
    prompt_file="w6_performance.md",
    tools=[tool("list_uploads", "등록된 업로드(기획안↔bvid)와 성과 기록 개수·최신값."),
           tool("get_checkpoints", "영상 하나의 시점별 성과(조회·좋아요·코인·즐겨찾기·댓글, 반응률).",
                {"bvid": {"type": "string"}}, ["bvid"]),
           tool("propose_weights", "성과 8개 이상이면 점수 가중치 보정안을 계산(적용은 사람).")],
    handlers={"list_uploads": h_list_uploads, "get_checkpoints": h_get_checkpoints, "propose_weights": h_propose_weights},
    submit_tool=submit({
        "per_video": {"type": "array", "items": {"type": "object", "properties": {
            "bvid": {"type": "string"}, "observation_ko": {"type": "string"}}, "required": ["bvid", "observation_ko"]}},
        "next_actions_ko": STR_LIST, "weight_note_ko": {"type": "string"}}, ["per_video", "next_actions_ko"]),
)
