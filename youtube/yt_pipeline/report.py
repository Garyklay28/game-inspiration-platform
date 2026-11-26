"""실행 하나(runs/<id>)의 산출물을 모아 YouTubeReport(report.json)로 만든다."""
import json
from typing import Dict

from .common import FILES, PERF_DIR, read_json, run_dir, write_stage
from .contracts import YouTubeReport


def _opt(run_id: str, key: str):
    p = run_dir(run_id) / FILES[key]
    return read_json(p) if p.exists() else None


def build(run_id: str, intent: str = "make_video", task_id: str = "local-demo") -> Dict:
    d = run_dir(run_id)
    raw, scores, ev = _opt(run_id, "raw"), _opt(run_id, "scores"), _opt(run_id, "evidence")
    analysis, plan, val = _opt(run_id, "analysis"), _opt(run_id, "plan"), _opt(run_id, "validation")
    warnings = list((ev or {}).get("data_quality", []))
    reasons = {c.get("topic_id"): c.get("claim") for c in (analysis or {}).get("claims", []) if c.get("topic_id")}
    opps = [dict(t, reason_ko=reasons.get(t["topic_id"])) for t in (scores or {}).get("topics", [])[:5]]

    video = None
    out = d / "07_video" / "output"
    if out.exists():
        qas = [read_json(p) for p in sorted(out.glob("*.qa.json"))]
        video = {"renders": [{"file": q["file"], "kind": q["kind"], "verdict": q["verdict"],
                              "visual_review": (q.get("visual_review") or {}).get("passed")} for q in qas]}
    td = d / "05_thumbnails"
    thumbs = [read_json(p) for p in sorted(td.glob("thumb_v*.json"))] if td.exists() else []
    if thumbs:
        video = dict(video or {}, thumbnails=[{"file": t["file"], "source": t["source"]} for t in thumbs])
    perf = read_json(PERF_DIR / "summary.json") if (PERF_DIR / "summary.json").exists() else None
    if perf:
        perf = {"rows": [r for r in perf["rows"] if r.get("plan_id") == (plan or {}).get("plan_id")]}
    trace = [json.loads(l) for l in (d / FILES["trace"]).read_text(encoding="utf-8").splitlines() if l.strip()] \
        if (d / FILES["trace"]).exists() else []
    if val and not val.get("passed"):
        warnings.append("기획안 검증 미통과: %s" % val.get("next"))
    rep = YouTubeReport(
        task_id=task_id, intent=intent, run_id=run_id,
        summary_ko=(analysis or {}).get("summary", "(trend-analyst 분석 없음)"),
        opportunities=opps,
        duration_advice=(ev or {}).get("pool", {}).get("duration_buckets_shorts") and
        {"shorts_buckets": ev["pool"]["duration_buckets_shorts"],
         "recommended_sec": (analysis or {}).get("recommended_duration_sec")},
        alias_candidates=(ev or {}).get("alias_candidates", []),
        plan=plan, plan_validation=val, video=video, performance=perf,
        data_sources=[{"name": "YouTube Data API v3" if (raw or {}).get("source") == "api" else (raw or {}).get("source"),
                       "collected_at": (raw or {}).get("collected_at"), "is_sample": (raw or {}).get("is_sample")}],
        agent_trace=trace, warnings=warnings)
    write_stage(run_id, "report", rep.to_dict())
    return {"run_id": run_id, "summary": "report.json 생성 (경고 %d)" % len(warnings)}
