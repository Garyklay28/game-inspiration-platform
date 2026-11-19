"""결정적 지표 계산 (LLM 없음).

LLM은 숫자를 '만들지' 않고, 여기서 계산한 숫자를 '해석'만 한다.
그래서 같은 데이터면 언제나 같은 점수가 나온다(재현 가능).
"""
import math
import re
import statistics
import time
from typing import Dict, List, Optional

# ── 1. 반응률 ─────────────────────────────────────────────

def engagement(v: Dict) -> Dict[str, float]:
    view = max(v.get("view", 0), 1)
    rates = {
        "coin_rate": v.get("coin", 0) / view,
        "favorite_rate": v.get("favorite", 0) / view,
        "like_rate": v.get("like", 0) / view,
        "share_rate": v.get("share", 0) / view,
    }
    # 기획안: 즐겨찾기·코인·좋아요·공유율로 정렬
    rates["engagement_rate"] = sum(rates.values())
    return rates


def _median(values: List[float], default: float = 0.0) -> float:
    return statistics.median(values) if values else default


def rank_by_engagement(videos: List[Dict], top: int = 10) -> Dict:
    """반응률 정렬 + 풀(pool) 중앙값 대비 배수."""
    rows = []
    for v in videos:
        e = engagement(v)
        rows.append({"bvid": v["bvid"], "title": v["title"], "view": v["view"], **e})
    med_eng = _median([r["engagement_rate"] for r in rows])
    med_coin = _median([r["coin_rate"] for r in rows])
    for r in rows:
        r["engagement_multiple"] = r["engagement_rate"] / med_eng if med_eng else 0.0
        r["coin_multiple"] = r["coin_rate"] / med_coin if med_coin else 0.0
    rows.sort(key=lambda r: r["engagement_rate"], reverse=True)
    return {"pool_size": len(rows), "median_engagement_rate": med_eng,
            "median_coin_rate": med_coin, "top": [_round(r) for r in rows[:top]]}


# ── 2. 영상 길이 · 유형 분포 ──────────────────────────────

DURATION_BUCKETS = [(0, 60, "1분 미만"), (60, 180, "1–3분"), (180, 600, "3–10분"),
                    (600, 1800, "10–30분"), (1800, 3600, "30–60분"), (3600, 10 ** 9, "60분 이상")]

# 기획안의 6개 유형 + 실측 데이터에서 비중이 커서 추가한 'e스포츠'. 매칭이 없으면 '기타'.
TYPE_RULES = [
    ("AI창작", ["AI", "ai生成", "AI绘", "AI做"]),
    ("e스포츠", ["夺冠", "决赛", "战队", "LPL", "LCK", "S赛", "总决赛", "赛后", "BLG", "选手"]),
    ("PV·공식", ["PV", "预告", "前瞻", "动画短片", "CG", "官方", "版本更新", "EP"]),
    ("공략", ["攻略", "教程", "技巧", "配队", "打法", "平民", "阵容", "毕业", "单核", "速通", "摆完挂"]),
    ("리뷰·평가", ["锐评", "评测", "测评", "盘点", "从夯到拉", "推荐", "排行", "值不值"]),
    ("밈·2차창작", ["整活", "鬼畜", "梗", "搞笑", "MAD", "GMV", "手书", "名场面", "绷"]),
    ("실황", ["实况", "直播", "录播", "一命", "通关", "全流程", "挑战", "第一视角"]),
]


def classify_type(title: str) -> str:
    for label, keywords in TYPE_RULES:
        if any(k in title for k in keywords):
            return label
    return "기타"


def duration_and_type_distribution(videos: List[Dict]) -> Dict:
    buckets = []
    for lo, hi, label in DURATION_BUCKETS:
        in_b = [v for v in videos if lo <= (v.get("duration_sec") or 0) < hi]
        buckets.append({"bucket": label, "count": len(in_b),
                        "median_view": int(_median([v["view"] for v in in_b]))})
    types = {}
    for v in videos:
        t = classify_type(v["title"])
        types.setdefault(t, []).append(v["view"])
    type_rows = sorted(({"type": t, "count": len(vs), "median_view": int(_median(vs))}
                        for t, vs in types.items()), key=lambda r: -r["count"])
    most_common = max(buckets, key=lambda b: b["count"]) if videos else None
    best_median = max((b for b in buckets if b["count"] >= 2), key=lambda b: b["median_view"],
                      default=None)
    return {"duration_buckets": buckets, "type_distribution": type_rows,
            "most_common_bucket": most_common and most_common["bucket"],
            "best_median_bucket(count>=2)": best_median and best_median["bucket"]}


# ── 3. 제목 진단 ──────────────────────────────────────────

def title_features(title: str) -> Dict:
    return {
        "length": len(title),
        "square_brackets": title.count("【"),  # 【】
        "book_brackets": title.count("《"),  # 《》
        "has_question_or_exclaim": bool(re.search(r"[？?！!]", title)),
        "has_number": bool(re.search(r"\d", title)),
    }


def title_benchmark(videos: List[Dict]) -> Dict:
    feats = [title_features(v["title"]) for v in videos]
    n = max(len(feats), 1)
    return {
        "pool_size": len(feats),
        "median_length": _median([f["length"] for f in feats]),
        "pct_square_brackets": sum(f["square_brackets"] > 0 for f in feats) / n,
        "pct_book_brackets": sum(f["book_brackets"] > 0 for f in feats) / n,
        "pct_question_or_exclaim": sum(f["has_question_or_exclaim"] for f in feats) / n,
        "pct_number": sum(f["has_number"] for f in feats) / n,
    }


def diagnose_title(title: str, benchmark: Dict) -> Dict:
    f = title_features(title)
    gap = f["length"] - benchmark["median_length"]
    return {"title": title, "features": f, "benchmark": _round(benchmark),
            "length_gap_vs_median": gap, "detected_type": classify_type(title)}


# ── 4. 게임별 집계 · 소재 점수 ────────────────────────────

FRESHNESS_HALF_LIFE_H = 72.0
EVENT_BONUS = 0.2
WEIGHTS = {"demand": 1.0, "outlier": 1.0, "freshness": 1.0, "competition": 1.0}  # 기획안: 초기 동일 가중치


def aggregate_by_game(videos: List[Dict], alias_store) -> Dict[str, Dict]:
    games = {}
    for v in videos:
        for g in alias_store.find_in_text(v["title"]):
            row = games.setdefault(g["game_id"], {"game": g, "videos": []})
            row["videos"].append(v)
    return games


def hot_keyword_signals(keywords: List[Dict], videos: List[Dict], alias_store) -> List[Dict]:
    """핫서치 키워드 중 게임 관련 키워드. 인기 영상 풀에 해당 게임 영상이 적으면 '선행 신호'."""
    by_game = aggregate_by_game(videos, alias_store)
    signals = []
    for kw in keywords:
        for g in alias_store.find_in_text(kw["keyword"]):
            n_videos = len(by_game.get(g["game_id"], {}).get("videos", []))
            signals.append({"keyword": kw["keyword"], "rank": kw["rank"], "game_id": g["game_id"],
                            "game_zh": g["zh"], "videos_in_pool": n_videos,
                            "leading_signal": n_videos <= 1})
    return signals


def event_signals(videos: List[Dict], alias_store) -> List[Dict]:
    """공식 활동(mission_id) 참여 영상을 게임별로 묶는다."""
    rows = {}
    for v in videos:
        if not v.get("mission_id"):
            continue
        games = alias_store.find_in_text(v["title"]) or [{"game_id": "unmatched", "zh": "(미매칭)"}]
        for g in games:
            r = rows.setdefault((g["game_id"], v["mission_id"]),
                                {"game_id": g["game_id"], "game_zh": g["zh"], "mission_id": v["mission_id"],
                                 "videos": 0, "total_view": 0, "sample_titles": []})
            r["videos"] += 1
            r["total_view"] += v["view"]
            if len(r["sample_titles"]) < 3:
                r["sample_titles"].append(v["title"])
    return sorted(rows.values(), key=lambda r: -r["total_view"])


def score_games(videos: List[Dict], keywords: List[Dict], alias_store, now: Optional[float] = None) -> List[Dict]:
    """Score_bili = w1·수요 + w2·아웃라이어 배수 + w3·신선도 − w4·경쟁도 (각 항목 0~1 정규화).

    수요      : 핫서치 순위 가중합(상위일수록 큼) 과 조회수 합의 평균
    아웃라이어: 게임 영상 반응률 중앙값 ÷ 전체 풀 중앙값 (3배 이상이면 1)
    신선도    : 게시 후 경과시간 반감기(72h) 감쇠 평균 + 공식 활동 참여 시 가산
    경쟁도    : 풀 안의 같은 게임 영상 수
    ※ 기획안대로 이 점수는 '정렬 참고용'이며 조회수 예측치로 쓰지 않는다.
    """
    now = now or time.time()
    by_game = aggregate_by_game(videos, alias_store)
    pool_med = _median([engagement(v)["engagement_rate"] for v in videos]) or 1e-9
    kw_weight = {}
    for kw in keywords:
        for g in alias_store.find_in_text(kw["keyword"]):
            kw_weight[g["game_id"]] = kw_weight.get(g["game_id"], 0) + (31 - min(kw["rank"], 30)) / 30
    for gid in kw_weight:
        by_game.setdefault(gid, {"game": alias_store.resolve_id(gid), "videos": []})

    raw = {}
    for gid, row in by_game.items():
        vs = row["videos"]
        med = _median([engagement(v)["engagement_rate"] for v in vs])
        fresh = _median([0.5 ** (max(now - (v.get("pubdate") or now), 0) / 3600 / FRESHNESS_HALF_LIFE_H)
                         for v in vs])
        if any(v.get("mission_id") for v in vs):
            fresh += EVENT_BONUS
        raw[gid] = {"trend": kw_weight.get(gid, 0.0), "views": sum(v["view"] for v in vs),
                    "outlier": min((med / pool_med) / 3.0, 1.0) if vs else 0.0,
                    "freshness": min(fresh, 1.0), "count": len(vs),
                    "engagement_multiple": med / pool_med if vs else 0.0}

    def norm(key):
        top = max((r[key] for r in raw.values()), default=0) or 1
        return {gid: r[key] / top for gid, r in raw.items()}

    n_trend, n_views, n_count = norm("trend"), norm("views"), norm("count")
    results = []
    for gid, r in raw.items():
        comp = {"demand": (n_trend[gid] + n_views[gid]) / 2, "outlier": r["outlier"],
                "freshness": r["freshness"], "competition": n_count[gid]}
        score = (WEIGHTS["demand"] * comp["demand"] + WEIGHTS["outlier"] * comp["outlier"]
                 + WEIGHTS["freshness"] * comp["freshness"] - WEIGHTS["competition"] * comp["competition"])
        g = by_game[gid]["game"]
        results.append({"game_id": gid, "game_zh": g["zh"], "game_ko": g["ko"], "score": round(score, 3),
                        "components": _round(comp), "videos_in_pool": r["count"],
                        "engagement_multiple": round(r["engagement_multiple"], 2),
                        "trending_weight": round(r["trend"], 2)})
    return sorted(results, key=lambda x: -x["score"])


def _round(d: Dict, nd: int = 4) -> Dict:
    return {k: (round(v, nd) if isinstance(v, float) else v) for k, v in d.items()}
