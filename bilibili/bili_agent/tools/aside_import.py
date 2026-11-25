"""Aside 브라우저가 수집해 내보낸 CSV 를 읽는다 (수집 에이전트의 1순위 데이터).

왜 Aside 인가
- 빌리빌리 랭킹(ranking/v2)·영상 상세(view) API 는 일반 HTTP 요청에 봇 차단(-352 / 412)이 걸린다.
- Aside 는 사용자가 직접 쓰는 실제 브라우저라 페이지와 API 가 정상 동작하고, 랭킹·화제 태그·공식 활동까지 모은다.
- Aside 는 Python 에서 호출할 수 없으므로, Aside 가 만든 CSV 를 data/aside/ 에 두면 이 모듈이 읽는다.
  (팀 DB 13장 raw_snapshots.source 의 'aside' 값과 같은 의미)

파일 규칙 (data/aside/, 가장 최근 파일 사용)
- *videos*.csv          영상: bvid, 제목, 파티션, 길이, 게시 시각, 조회·좋아요·코인·즐겨찾기·공유·댓글·탄막, 태그
- *hot_keyword*.csv     핫키워드: 순위, 키워드, 열기
- *event*.csv           공식 활동/화제: 이름, id, 참여 영상 수, 조회수 합
- *performance*.csv     (성과 기록) bvid, 수집 시각, 조회·좋아요·코인·즐겨찾기·댓글

열 이름은 영어·한국어·중국어 어느 쪽이든 아래 별칭표로 맞춘다. 인코딩은 UTF-8(BOM) → GB18030 → CP949 순으로 시도한다.
"""
import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import config

# 표준 열 이름 → 허용하는 별칭 (소문자·공백 제거 후 비교)
COLUMNS = {
    "bvid": ["bvid", "bv", "bv号", "bv번호"],
    "title": ["title", "标题", "제목", "영상제목"],
    "partition": ["pid_name_v2", "partition", "分区", "파티션", "카테고리", "대분류"],
    "tname": ["tnamev2", "tname", "子分区", "세부파티션", "소분류"],
    "author": ["owner", "owner_name", "author", "up主", "up", "작성자", "업로더"],
    "duration_sec": ["duration", "duration_sec", "时长(秒)", "时长", "길이(초)", "길이초", "길이"],
    "pubdate": ["pubdate", "published_at", "发布时间", "게시일", "게시시각", "업로드시각"],
    "view": ["view", "views", "播放", "播放量", "조회수", "조회"],
    "like": ["like", "likes", "点赞", "좋아요"],
    "coin": ["coin", "coins", "投币", "코인"],
    "favorite": ["favorite", "favorites", "收藏", "즐겨찾기"],
    "share": ["share", "shares", "分享", "공유"],
    "reply": ["reply", "replies", "comments", "评论", "댓글"],
    "danmaku": ["danmaku", "弹幕", "탄막"],
    "tags": ["topics", "tags", "话题", "标签", "태그", "화제"],
    "rank": ["rank", "排名", "순위"],
    "source": ["source", "来源", "출처", "수집출처"],
    "mission_id": ["mission_id", "활동id"],
    # 핫키워드
    "keyword": ["keyword", "关键词", "热词", "키워드", "핫키워드"],
    "heat": ["heat", "heat_score", "热度", "열기", "인기도"],
    # 이벤트
    "event_name": ["topic_name", "event", "event_name", "活动", "话题名", "이벤트", "화제명", "토픽명"],
    "event_id": ["topic_id", "event_id", "活动id", "话题id", "토픽id", "이벤트id"],
    "event_videos": ["videos", "video_count", "참여영상수", "참여영상", "인기영상내참여영상수"],
    "event_views": ["total_view", "views_sum", "조회수합", "총조회수"],
    # 성과
    "collected_at": ["collected_at", "at", "수집시각", "采集时间"],
}
GAME_PARTITIONS = {"游戏", "게임", "game", "games"}
ENCODINGS = ("utf-8-sig", "gb18030", "cp949")


class AsideImportError(RuntimeError):
    pass


def _key(s: str) -> str:
    return "".join((s or "").lower().split()).replace("_", "") if s else ""


_ALIAS = {_key(a): std for std, aliases in COLUMNS.items() for a in aliases}


def _decode(raw: bytes) -> Tuple[str, str]:
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if "�" not in text:
            return text, enc
    raise AsideImportError("인코딩을 읽을 수 없습니다(UTF-8/GB18030/CP949 모두 실패). Aside 에 UTF-8 로 다시 저장해 달라고 요청하세요.")


def read_csv(path: Path) -> Dict:
    text, enc = _decode(path.read_bytes())
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    mapping = {h: _ALIAS.get(_key(h)) for h in header}
    rows = [{mapping[h]: (v or "").strip() for h, v in r.items() if h in mapping and mapping[h]} for r in reader]
    return {"file": path.name, "encoding": enc, "rows": rows, "header": header,
            "unmapped": [h for h, m in mapping.items() if not m],
            "age_h": (time.time() - path.stat().st_mtime) / 3600}


def _num(v: str) -> int:
    """'1.2万', '3,456', '1.17641E+14' 같은 표기도 정수로."""
    if not v:
        return 0
    v = v.replace(",", "").strip()
    mult = 1
    if v.endswith("万") or v.endswith("만"):
        mult, v = 10000, v[:-1]
    elif v.endswith("亿") or v.endswith("억"):
        mult, v = 100000000, v[:-1]
    try:
        return int(float(v) * mult)
    except ValueError:
        return 0


def _duration(v: str) -> int:
    if ":" in (v or ""):
        parts = [int(p) for p in v.split(":") if p.isdigit()]
        sec = 0
        for p in parts:
            sec = sec * 60 + p
        return sec
    return _num(v)


def _epoch(v: str) -> Optional[float]:
    if not v:
        return None
    if v.isdigit():
        return float(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(v[:19], fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _latest(pattern: str) -> Optional[Path]:
    files = sorted(config.ASIDE_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _latest_json() -> Optional[Path]:
    files = sorted(config.ASIDE_DIR.glob("bilibili_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _local_ts(s: str) -> Optional[float]:
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").timestamp()  # Aside crawled_at: 로컬 시각
    except (ValueError, TypeError):
        return None


def load_json() -> Optional[Dict]:
    """Aside 크롤러 JSON (bilibili_YYYY-MM-DD.json) → 영상·핫키워드·공식 활동.

    형식: {crawled_at, scope, hot_keywords:[{rank,keyword,heat_score,is_game}],
           videos:[{bvid,title,owner,category,source,pubdate,event_radar:{view,like,coin,favorite,share,reply,danmaku},
                    official_event:{mission_id,event_tags[]}, tags[]}]}
    반응률·제목 진단 같은 Aside 계산값은 쓰지 않고 원본 수치로 다시 계산한다(공식이 다름: Aside 는 댓글 포함).
    """
    path = _latest_json()
    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    crawled = _local_ts(raw.get("crawled_at", ""))
    age_h = (time.time() - (crawled or path.stat().st_mtime)) / 3600
    videos, events = [], {}
    for v in raw.get("videos", []):
        st = v.get("event_radar") or {}
        oe = v.get("official_event") or {}
        videos.append({
            "bvid": v["bvid"], "title": v.get("title", ""), "tid": None, "tname": v.get("category"),
            "tname_v2": v.get("category"), "pubdate": _epoch(v.get("pubdate", "")), "duration_sec": None,
            "view": int(st.get("view") or 0), "like": int(st.get("like") or 0), "coin": int(st.get("coin") or 0),
            "favorite": int(st.get("favorite") or 0), "share": int(st.get("share") or 0),
            "reply": int(st.get("reply") or 0), "danmaku": int(st.get("danmaku") or 0),
            "author": v.get("owner"), "mission_id": oe.get("mission_id") or None,
            "event_tags": list(oe.get("event_tags") or []), "tags": list(v.get("tags") or []),
            "rank": None, "source": "aside:" + (v.get("source") or "videos")})
        for tag in oe.get("event_tags") or []:
            e = events.setdefault(tag, {"name": tag, "event_id": oe.get("mission_id") or "", "videos": 0, "total_view": 0})
            e["videos"] += 1
            e["total_view"] += int(st.get("view") or 0)
    kws = [{"keyword": k["keyword"], "show_name": k["keyword"], "heat_score": k.get("heat_score", 0),
            "rank": k.get("rank") or i + 1, "aside_is_game": k.get("is_game")}
           for i, k in enumerate(raw.get("hot_keywords", [])) if k.get("keyword")]
    return {"videos": videos, "keywords": kws, "events": sorted(events.values(), key=lambda e: -e["total_view"]),
            "origin": "aside", "file": path.name, "age_h": round(age_h, 1), "crawled_at": raw.get("crawled_at"),
            "scope": raw.get("scope"), "endpoint": "aside:" + path.name, "encoding": "utf-8",
            "rows_total": len(videos), "rows_non_game": 0, "partition_known": True, "unmapped_columns": []}


def load_videos(game_only: bool = True) -> Optional[Dict]:
    """Aside 영상 CSV → 공통 영상 레코드(bilibili_api.normalize_video 와 같은 키). 파일이 없으면 None."""
    path = _latest("*videos*.csv")
    if path is None:
        return None
    data = read_csv(path)
    if not data["rows"] or "bvid" not in data["rows"][0]:
        raise AsideImportError("%s: bvid 열을 찾지 못했습니다. 열 이름: %s" % (path.name, data["header"][:12]))
    videos, skipped = [], 0
    for r in data["rows"]:
        part = r.get("partition", "")
        if game_only and part and part.lower() not in GAME_PARTITIONS:
            skipped += 1
            continue
        tags = [t.strip() for t in r.get("tags", "").replace("，", "|").replace(",", "|").split("|") if t.strip()]
        videos.append({
            "bvid": r["bvid"], "title": r.get("title", ""), "tid": None, "tname": r.get("tname"),
            "tname_v2": r.get("tname"), "pubdate": _epoch(r.get("pubdate", "")),
            "duration_sec": _duration(r.get("duration_sec", "")),
            "view": _num(r.get("view")), "like": _num(r.get("like")), "coin": _num(r.get("coin")),
            "favorite": _num(r.get("favorite")), "share": _num(r.get("share")), "reply": _num(r.get("reply")),
            "danmaku": _num(r.get("danmaku")), "author": r.get("author"),
            "mission_id": _num(r.get("mission_id")) or None, "tags": tags,
            "rank": _num(r.get("rank")) or None, "source": "aside:" + (r.get("source") or "videos"),
        })
    return {"videos": videos, "origin": "aside", "file": data["file"], "encoding": data["encoding"],
            "age_h": round(data["age_h"], 1), "rows_total": len(data["rows"]), "rows_non_game": skipped,
            "partition_known": any(r.get("partition") for r in data["rows"]),
            "unmapped_columns": data["unmapped"], "endpoint": "aside:" + data["file"]}


def load_keywords() -> Optional[Dict]:
    path = _latest("*hot_keyword*.csv")
    if path is None:
        return None
    data = read_csv(path)
    kws = []
    for i, r in enumerate(data["rows"]):
        if r.get("keyword"):
            kws.append({"keyword": r["keyword"], "show_name": r["keyword"], "heat_score": _num(r.get("heat")),
                        "rank": _num(r.get("rank")) or i + 1})
    kws.sort(key=lambda k: k["rank"])
    return {"keywords": kws, "origin": "aside", "file": data["file"], "age_h": round(data["age_h"], 1),
            "endpoint": "aside:" + data["file"]}


def load_events() -> Optional[Dict]:
    path = _latest("*event*.csv")
    if path is None:
        return None
    data = read_csv(path)
    events = [{"name": r.get("event_name", ""), "event_id": r.get("event_id", ""),
               "videos": _num(r.get("event_videos")), "total_view": _num(r.get("event_views"))}
              for r in data["rows"] if r.get("event_name")]
    events.sort(key=lambda e: -e["total_view"])
    return {"events": events, "origin": "aside", "file": data["file"], "age_h": round(data["age_h"], 1)}


def load_performance() -> Optional[Dict]:
    path = _latest("*performance*.csv")
    if path is None:
        return None
    data = read_csv(path)
    rows = [{"bvid": r["bvid"], "at": r.get("collected_at", ""), "view": _num(r.get("view")),
             "like": _num(r.get("like")), "coin": _num(r.get("coin")), "favorite": _num(r.get("favorite")),
             "reply": _num(r.get("reply"))} for r in data["rows"] if r.get("bvid")]
    return {"rows": rows, "origin": "aside", "file": data["file"]}
