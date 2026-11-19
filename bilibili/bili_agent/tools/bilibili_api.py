"""빌리빌리 데이터 수집 도구 (결정적 코드, LLM 없음).

원칙
- 로그인·쿠키 위조·서명 우회 없이 '공개적으로 열려 있는' 엔드포인트만 호출한다.
- 요청 사이에 REQUEST_INTERVAL 초 간격을 둔다(기획안 리스크 매트릭스: 요청 빈도 제한).
- 실시간 호출이 실패하면 data/snapshots/ 의 스냅샷으로 대체하고, 출처를 'snapshot'으로 기록한다.

사용 엔드포인트 (2026-11-16 실측)
- 종합 인기   /x/web-interface/popular            ✅ 실시간, 게임 카테고리(pid_v2=1008) 필터링
- 실시간 핫서치 /x/web-interface/wbi/search/square ✅ 실시간
- 게임 카테고리 랭킹 /x/web-interface/ranking/v2?rid=4  ❌ -352 (봇 차단) → 사람이 브라우저로 저장한
                                                     ranking_game_*.json 스냅샷만 읽는다
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import config

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular?ps=50&pn={page}"
TRENDING_URL = "https://api.bilibili.com/x/web-interface/wbi/search/square?limit=30"

GAME_PID_V2 = 1008  # 신 카테고리 체계의 '游戏'
GAME_TIDS_V1 = {4, 17, 19, 65, 121, 136, 171, 172, 173}  # 구 카테고리 체계의 게임 하위 카테고리

_last_request_at = 0.0


class BiliFetchError(RuntimeError):
    pass


def _get_json(url: str) -> Dict[str, Any]:
    global _last_request_at
    wait = config.REQUEST_INTERVAL - (time.time() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as exc:
        raise BiliFetchError("%s: %s" % (url, exc))
    finally:
        _last_request_at = time.time()
    if payload.get("code") != 0:
        raise BiliFetchError("%s: code=%s message=%s" % (url, payload.get("code"), payload.get("message")))
    return payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_video(raw: Dict[str, Any], source: str) -> Dict[str, Any]:
    """popular / ranking/v2 응답의 영상 항목을 공통 형태로 정규화."""
    stat = raw.get("stat", {})
    return {
        "bvid": raw.get("bvid"),
        "title": raw.get("title", ""),
        "tid": raw.get("tid"),
        "tname": raw.get("tname"),
        "tname_v2": raw.get("tnamev2"),
        "pubdate": raw.get("pubdate"),
        "duration_sec": raw.get("duration"),
        "view": stat.get("view", 0),
        "like": stat.get("like", 0),
        "coin": stat.get("coin", 0),
        "favorite": stat.get("favorite", 0),
        "share": stat.get("share", 0),
        "reply": stat.get("reply", 0),
        "danmaku": stat.get("danmaku", 0),
        "author": (raw.get("owner") or {}).get("name"),
        # mission_id 가 있으면 공식 활동(이벤트)에 참여한 영상
        "mission_id": raw.get("mission_id") or None,
        "source": source,
    }


def is_game_video(raw: Dict[str, Any]) -> bool:
    return raw.get("pid_v2") == GAME_PID_V2 or raw.get("tid") in GAME_TIDS_V1


# ── 스냅샷 ───────────────────────────────────────────────

def _latest_snapshot(prefix: str) -> Optional[Tuple[str, Any]]:
    files = sorted(config.SNAPSHOT_DIR.glob(prefix + "*.json"))
    if not files:
        return None
    path = files[-1]
    with open(path, encoding="utf-8") as f:
        return path.name, json.load(f)


def save_snapshot(name: str, data: Any) -> str:
    config.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.SNAPSHOT_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return str(path)


# ── 공개 수집 함수 ────────────────────────────────────────

def fetch_popular_game_videos(pages: Optional[int] = None) -> Dict[str, Any]:
    """종합 인기에서 게임 카테고리 영상만 골라 반환. 실패 시 스냅샷."""
    pages = pages or config.POPULAR_PAGES
    if not config.OFFLINE:
        try:
            videos = []
            for page in range(1, pages + 1):
                data = _get_json(POPULAR_URL.format(page=page))["data"]
                videos += [normalize_video(v, "popular") for v in data["list"] if is_game_video(v)]
                if data.get("no_more"):
                    break
            return {"videos": videos, "origin": "live", "fetched_at": _now_iso(),
                    "endpoint": "x/web-interface/popular", "pages": pages}
        except BiliFetchError as exc:
            error = str(exc)
    else:
        error = "BILI_OFFLINE=1"
    snap = _latest_snapshot("popular_game_")
    if snap is None:
        raise BiliFetchError("실시간 수집 실패, 스냅샷도 없음: %s" % error)
    name, data = snap
    data = dict(data, origin="snapshot", snapshot_file=name, live_error=error)
    return data


def fetch_trending_keywords() -> Dict[str, Any]:
    """실시간 핫서치(热搜) 키워드. 실패 시 스냅샷."""
    if not config.OFFLINE:
        try:
            items = _get_json(TRENDING_URL)["data"]["trending"]["list"]
            keywords = [{"keyword": i.get("keyword"), "show_name": i.get("show_name"),
                         "heat_score": i.get("heat_score", 0), "rank": n + 1}
                        for n, i in enumerate(items)]
            return {"keywords": keywords, "origin": "live", "fetched_at": _now_iso(),
                    "endpoint": "x/web-interface/wbi/search/square"}
        except BiliFetchError as exc:
            error = str(exc)
    else:
        error = "BILI_OFFLINE=1"
    snap = _latest_snapshot("trending_")
    if snap is None:
        raise BiliFetchError("핫서치 수집 실패, 스냅샷도 없음: %s" % error)
    name, data = snap
    return dict(data, origin="snapshot", snapshot_file=name, live_error=error)


def load_ranking_snapshot() -> Optional[Dict[str, Any]]:
    """사람이 브라우저로 저장한 게임 카테고리 랭킹(ranking/v2?rid=4) 원본 JSON을 읽는다.

    파일명: data/snapshots/ranking_game_YYYYMMDD.json (가장 최신 날짜 사용)
    저장 방법은 README '랭킹 스냅샷 저장' 참고. 파일이 없으면 None.
    """
    snap = _latest_snapshot("ranking_game_")
    if snap is None:
        return None
    name, raw = snap
    if raw.get("code") not in (0, None):
        return {"videos": [], "origin": "snapshot", "snapshot_file": name,
                "error": "저장된 파일이 정상 응답이 아님(code=%s)" % raw.get("code")}
    items = (raw.get("data") or {}).get("list", [])
    return {"videos": [normalize_video(v, "ranking_v2") for v in items], "origin": "snapshot",
            "snapshot_file": name, "endpoint": "x/web-interface/ranking/v2?rid=4"}
