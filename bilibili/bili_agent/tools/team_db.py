"""팀 공용 DB(기획안 13장 「데이터베이스 설계」)에 맞춘 행 만들기.

세 플랫폼이 같은 테이블을 쓰고 platform='bilibili' 로 구분한다. 스키마 원본은 팀 저장소의 youtube/db/schema.sql.
- export: 행을 JSON 파일로 저장 (기본, 네트워크 없음)
- push  : SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY 가 있을 때만 PostgREST upsert (명시적으로 --db-push 를 줄 때)
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List

PLATFORM = "bilibili"
CONFLICT = {"raw_snapshots": "id", "videos": "platform,video_id,run_id", "topic_scores": "run_id,platform,game_id",
            "analyses": "analysis_id", "plans": "plan_id", "uploads": "video_id", "performance": "video_id,at"}
ORDER = ["raw_snapshots", "videos", "topic_scores", "analyses", "plans", "uploads", "performance"]


def _iso(ts) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def build_rows(ws, report: Dict) -> Dict[str, List[Dict]]:
    rid = ws.run_id
    rows: Dict[str, List[Dict]] = {k: [] for k in ORDER}
    for i, s in enumerate(ws.cache.get("raw_snapshots", [])):
        rows["raw_snapshots"].append({
            "id": "%s:%s:%d" % (rid, PLATFORM, i), "run_id": rid, "platform": PLATFORM,
            "source": s["source"] if s["source"] != "snapshot" else "file:" + (s.get("file") or "ranking"),
            "is_sample": False, "collected_at": s.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
            "payload": s})
    now_h = datetime.now(timezone.utc).timestamp() / 3600
    for v in ws.videos:
        hours = max(now_h - (v.get("pubdate") or 0) / 3600, 1) if v.get("pubdate") else None
        rows["videos"].append({
            "video_id": v["bvid"], "platform": PLATFORM, "run_id": rid, "game_ids": v.get("game_ids") or [],
            "channel_id": v.get("author"), "title": v["title"], "views": v["view"], "likes": v["like"],
            "comments": v["reply"], "coins": v["coin"], "favorites": v["favorite"], "duration_sec": v.get("duration_sec"),
            "is_short": v["duration_sec"] < 60 if v.get("duration_sec") else None, "published_at": _iso(v.get("pubdate")),
            "outlier_multiple": None, "views_per_hour": round(v["view"] / hours, 1) if hours else None})
    for s in ws.cache.get("game_scores") or []:
        c = s["components"]
        rows["topic_scores"].append({"run_id": rid, "platform": PLATFORM, "game_id": s["game_id"],
                                     "demand": c["demand"], "outlier": c["outlier"], "freshness": c["freshness"],
                                     "competition": c["competition"], "score": s["score"],
                                     "videos_in_pool": s["videos_in_pool"]})
    a = ws.findings.get("analyst")
    if a:
        rows["analyses"].append({"analysis_id": "%s:%s" % (rid, PLATFORM), "run_id": rid, "platform": PLATFORM,
                                 "game_id": ws.requested_game["game_id"] if ws.requested_game else None,
                                 "summary": a.get("summary_ko"), "claims": a.get("claims", [])})
    plan = report.get("plan")
    if plan:
        rows["plans"].append({"plan_id": plan["plan_id"], "run_id": rid, "platform": PLATFORM,
                              "game_id": plan.get("game_id"), "plan": plan, "status": plan.get("status", "draft")})
    for u in ws.cache.get("performance_uploads") or []:
        rows["uploads"].append({"video_id": u["bvid"], "plan_id": u.get("plan_id"), "platform": PLATFORM})
        if u.get("latest"):
            l = u["latest"]
            rows["performance"].append({"video_id": u["bvid"], "at": l.get("at") or datetime.now(timezone.utc).isoformat(),
                                        "source": l.get("source", "aside"), "views": l["view"], "likes": l["like"],
                                        "comments": l["reply"]})
    return rows


def export(rows: Dict[str, List[Dict]], path) -> Dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {k: len(v) for k, v in rows.items()}


def push(rows: Dict[str, List[Dict]]) -> Dict[str, int]:
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not (url and key):
        raise RuntimeError("SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 가 .env 에 없습니다 (팀 스키마를 먼저 실행)")
    sent = {}
    for table in ORDER:
        if not rows[table]:
            continue
        req = urllib.request.Request(
            "%s/rest/v1/%s?on_conflict=%s" % (url.rstrip("/"), table, CONFLICT[table]),
            data=json.dumps(rows[table], ensure_ascii=False, default=str).encode("utf-8"), method="POST",
            headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"})
        with urllib.request.urlopen(req, timeout=60):
            pass
        sent[table] = len(rows[table])
    return sent
