"""3단계 · 점수화 (코드만, LLM 없음 — 같은 데이터면 언제나 같은 점수).

Score_yt(주제) = w1·수요 + w2·아웃라이어 + w3·신선도 − w4·경쟁도   (각 항목 0~1)

  수요       : 주제 영상들의 시간당 조회수 합(정규화)과 차트·검색 순위 가중치(정규화)의 평균
  아웃라이어 : 주제 영상의 '채널 평균 조회수 대비 배수' 중앙값 ÷ outlier_cap (최대 1)
               → 구독자가 적은 채널에서도 터졌는가 = 소재 자체의 힘
  신선도     : 게시 후 경과 시간의 반감기 감쇠 중앙값 (기본 72시간)
  경쟁도     : 풀 안에서 같은 주제 영상 수(정규화). 많을수록 레드오션
※ 이 점수는 '정렬 참고용'이다. 조회수 예측으로 쓰지 않는다 (기획안·보고서에 문구를 강제).
가중치는 config/pipeline.json 의 score.weights. 성과 기록이 쌓이면 performance calibrate 로 보정안을 만든다.
"""
from typing import Dict, List

from .common import load_config, median, read_stage, rnd, trace, write_stage
from .normalize import AliasStore


def _list_weight(lists: List[Dict]) -> float:
    """인기 차트·검색 결과 상위일수록 큰 값 (순위 1 → 1.0, 50 → 0.02)."""
    return sum((51 - min(s["rank"], 50)) / 50 for s in lists)


def score_topics(videos: List[Dict], alias: AliasStore, scfg: Dict) -> List[Dict]:
    w, half, cap = scfg["weights"], scfg["freshness_half_life_h"], scfg["outlier_cap"]
    groups: Dict[str, List[Dict]] = {}
    for v in videos:
        for t in v["topics"]:
            groups.setdefault(t, []).append(v)

    raw = {}
    for tid, vs in groups.items():
        mults = [v["outlier_multiple"] for v in vs if v.get("outlier_multiple") is not None]
        raw[tid] = {
            "vph": sum(v["views_per_hour"] for v in vs),
            "rank": sum(_list_weight(v["lists"]) for v in vs),
            "outlier_median": median(mults),
            "outlier": min(median(mults) / cap, 1.0) if mults else 0.0,
            "freshness": median([0.5 ** (v["age_h"] / half) for v in vs]),
            "count": len(vs),
            "channels": len({v["channel_id"] for v in vs}),
            "shorts_ratio": sum(v["is_short"] for v in vs) / len(vs),
            "median_engagement": median([v["engagement_rate"] for v in vs]),
        }

    def norm(key):
        top = max((r[key] for r in raw.values()), default=0) or 1
        return {t: r[key] / top for t, r in raw.items()}

    n_vph, n_rank, n_cnt = norm("vph"), norm("rank"), norm("count")
    out = []
    for tid, r in raw.items():
        comp = {"demand": (n_vph[tid] + n_rank[tid]) / 2, "outlier": r["outlier"],
                "freshness": r["freshness"], "competition": n_cnt[tid]}
        s = (w["demand"] * comp["demand"] + w["outlier"] * comp["outlier"]
             + w["freshness"] * comp["freshness"] - w["competition"] * comp["competition"])
        t = alias.get(tid)
        out.append({"topic_id": tid, "name_ko": t["name_ko"], "name_en": t["name_en"], "score": round(s, 3),
                    "components": rnd(comp), "videos_in_pool": r["count"], "channels": r["channels"],
                    "median_outlier_multiple": round(r["outlier_median"], 2),
                    "median_engagement_rate": round(r["median_engagement"], 4),
                    "total_views_per_hour": round(r["vph"], 1), "shorts_ratio": round(r["shorts_ratio"], 2)})
    return sorted(out, key=lambda x: -x["score"])


def top_outlier_videos(videos: List[Dict], n: int = 15) -> List[Dict]:
    """채널 평균 대비 많이 터진 영상 (1of10 방식). 기획안 근거로 쓴다."""
    vs = [v for v in videos if v.get("outlier_multiple") is not None]
    vs.sort(key=lambda v: -v["outlier_multiple"])
    keep = ("video_id", "title", "channel_title", "views", "outlier_multiple", "views_per_hour",
            "engagement_rate", "duration_sec", "is_short", "age_h", "topics", "url")
    return [{k: v[k] for k in keep} for v in vs[:n]]


def run(run_id: str) -> Dict:
    cfg = load_config()
    norm = read_stage(run_id, "normalized")
    alias = AliasStore()
    topics = score_topics(norm["videos"], alias, cfg["score"])
    out = {"formula": "Score_yt = w1·demand + w2·outlier + w3·freshness − w4·competition",
           "weights": cfg["score"]["weights"], "disclaimer": cfg["score"]["disclaimer"],
           "is_sample": norm.get("is_sample", False), "topics": topics,
           "top_outlier_videos": top_outlier_videos(norm["videos"])}
    write_stage(run_id, "scores", out)
    head = ", ".join("%s %.3f" % (t["name_ko"], t["score"]) for t in topics[:3])
    msg = "주제 %d개 점수화. 상위: %s" % (len(topics), head or "(없음)")
    trace(run_id, "score", msg)
    return {"run_id": run_id, "summary": msg}
