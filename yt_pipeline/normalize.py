"""2단계 · 정규화.

API 응답이든 다른 도구에서 가져온 간단형이든 한 가지 영상 레코드로 맞춘다.
- 길이(ISO 8601 → 초), 쇼츠 여부, 게시 후 경과 시간
- 주제(게임) 통일: 별칭 사전으로 한·영 표기를 topic_id 하나로
- 채널 평균 조회수 대비 배수(아웃라이어 배수), 시간당 조회수, 반응률
- 사전에 없는 반복 단어는 alias_candidates 로 제안(사람이 검토 후 사전에 추가)
"""
import collections
import datetime as dt
import re
from typing import Dict, List, Optional

from .common import load_config, now_iso, read_stage, trace, write_stage

_DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def iso_duration_sec(s: str) -> int:
    m = _DUR.fullmatch(s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


class AliasStore:
    def __init__(self, data: Optional[Dict] = None):
        data = data or load_config("alias_dictionary.json")
        self.topics = data["topics"]
        self.generic = {_squash(w) for w in data.get("generic_words", [])}
        self._pairs = []  # (squashed alias, topic) — 긴 별칭부터 검사
        for t in self.topics:
            for a in set(t["aliases"] + [t["name_en"], t["name_ko"]]):
                self._pairs.append((_squash(a), t))
        self._pairs.sort(key=lambda p: -len(p[0]))

    def find(self, text: str) -> List[Dict]:
        s = _squash(text)
        found = {}
        for a, t in self._pairs:
            if a and a in s:
                found[t["topic_id"]] = t
        return list(found.values())

    def get(self, topic_id: str) -> Dict:
        for t in self.topics:
            if t["topic_id"] == topic_id:
                return t
        return {"topic_id": topic_id, "name_en": topic_id, "name_ko": topic_id, "aliases": []}


def _hours_since(iso: str, now: dt.datetime) -> float:
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return 0.0
    return max((now - t).total_seconds() / 3600, 0.0)


def _from_api(it: Dict, channels: Dict) -> Dict:
    sn, st, cd = it.get("snippet", {}), it.get("statistics", {}), it.get("contentDetails", {})
    ch = channels.get(sn.get("channelId"), {})
    ch_views, ch_count = int(ch.get("viewCount", 0) or 0), int(ch.get("videoCount", 0) or 0)
    return {"video_id": it["id"], "title": sn.get("title", ""), "channel_id": sn.get("channelId", ""),
            "channel_title": sn.get("channelTitle", ""), "published_at": sn.get("publishedAt", ""),
            "views": int(st.get("viewCount", 0) or 0), "likes": int(st.get("likeCount", 0) or 0),
            "comments": int(st.get("commentCount", 0) or 0),
            "duration_sec": iso_duration_sec(cd.get("duration", "")), "tags": sn.get("tags", []) or [],
            "channel_subscribers": int(ch.get("subscriberCount", 0) or 0),
            "channel_avg_views": (ch_views / ch_count) if ch_count else None}


def _from_simple(it: Dict) -> Dict:
    return {"video_id": it["video_id"], "title": it.get("title", ""), "channel_id": it.get("channel_id", ""),
            "channel_title": it.get("channel_title", ""), "published_at": it.get("published_at", ""),
            "views": int(it.get("views", 0)), "likes": int(it.get("likes", 0)), "comments": int(it.get("comments", 0)),
            "duration_sec": int(it.get("duration_sec", 0)), "tags": it.get("tags", []) or [],
            "channel_subscribers": int(it.get("channel_subscribers", 0) or 0),
            "channel_avg_views": it.get("channel_avg_views")}


def normalize(raw: Dict, alias: AliasStore, cfg: Dict, now: Optional[dt.datetime] = None) -> Dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    if raw.get("reference_now"):  # 샘플 데이터는 고정 시각 기준으로 계산해야 결과가 재현된다
        now = dt.datetime.fromisoformat(raw["reference_now"].replace("Z", "+00:00"))
    ncfg = cfg["normalize"]
    lists = collections.defaultdict(list)
    for s in raw.get("list_signals", []):
        lists[s["video_id"]].append({"list": s["list"], "rank": s["rank"]})

    videos, seen, dropped = [], set(), collections.Counter()
    for it in raw.get("items", []):
        v = _from_api(it, raw.get("channels", {})) if "snippet" in it else _from_simple(it)
        if v["video_id"] in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(v["video_id"])
        if v["views"] < ncfg["min_views"]:
            dropped["low_views"] += 1
            continue
        age = _hours_since(v["published_at"], now)
        topics = alias.find(v["title"] + " " + " ".join(v["tags"]))
        avg = v["channel_avg_views"]
        v.update({
            "url": "https://www.youtube.com/watch?v=" + v["video_id"],
            "is_short": 0 < v["duration_sec"] <= ncfg["shorts_max_sec"],
            "age_h": round(age, 1),
            "views_per_hour": round(v["views"] / max(age, 1.0), 1),
            "engagement_rate": round((v["likes"] + v["comments"]) / max(v["views"], 1), 4),
            "outlier_multiple": round(v["views"] / avg, 2) if avg else None,
            "topics": [t["topic_id"] for t in topics],
            "lists": lists.get(v["video_id"], []),
        })
        videos.append(v)

    return {"normalized_at": now_iso(), "source": raw.get("source"), "is_sample": raw.get("is_sample", False),
            "reference_now": now.isoformat(), "videos": videos,
            "dropped": dict(dropped), "alias_candidates": alias_candidates(videos, alias)}


_TOKEN = re.compile(r"[#]?[A-Za-z][A-Za-z0-9']+(?:\s[A-Za-z][A-Za-z0-9']+){0,2}|[#]?[가-힣]{2,}(?:\s?[가-힣0-9]{1,})?")


def alias_candidates(videos: List[Dict], alias: AliasStore, min_count: int = 2) -> List[Dict]:
    """주제를 못 찾은 영상 제목에서 반복되는 단어를 모은다. 자동으로 사전에 넣지 않는다."""
    cnt, examples = collections.Counter(), collections.defaultdict(list)
    for v in videos:
        if v["topics"]:
            continue
        toks = {t.strip("#").strip() for t in _TOKEN.findall(v["title"])}
        for t in toks:
            if len(t) < 2 or _squash(t) in alias.generic:
                continue
            cnt[t] += 1
            if len(examples[t]) < 2:
                examples[t].append(v["title"])
    return [{"text": t, "count": n, "examples": examples[t]} for t, n in cnt.most_common(15) if n >= min_count]


def run(run_id: str) -> Dict:
    cfg = load_config()
    raw = read_stage(run_id, "raw")
    out = normalize(raw, AliasStore(), cfg)
    write_stage(run_id, "normalized", out)
    vs = out["videos"]
    matched = sum(1 for v in vs if v["topics"])
    msg = "영상 %d개 (쇼츠 %d, 주제 매칭 %d), 제외 %s, 별칭 후보 %d" % (
        len(vs), sum(v["is_short"] for v in vs), matched, out["dropped"], len(out["alias_candidates"]))
    trace(run_id, "normalize", msg)
    return {"run_id": run_id, "summary": msg}
