"""에이전트 2 · 정규화 (기획안 12장 '2 정규화')

코드(pre_run): 중복 제거, 게시 MAX_VIDEO_AGE_DAYS(기본 30일) 넘은 영상 제외, 제목·화제 태그로 game_id 부여(별칭 사전).
LLM: 별칭 사전에 없는 게임 이름을 찾아 '별칭 후보'로 제안 (사람 검토 후 game_aliases 에 반영).
DB(13장): videos, game_aliases(후보)
"""
import time
from typing import Dict

from ... import config
from ...workspace import Workspace
from ..base import STR_LIST, WorkerSpec, submit, tool


def normalize_pool(ws: Workspace) -> Dict:
    seen, videos, matched = set(), [], 0
    limit, now = config.MAX_VIDEO_AGE_DAYS * 86400, time.time()
    old_by_source: Dict[str, int] = {}
    for v in ws.raw_videos:
        if v["bvid"] in seen:
            continue
        seen.add(v["bvid"])
        if v.get("pubdate") and now - v["pubdate"] > limit:  # 지금의 트렌드가 아닌 오래된 영상
            old_by_source[v.get("source", "?")] = old_by_source.get(v.get("source", "?"), 0) + 1
            continue
        text = v["title"] + " " + " ".join(v.get("tags") or [])
        ids = [g["game_id"] for g in ws.alias.find_in_text(text)]
        videos.append(dict(v, game_ids=ids))
        matched += bool(ids)
    ws.videos, ws.normalized = videos, True
    req = ws.requested_game
    n_old = sum(old_by_source.values())
    result = {"videos": len(videos), "matched_to_game": matched, "unmatched": len(videos) - matched,
              "old_videos_dropped": n_old, "old_by_source": old_by_source,
              "max_video_age_days": config.MAX_VIDEO_AGE_DAYS,
              "duplicates_removed": len(ws.raw_videos) - len(videos) - n_old,
              "videos_for_requested_game": len(ws.videos_for(req["game_id"])) if req else None}
    ws.cache["normalize"] = result
    return result


def h_resolve_game(ws: Workspace, name: str) -> Dict:
    g = ws.alias.resolve(name) or next(iter(ws.alias.find_in_text(name)), None)
    if not g:
        return {"found": False, "name": name}
    return {"found": True, "game_id": g["game_id"], "zh": g["zh"], "ko": g["ko"], "en": g["en"]}


def h_list_unmatched_titles(ws: Workspace, n: int = 20) -> Dict:
    rows = [{"title": v["title"], "tags": (v.get("tags") or [])[:5], "tname": v.get("tname_v2") or v.get("tname"),
             "view": v["view"]} for v in ws.videos if not v.get("game_ids")]
    rows.sort(key=lambda r: -r["view"])
    return {"unmatched": len(rows), "pool_size": len(ws.videos), "titles": rows[:n]}


SPEC = WorkerSpec(
    name="normalizer", stage="2 정규화", db_tables=["videos", "game_aliases"], prompt_file="w2_normalizer.md",
    requires="collector", pre_run=normalize_pool,
    tools=[tool("list_unmatched_titles", "게임을 찾지 못한 영상(제목·화제 태그, 조회수 순).",
                {"n": {"type": "integer", "description": "개수(기본 20)"}}),
           tool("resolve_game", "게임 이름(한·중·영)을 별칭 사전으로 표준화.", {"name": {"type": "string"}}, ["name"])],
    handlers={"list_unmatched_titles": h_list_unmatched_titles, "resolve_game": h_resolve_game},
    submit_tool=submit({
        "alias_candidates": {"type": "array", "description": "별칭 사전 추가 제안(사람 검토 후 반영)", "items": {
            "type": "object", "properties": {"zh": {"type": "string"}, "ko": {"type": "string"},
                                             "en": {"type": "string"}, "aliases": STR_LIST,
                                             "evidence_title": {"type": "string"}},
            "required": ["zh", "evidence_title"]}},
        "data_quality_notes": STR_LIST}, ["alias_candidates"]),
)
