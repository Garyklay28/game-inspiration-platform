"""8단계 · 성과 기록 → 점수 가중치 보정.

  register   업로드한 영상 ID 를 기획안(run)과 연결 → performance/uploads.json
             (업로드 자체는 사람이 한다. 이 파이프라인은 게시·업로드를 하지 않는다)
  fetch      YouTube Data API 로 조회수·좋아요·댓글을 읽어 performance/log.jsonl 에 쌓는다
  manual     API 없이 YouTube Studio 숫자를 직접 기록
  summary    영상별 24h·72h·7d 체크포인트 표 → performance/summary.json / .md
  calibrate  체크포인트 성과와 기획 당시 점수 항목의 상관을 보고 가중치 보정안을 만든다
             → config/weights.proposed.json (자동 적용하지 않음)
  apply      사람이 보정안을 승인하면 config/pipeline.json 의 score.weights 에 반영
"""
import datetime as dt
import json
import math
import os
from typing import Dict, List, Optional

from .collect import CollectError, _get
from .common import (CONFIG_DIR, PERF_DIR, load_config, load_env, now_iso, read_json, read_stage, write_json)

UPLOADS = PERF_DIR / "uploads.json"
LOG = PERF_DIR / "log.jsonl"
COMPONENTS = ["demand", "outlier", "freshness", "competition"]


def _uploads() -> List[Dict]:
    return read_json(UPLOADS) if UPLOADS.exists() else []


def _log() -> List[Dict]:
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append(rec: Dict) -> None:
    PERF_DIR.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def register(run_id: str, video_id: str, published_at: Optional[str] = None) -> Dict:
    plan = read_stage(run_id, "plan")
    scores = read_stage(run_id, "scores")
    topic = next((t for t in scores["topics"] if t["topic_id"] == plan.get("topic_id")), None)
    ups = [u for u in _uploads() if u["video_id"] != video_id]
    ups.append({"video_id": video_id, "run_id": run_id, "plan_id": plan.get("plan_id"),
                "topic_id": plan.get("topic_id"), "content_type": plan.get("content_type"),
                "selected_hook": plan.get("selected_hook"), "target_duration_sec": plan.get("target_duration_sec"),
                "components": topic and topic["components"], "topic_score": topic and topic["score"],
                "is_sample_data": scores.get("is_sample", False),
                "published_at": published_at, "registered_at": now_iso()})
    write_json(UPLOADS, ups)
    return {"summary": "등록: %s ← %s" % (video_id, plan.get("plan_id")), "count": len(ups)}


def fetch() -> Dict:
    load_env()
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        raise CollectError("YOUTUBE_API_KEY 가 없습니다. API 없이 기록하려면 performance manual 사용")
    ups = _uploads()
    if not ups:
        return {"summary": "등록된 영상이 없습니다 (performance register 먼저)"}
    res = _get("videos", {"part": "statistics,snippet", "id": ",".join(u["video_id"] for u in ups)}, key)
    n = 0
    by_id = {it["id"]: it for it in res.get("items", [])}
    for u in ups:
        it = by_id.get(u["video_id"])
        if not it:
            continue
        if not u.get("published_at"):
            u["published_at"] = it["snippet"].get("publishedAt")
        st = it.get("statistics", {})
        _append({"video_id": u["video_id"], "at": now_iso(), "source": "api",
                 "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0) or 0),
                 "comments": int(st.get("commentCount", 0) or 0)})
        n += 1
    write_json(UPLOADS, ups)
    return {"summary": "기록 %d건 (조회 실패 %d건)" % (n, len(ups) - n)}


def manual(video_id: str, views: int, likes: int = 0, comments: int = 0, at: Optional[str] = None) -> Dict:
    _append({"video_id": video_id, "at": at or now_iso(), "source": "manual",
             "views": views, "likes": likes, "comments": comments})
    return {"summary": "수동 기록: %s views=%d" % (video_id, views)}


def _age_h(published: str, at: str) -> Optional[float]:
    try:
        p = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
        a = dt.datetime.fromisoformat(at.replace("Z", "+00:00"))
        return (a - p).total_seconds() / 3600
    except Exception:
        return None


def summary() -> Dict:
    cps = load_config()["performance"]["checkpoints_h"]
    logs = _log()
    rows = []
    for u in _uploads():
        recs = sorted((r for r in logs if r["video_id"] == u["video_id"]), key=lambda r: r["at"])
        row = {"video_id": u["video_id"], "plan_id": u["plan_id"], "topic_id": u["topic_id"],
               "content_type": u.get("content_type"), "topic_score": u.get("topic_score"),
               "is_sample_data": u.get("is_sample_data", False), "snapshots": len(recs)}
        for cp in cps:
            # 체크포인트 시각에 가장 가까운(±30%) 기록. 없으면 비워 둔다 — 보간으로 숫자를 만들지 않는다
            best = None
            for r in recs:
                age = _age_h(u.get("published_at") or "", r["at"])
                if age is not None and abs(age - cp) <= cp * 0.3 and (best is None or abs(age - cp) < abs(best[0] - cp)):
                    best = (age, r)
            row["views_%dh" % cp] = best[1]["views"] if best else None
        if recs:
            row["latest_views"] = recs[-1]["views"]
        rows.append(row)
    out = {"generated_at": now_iso(), "checkpoints_h": cps, "rows": rows}
    write_json(PERF_DIR / "summary.json", out)
    md = ["| 영상 | 주제 | 유형 | 점수 | " + " | ".join("%dh" % c for c in cps) + " | 최신 |",
          "|---|---|---|---|" + "---|" * (len(cps) + 1)]
    for r in rows:
        md.append("| %s | %s | %s | %s | %s | %s |" % (r["video_id"], r["topic_id"], r["content_type"], r["topic_score"],
                                                     " | ".join(str(r["views_%dh" % c] or "–") for c in cps),
                                                     r.get("latest_views", "–")))
    (PERF_DIR / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"summary": "영상 %d개 요약 → performance/summary.md" % len(rows)}


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def calibrate(checkpoint_h: int = 72) -> Dict:
    cfg = load_config()
    summary()
    rows = read_json(PERF_DIR / "summary.json")["rows"]
    ups = {u["video_id"]: u for u in _uploads()}
    data = [(ups[r["video_id"]]["components"], r["views_%dh" % checkpoint_h]) for r in rows
            if r.get("views_%dh" % checkpoint_h) and ups[r["video_id"]].get("components")
            and not r.get("is_sample_data")]
    need = cfg["performance"]["min_samples_for_calibration"]
    if len(data) < need:
        return {"summary": "표본 %d개 — 보정에는 %d개 이상 필요(샘플 데이터 기반 기획은 제외). 지금 가중치 유지." % (len(data), need)}
    y = [math.log10(v + 1) for _, v in data]
    cur = cfg["score"]["weights"]
    corr, proposed = {}, {}
    for k in COMPONENTS:
        c = _pearson([comp[k] for comp, _ in data], y)
        corr[k] = None if c is None else round(c, 3)
        if c is None:
            proposed[k] = cur[k]
            continue
        # competition 은 빼는 항목이라 상관이 음수일수록(경쟁 많을수록 성과 낮음) 가중치를 키운다
        signed = -c if k == "competition" else c
        proposed[k] = round(min(max(cur[k] * (1 + signed), 0.2), 2.0), 2)
    out = {"created_at": now_iso(), "checkpoint_h": checkpoint_h, "samples": len(data),
           "target": "log10(views_%dh)" % checkpoint_h, "correlations": corr,
           "current_weights": cur, "proposed_weights": proposed,
           "note": "상관은 인과가 아니다. 표본이 적으면 흔들린다. 사람이 보고 perf apply 로 반영한다."}
    write_json(CONFIG_DIR / "weights.proposed.json", out)
    return {"summary": "보정안 → config/weights.proposed.json (표본 %d)" % len(data), "proposal": out}


def apply_proposed() -> Dict:
    prop = read_json(CONFIG_DIR / "weights.proposed.json")
    path = CONFIG_DIR / "pipeline.json"
    cfg = read_json(path)
    old = cfg["score"]["weights"]
    cfg["score"]["weights"] = prop["proposed_weights"]
    cfg["score"].setdefault("weights_history", []).append({"applied_at": now_iso(), "from": old,
                                                          "to": prop["proposed_weights"], "samples": prop["samples"]})
    write_json(path, cfg)
    return {"summary": "가중치 반영: %s → %s" % (old, prop["proposed_weights"])}
