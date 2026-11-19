"""4단계 · 분석 — 코드 부분(근거 팩).

숫자는 코드가 계산해 04_evidence.json 에 둔다. trend-analyst 에이전트는 이 파일만 보고
해석을 04_analysis.json 으로 쓴다. 에이전트는 새 숫자를 만들지 않고 evidence 의 경로를 인용한다
(예: "evidence.topics.grow_a_garden.duration_buckets").
"""
import collections
import datetime as dt
import re
from typing import Dict, List

from .common import median, read_stage, trace, write_stage

BUCKETS = [(0, 15, "~15초"), (15, 30, "15–30초"), (30, 45, "30–45초"), (45, 61, "45–60초"),
           (61, 181, "1–3분"), (181, 10 ** 9, "3분 초과")]
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def duration_buckets(videos: List[Dict]) -> List[Dict]:
    rows = []
    for lo, hi, label in BUCKETS:
        b = [v for v in videos if lo <= v["duration_sec"] < hi]
        rows.append({"bucket": label, "count": len(b),
                     "median_views_per_hour": round(median([v["views_per_hour"] for v in b]), 1),
                     "median_outlier_multiple": round(median([v["outlier_multiple"] for v in b
                                                              if v.get("outlier_multiple") is not None]), 2)})
    return rows


def title_features(videos: List[Dict]) -> Dict:
    n = max(len(videos), 1)
    t = [v["title"] for v in videos]
    return {
        "pool_size": len(videos),
        "median_length": median([len(x) for x in t]),
        "pct_number": round(sum(bool(re.search(r"\d", x)) for x in t) / n, 2),
        "pct_question": round(sum(("?" in x or "？" in x) for x in t) / n, 2),
        "pct_exclaim": round(sum(("!" in x or "！" in x) for x in t) / n, 2),
        "pct_emoji": round(sum(bool(_EMOJI.search(x)) for x in t) / n, 2),
        "pct_hashtag": round(sum("#" in x for x in t) / n, 2),
        "pct_korean": round(sum(bool(re.search("[가-힣]", x)) for x in t) / n, 2),
    }


def top_tags(videos: List[Dict], k: int = 15) -> List[Dict]:
    c = collections.Counter(tag.lower() for v in videos for tag in v.get("tags", []))
    return [{"tag": t, "count": n} for t, n in c.most_common(k)]


def publish_hours_kst(videos: List[Dict]) -> List[Dict]:
    c = collections.Counter()
    for v in videos:
        try:
            t = dt.datetime.fromisoformat(v["published_at"].replace("Z", "+00:00")) + dt.timedelta(hours=9)
            c[t.hour] += 1
        except Exception:
            pass
    return [{"hour_kst": h, "count": c[h]} for h in sorted(c)]


def build_evidence(norm: Dict, scores: Dict, top_k: int = 5) -> Dict:
    videos = norm["videos"]
    topics = {}
    for t in scores["topics"][:top_k]:
        vs = [v for v in videos if t["topic_id"] in v["topics"]]
        vs_sorted = sorted(vs, key=lambda v: -(v.get("outlier_multiple") or 0))
        topics[t["topic_id"]] = {
            "name_ko": t["name_ko"], "score": t["score"], "components": t["components"],
            "videos_in_pool": len(vs), "duration_buckets": duration_buckets(vs),
            "title_features": title_features(vs), "top_tags": top_tags(vs, 10),
            "top_videos": [{k: v[k] for k in ("video_id", "title", "channel_title", "views", "outlier_multiple",
                                              "views_per_hour", "duration_sec", "age_h", "url")}
                           for v in vs_sorted[:6]],
        }
    shorts = [v for v in videos if v["is_short"]]
    quality = []
    if norm.get("is_sample"):
        quality.append("연습용 샘플 데이터입니다. 실제 수치가 아니므로 기획 근거로 공개하지 마세요.")
    no_avg = sum(1 for v in videos if v.get("outlier_multiple") is None)
    if no_avg:
        quality.append("채널 평균을 모르는 영상 %d개는 아웃라이어 계산에서 빠졌습니다." % no_avg)
    unmatched = sum(1 for v in videos if not v["topics"])
    if unmatched:
        quality.append("주제를 못 찾은 영상 %d개 — alias_candidates 를 검토하세요." % unmatched)
    quality.append("채널 평균 조회수는 채널 전체 누적 기준(총 조회수÷영상 수)이라 최근 성과와 다를 수 있습니다.")
    return {
        "disclaimer": scores["disclaimer"], "is_sample": norm.get("is_sample", False),
        "pool": {"videos": len(videos), "shorts": len(shorts),
                 "duration_buckets_shorts": duration_buckets(shorts),
                 "title_features_all": title_features(videos), "publish_hours_kst": publish_hours_kst(videos)},
        "ranking": [{k: t[k] for k in ("topic_id", "name_ko", "score", "components", "videos_in_pool")}
                    for t in scores["topics"]],
        "topics": topics,
        "top_outlier_videos": scores["top_outlier_videos"],
        "alias_candidates": norm.get("alias_candidates", []),
        "data_quality": quality,
    }


def run(run_id: str) -> Dict:
    ev = build_evidence(read_stage(run_id, "normalized"), read_stage(run_id, "scores"))
    write_stage(run_id, "evidence", ev)
    msg = "근거 팩 생성: 상위 주제 %d개, 품질 메모 %d개" % (len(ev["topics"]), len(ev["data_quality"]))
    trace(run_id, "analyze", msg)
    return {"run_id": run_id, "summary": msg, "next": "trend-analyst 에이전트가 04_analysis.json 작성"}
