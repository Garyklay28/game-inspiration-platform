"""Supabase 저장 (6개 에이전트가 같은 DB 를 쓰도록).

  db export --run ID   실행 폴더의 결과를 db/schema.sql 테이블 모양의 행으로 바꿔
                       runs/<id>/db/<table>.json 에 쓴다 (네트워크 없음)
  db push --run ID     위 행을 Supabase REST(PostgREST)로 upsert 한다
                       .env 의 SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 필요

파일이 원본이고 DB 는 웹 화면과 팀원이 같이 보기 위한 사본이다. push 를 다시 해도 같은 행은 덮어쓴다.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List

from .common import FILES, PERF_DIR, load_env, read_json, run_dir, trace, write_json

# 외래 키 순서대로 넣는다
ORDER = ["raw_snapshots", "channels", "videos", "topic_scores", "analyses", "plans", "thumbnails", "uploads", "performance"]
CONFLICT = {"raw_snapshots": "id", "channels": "platform,channel_id", "videos": "platform,video_id,run_id",
            "topic_scores": "run_id,platform,game_id", "analyses": "analysis_id", "plans": "plan_id",
            "thumbnails": "file_path", "uploads": "video_id", "performance": "video_id,at"}


def _opt(path: Path):
    return read_json(path) if path.exists() else None


def build_rows(run_id: str) -> Dict[str, List[Dict]]:
    d = run_dir(run_id)
    raw, norm = _opt(d / FILES["raw"]), _opt(d / FILES["normalized"])
    scores, analysis = _opt(d / FILES["scores"]), _opt(d / FILES["analysis"])
    plan, status = _opt(d / FILES["plan"]), _opt(d / "05_plan.status.json")
    rows: Dict[str, List[Dict]] = {t: [] for t in ORDER}
    if raw:
        rows["raw_snapshots"].append({"id": "%s:youtube" % run_id, "run_id": run_id, "platform": "youtube",
                                      "source": raw.get("source"), "is_sample": bool(raw.get("is_sample")),
                                      "collected_at": raw.get("collected_at"), "payload": raw})
    if norm:
        seen = set()
        for v in norm["videos"]:
            if v["channel_id"] and v["channel_id"] not in seen:
                seen.add(v["channel_id"])
                rows["channels"].append({"platform": "youtube", "channel_id": v["channel_id"],
                                         "title": v.get("channel_title"),
                                         "subscribers": v.get("channel_subscribers") or None,
                                         "avg_views": v.get("channel_avg_views")})
            rows["videos"].append({"platform": "youtube", "video_id": v["video_id"], "run_id": run_id,
                                   "game_ids": v["topics"], "channel_id": v["channel_id"] or None,
                                   "title": v["title"], "views": v["views"], "likes": v["likes"],
                                   "comments": v["comments"], "duration_sec": v["duration_sec"],
                                   "is_short": v["is_short"], "published_at": v["published_at"] or None,
                                   "outlier_multiple": v.get("outlier_multiple"),
                                   "views_per_hour": v.get("views_per_hour")})
    if scores:
        for t in scores["topics"]:
            c = t["components"]
            rows["topic_scores"].append({"run_id": run_id, "platform": "youtube", "game_id": t["topic_id"],
                                         "demand": c["demand"], "outlier": c["outlier"],
                                         "freshness": c["freshness"], "competition": c["competition"],
                                         "score": t["score"], "videos_in_pool": t["videos_in_pool"]})
    if analysis:
        rows["analyses"].append({"analysis_id": run_id, "run_id": run_id, "platform": "youtube",
                                 "game_id": analysis.get("selected_topic_id"), "summary": analysis.get("summary"),
                                 "claims": analysis.get("claims", [])})
    if plan:
        rows["plans"].append({"plan_id": plan["plan_id"], "run_id": run_id, "platform": "youtube",
                              "game_id": plan.get("topic_id"), "plan": plan,
                              "status": (status or {}).get("status", "draft")})
        for meta in sorted((d / "05_thumbnails").glob("thumb_v*.json")) if (d / "05_thumbnails").exists() else []:
            m = read_json(meta)
            rows["thumbnails"].append({"file_path": m["file"], "plan_id": m["plan_id"], "ratio": m["ratio"],
                                       "source": m["source"], "prompt": m.get("prompt"),
                                       "overlay_text": m.get("overlay_text"), "created_at": m["created_at"]})
    ups = _opt(PERF_DIR / "uploads.json") or []
    mine = [u for u in ups if u.get("run_id") == run_id]
    ids = {u["video_id"] for u in mine}
    rows["uploads"] = [{"video_id": u["video_id"], "plan_id": u["plan_id"], "platform": "youtube",
                        "published_at": u.get("published_at"), "registered_at": u["registered_at"]} for u in mine]
    log = PERF_DIR / "log.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["video_id"] in ids:
                    rows["performance"].append({k: r.get(k) for k in ("video_id", "at", "source", "views", "likes", "comments")})
    return rows


def export(run_id: str) -> Dict:
    rows = build_rows(run_id)
    out = run_dir(run_id) / "db"
    for t, rs in rows.items():
        write_json(out / ("%s.json" % t), rs)
    counts = {t: len(rs) for t, rs in rows.items()}
    trace(run_id, "db.export", "행 수 %s" % counts)
    return {"run_id": run_id, "summary": "runs/%s/db/ 에 테이블별 JSON 저장" % run_id, "counts": counts}


def _post(url: str, key: str, table: str, rows: List[Dict]) -> None:
    req = urllib.request.Request(
        "%s/rest/v1/%s?on_conflict=%s" % (url.rstrip("/"), table, CONFLICT[table]),
        data=json.dumps(rows, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=60):
            pass
    except urllib.error.HTTPError as e:
        raise RuntimeError("Supabase %s 저장 실패 %s: %s" % (table, e.code, e.read().decode("utf-8", "ignore")[:300]))


def push(run_id: str, poster=_post) -> Dict:
    load_env()
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 가 .env 에 없습니다 (db/schema.sql 을 먼저 실행)")
    rows = build_rows(run_id)
    sent = {}
    for t in ORDER:
        rs = rows[t]
        for i in range(0, len(rs), 500):
            poster(url, key, t, rs[i:i + 500])
        sent[t] = len(rs)
    trace(run_id, "db.push", "Supabase upsert %s" % sent)
    return {"run_id": run_id, "summary": "Supabase 에 저장", "counts": sent}
