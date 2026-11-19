"""1단계 · 트렌드 수집.

소스 3가지 (결과 형식은 같다: runs/<id>/01_raw.json)
- api    : YouTube Data API v3 (공식 API, 키 필요). 인기 차트(게임 카테고리) + 키워드 검색 + 채널 통계
- file   : 다른 도구(vidIQ MCP, 수동 저장 등)로 모은 JSON 파일을 그대로 가져온다
- sample : data/sample/ 의 연습용 가짜 데이터 (실제 수치 아님, 테스트·연습 전용)

쿼터(하루 기본 10,000 units): videos.list/channels.list 1 unit, search.list 100 units.
키워드 2개 기준 한 번 수집 ≈ 200 + 5 units.
"""
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from .common import ROOT, load_config, load_env, now_iso, read_json, trace, write_stage

API = "https://www.googleapis.com/youtube/v3/"
SAMPLE = ROOT / "data" / "sample" / "youtube_sample.json"


class CollectError(RuntimeError):
    pass


def _get(endpoint: str, params: Dict, key: str) -> Dict:
    q = dict(params, key=key)
    url = API + endpoint + "?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            reason = json.loads(body)["error"]["message"]
        except Exception:
            reason = body[:200]
        # 키가 메시지에 섞여 나오지 않도록 지운다
        raise CollectError("YouTube API %s %s: %s" % (endpoint, e.code, reason.replace(key, "***")))
    except urllib.error.URLError as e:
        raise CollectError("네트워크 오류(%s): %s" % (endpoint, e.reason))


def _chunks(xs: List[str], n: int = 50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def collect_api(cfg: Dict, keywords: Optional[List[str]] = None) -> Dict:
    load_env()
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        raise CollectError("YOUTUBE_API_KEY 가 .env 에 없습니다. (.env.example 참고) 연습은 --source sample")
    c = cfg["collect"]
    gap = c.get("request_interval_sec", 0.5)
    keywords = keywords or c["search_keywords"]
    ids, signals = [], []

    # 1) 인기 차트 (게임 카테고리)
    pop = _get("videos", {"part": "id", "chart": "mostPopular", "regionCode": c["region_code"],
                          "videoCategoryId": c["category_id"], "maxResults": c["max_results"]}, key)
    for rank, it in enumerate(pop.get("items", []), 1):
        ids.append(it["id"])
        signals.append({"video_id": it["id"], "list": "mostPopular", "rank": rank})
    time.sleep(gap)

    # 2) 키워드 검색 (최근 N일, 조회수순, 4분 미만 영상)
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=c["search_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    for kw in keywords:
        res = _get("search", {"part": "id", "q": kw, "type": "video", "order": "viewCount",
                              "publishedAfter": after, "regionCode": c["region_code"],
                              "videoDuration": "short", "maxResults": c["max_results"]}, key)
        for rank, it in enumerate(res.get("items", []), 1):
            vid = it["id"]["videoId"]
            ids.append(vid)
            signals.append({"video_id": vid, "list": "search:" + kw, "rank": rank})
        time.sleep(gap)

    # 3) 영상 상세 (조회수·길이·태그)
    uniq = list(dict.fromkeys(ids))
    items = []
    for part in _chunks(uniq):
        res = _get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(part)}, key)
        items += res.get("items", [])
        time.sleep(gap)

    # 4) 채널 통계 (채널 평균 조회수 = 아웃라이어 배수의 기준)
    ch_ids = list(dict.fromkeys(it["snippet"]["channelId"] for it in items))
    channels = {}
    for part in _chunks(ch_ids):
        res = _get("channels", {"part": "statistics,snippet", "id": ",".join(part)}, key)
        for ch in res.get("items", []):
            channels[ch["id"]] = {"title": ch["snippet"].get("title", ""), **ch.get("statistics", {})}
        time.sleep(gap)

    return {"collected_at": now_iso(), "source": "api", "is_sample": False,
            "params": {"region": c["region_code"], "category": c["category_id"], "keywords": keywords,
                       "search_days": c["search_days"]},
            "items": items, "channels": channels, "list_signals": signals}


def collect_file(path: str) -> Dict:
    """다른 도구로 저장한 JSON 을 가져온다.

    허용 형식: (a) 이 파일과 같은 01_raw 형식 그대로  (b) {"items": [...]} 이고 각 item 이
    간단형 {video_id, title, channel_id, channel_title, views, likes, comments, duration_sec,
    published_at, tags?, channel_avg_views?} 인 경우.
    """
    data = read_json(Path(path))
    if isinstance(data, list):
        data = {"items": data}
    data.setdefault("collected_at", now_iso())
    data["source"] = "file:" + Path(path).name
    data.setdefault("is_sample", False)
    data.setdefault("channels", {})
    data.setdefault("list_signals", [])
    return data


def collect_sample() -> Dict:
    data = read_json(SAMPLE)
    data["source"] = "sample"
    data["is_sample"] = True
    return data


def run(run_id: str, source: str = "sample", path: Optional[str] = None,
        keywords: Optional[List[str]] = None) -> Dict:
    cfg = load_config()
    if source == "api":
        raw = collect_api(cfg, keywords)
    elif source == "file":
        if not path:
            raise CollectError("--source file 에는 --path 가 필요합니다")
        raw = collect_file(path)
    elif source == "sample":
        raw = collect_sample()
    else:
        raise CollectError("알 수 없는 source: %s" % source)
    write_stage(run_id, "raw", raw)
    msg = "%s: 영상 %d개, 채널 %d개" % (raw["source"], len(raw.get("items", [])), len(raw.get("channels", {})))
    trace(run_id, "collect", msg, is_sample=raw.get("is_sample", False))
    return {"run_id": run_id, "summary": msg, "is_sample": raw.get("is_sample", False)}
