"""오프라인 테스트 (네트워크·API 키 불필요): 지표 계산, Aside CSV, 정규화·점수화, 성과 보정, 팀 DB 행."""
import json
import time

import pytest

from bili_agent import config
from bili_agent.agents.supervisor import BiliSupervisor
from bili_agent.agents.workers import WORKERS
from bili_agent.agents.workers import w6_performance as perf
from bili_agent.contracts import BiliTask
from bili_agent.tools import aside_import, bilibili_api, metrics, team_db
from bili_agent.tools.alias_store import AliasStore

NOW = time.time()


def video(bvid, title, view, coin=0, fav=0, like=0, share=0, dur=300, hours_ago=10, mission=None, tags=None):
    return {"bvid": bvid, "title": title, "tid": 172, "tname": "手机游戏", "pubdate": NOW - hours_ago * 3600,
            "duration_sec": dur, "view": view, "like": like, "coin": coin, "favorite": fav, "share": share,
            "reply": 3, "danmaku": 0, "author": "x", "mission_id": mission, "tags": tags or [], "source": "test"}


VIDEOS = [
    video("BV1", "【原神】新版本角色攻略 平民配队", 100000, coin=2000, fav=3000, like=5000, share=100, mission=11),
    video("BV2", "《明日方舟》TL-S-4 平民单核", 50000, coin=5000, fav=4000, like=6000, share=300, dur=700),
    video("BV3", "BLG夺冠！S16决赛赛后数据", 900000, coin=10000, fav=8000, like=30000, share=2000, dur=200),
    video("BV4", "实况 第一视角 全流程", 30000, coin=100, fav=200, like=800, share=10, dur=2400, tags=["原神"]),
    video("BV5", "某个没收录的新游戏 PV", 20000, coin=50, fav=60, like=300, share=5, dur=90),
]
KEYWORDS = [{"keyword": "原神新角色", "rank": 3, "heat_score": 1}, {"keyword": "三角洲行动新赛季", "rank": 8, "heat_score": 1},
            {"keyword": "今日天气", "rank": 1, "heat_score": 1}]


@pytest.fixture
def alias():
    return AliasStore.load()


@pytest.fixture
def no_net(monkeypatch, tmp_path):
    """네트워크·실제 데이터 폴더를 쓰지 않도록 격리."""
    monkeypatch.setattr(config, "ASIDE_DIR", tmp_path / "aside")
    monkeypatch.setattr(config, "PERFORMANCE_DIR", tmp_path / "performance")
    monkeypatch.setattr(bilibili_api, "fetch_popular_game_videos",
                        lambda pages=None: {"videos": [dict(v) for v in VIDEOS], "origin": "live"})
    monkeypatch.setattr(bilibili_api, "fetch_trending_keywords", lambda: {"keywords": KEYWORDS, "origin": "live"})
    monkeypatch.setattr(bilibili_api, "load_ranking_snapshot", lambda: None)
    return tmp_path


# ── 지표 ────────────────────────────────────────────────

def test_alias_resolve_all_scripts(alias):
    assert alias.resolve("원신")["game_id"] == "genshin_impact"
    assert [g["game_id"] for g in alias.find_in_text("BLG夺冠！S16决赛")] == ["league_of_legends"]


def test_longer_alias_wins(alias):
    # 2026-11-25 Aside 재수집: '明日方舟：终末地'(엔드필드)가 '明日方舟'(명일방주)로도 세지던 문제
    assert [g["game_id"] for g in alias.find_in_text("《明日方舟：终末地》小刻EP 明日方舟终末地")] == ["arknights_endfield"]
    assert [g["game_id"] for g in alias.find_in_text("明日方舟 斗蛐蛐")] == ["arknights"]
    assert alias.find_in_text("IMC大赛") == []  # 짧은 영문 별칭 'MC' 는 단어 경계가 있어야


def test_engagement_distribution_title():
    r = metrics.rank_by_engagement(VIDEOS, top=5)
    assert r["top"][0]["bvid"] == "BV2" and r["top"][0]["engagement_multiple"] > 1
    d = metrics.duration_and_type_distribution(VIDEOS)
    assert sum(b["count"] for b in d["duration_buckets"]) == len(VIDEOS)
    diag = metrics.diagnose_title("【攻略】原神新角色", metrics.title_benchmark(VIDEOS))
    assert diag["features"]["square_brackets"] == 1


def test_unknown_duration_not_counted_as_zero():
    vids = [dict(v, duration_sec=None) for v in VIDEOS[:3]] + VIDEOS[3:]
    d = metrics.duration_and_type_distribution(vids)
    assert d["videos_without_duration"] == 3 and d["videos_with_duration"] == 2
    assert d["duration_buckets"][0]["count"] == 0          # '1분 미만' 에 길이 모르는 영상이 들어가지 않음
    assert sum(b["count"] for b in d["duration_buckets"]) == 2


def test_scores_include_leading_signal_game(alias):
    ids = [s["game_id"] for s in metrics.score_games(VIDEOS, KEYWORDS, alias, now=NOW)]
    assert "delta_force" in ids  # 핫키워드에만 있고 영상은 없는 게임도 후보
    assert any(s["game_id"] == "delta_force" and s["leading_signal"]
               for s in metrics.hot_keyword_signals(KEYWORDS, VIDEOS, alias))


# ── Aside CSV ──────────────────────────────────────────

ASIDE_HEADER = "bvid,aid,제목,파티션,세부파티션,길이(초),게시일,조회수,좋아요,코인,즐겨찾기,공유,댓글,탄막,태그\n"
ASIDE_ROWS = [
    "BVa1,1.17641E+14,【原神】5.5版本前瞻解读,游戏,手机游戏,412,2026-11-18 10:00:00,1.2万,800,300,500,40,90,120,原神|版本更新\n",
    "BVa2,1.17636E+14,咸猫原创编舞,舞蹈,宅舞,200,2026-11-18 11:00:00,50000,3000,900,1200,100,80,30,舞蹈\n",
    "BVa3,1.17626E+14,第一次在B站发视频,游戏,单机游戏,95,2026-11-18 12:00:00,\"3,456\",100,10,20,1,5,2,我的世界\n",
]


def write_aside(dirpath, name, text, enc="utf-8-sig"):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_bytes(text.encode(enc))


@pytest.mark.parametrize("enc", ["utf-8-sig", "gb18030"])
def test_aside_videos_korean_header_and_encoding(no_net, enc):
    if enc == "gb18030":  # GB18030 은 한글 열 이름을 담을 수 없어 중국어 열 이름으로
        header = "BV号,标题,分区,子分区,时长,发布时间,播放,点赞,投币,收藏,分享,评论,弹幕,话题\n"
        rows = ["BVa1,【原神】5.5版本前瞻解读,游戏,手机游戏,6:52,2026-11-18 10:00:00,1.2万,800,300,500,40,90,120,原神|版本更新\n",
                "BVa2,咸猫原创编舞,舞蹈,宅舞,3:20,2026-11-18 11:00:00,50000,3000,900,1200,100,80,30,舞蹈\n"]
    else:
        header, rows = ASIDE_HEADER, ASIDE_ROWS
    write_aside(config.ASIDE_DIR, "bilibili_videos_반응률.csv", header + "".join(rows), enc)
    d = aside_import.load_videos()
    assert d["encoding"] == enc and d["rows_non_game"] == 1          # 게임 외(舞蹈) 제외
    v = d["videos"][0]
    assert v["bvid"] == "BVa1" and v["view"] == 12000 and v["coin"] == 300 and v["duration_sec"] == 412
    assert v["tags"] == ["原神", "版本更新"] and v["pubdate"] is not None


def test_collector_prefers_fresh_aside_and_falls_back_when_stale(no_net, alias, monkeypatch):
    monkeypatch.setattr(config, "MIN_FRESH_VIDEOS", 1)  # 신선한 영상 수 기준을 낮춰 '보충 없음' 경우를 본다
    write_aside(config.ASIDE_DIR, "bilibili_videos.csv", ASIDE_HEADER + "".join(ASIDE_ROWS))
    write_aside(config.ASIDE_DIR, "bilibili_hot_keywords.csv", "순위,키워드,열기\n1,原神新角色,900\n2,三角洲行动,800\n")
    write_aside(config.ASIDE_DIR, "bilibili_events.csv", "화제명,토픽id,참여영상수,조회수합\n原神5.5版本创作激励,77,12,340000\n")
    rep = BiliSupervisor(alias_store=alias).run_dry(BiliTask(intent="trend_scan")).to_dict()
    assert [s["name"] for s in rep["data_sources"]][:3] == ["Aside 영상", "Aside 핫키워드", "Aside 공식 활동·화제"]
    assert not any("종합 인기" in s["name"] for s in rep["data_sources"])  # 신선한 Aside 영상이 있으면 영상 API 안 씀
    assert any("핫서치" in s["name"] for s in rep["data_sources"])         # Aside 핫키워드 2개뿐 → 핫서치로 보충
    monkeypatch.setattr(config, "ASIDE_MAX_AGE_H", -1)                      # 모든 파일을 '오래됨'으로
    rep = BiliSupervisor(alias_store=alias).run_dry(BiliTask(intent="trend_scan")).to_dict()
    assert any("공개 API" in s["name"] for s in rep["data_sources"])


def test_aside_event_bonus_in_scorer(no_net, alias, monkeypatch):
    monkeypatch.setattr(config, "MIN_FRESH_VIDEOS", 1)
    write_aside(config.ASIDE_DIR, "bilibili_videos.csv", ASIDE_HEADER + "".join(ASIDE_ROWS))
    write_aside(config.ASIDE_DIR, "bilibili_events.csv", "화제명,토픽id,참여영상수,조회수합\n原神5.5版本创作激励,77,12,340000\n")
    sup = BiliSupervisor(alias_store=alias)
    sup.run_dry(BiliTask(intent="event_watch"))
    gen = next(s for s in sup.last_ws.cache["game_scores"] if s["game_id"] == "genshin_impact")
    assert gen.get("aside_event_bonus") is True


def _aside_json(pubdates):
    return {"crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"), "scope": "游戏区 + 游戏相关",
            "hot_keywords": [{"rank": 1, "keyword": "将加盟LPL的韩援新面孔有哪些", "heat_score": 1095095, "is_game": True}],
            "videos": [{"title": "《鸣潮》0.1版本PV | 缩拉里斯", "bvid": "BVold%d" % i if p.startswith("2025") else "BVnew%d" % i,
                        "owner": "鸣潮", "category": "手机游戏",
                        "source": "游戏区排行榜" if p.startswith("2025") else "综合热门(游戏相关)", "pubdate": p,
                        "event_radar": {"view": 3607389, "like": 296195, "coin": 96790, "favorite": 49638, "share": 51996,
                                        "reply": 16608, "danmaku": 30902, "rcmd_reason": ""},
                        "official_event": {"mission_id": 4030240, "event_tags": ["鸣潮创作者激励计划"]},
                        "tags": ["鸣潮"], "engagement_rate": 15.03} for i, p in enumerate(pubdates)]}


def test_aside_json_and_old_videos_dropped(no_net, alias):
    # 실제 Aside 수집(2026-11-25) 형식. '游戏区排行榜' 은 2025-04 에 멈춘 목록이라 오래된 영상은 빠져야 한다
    recent = time.strftime("%Y-%m-%d %H:%M", time.gmtime(NOW - 3600 * 20))
    config.ASIDE_DIR.mkdir(parents=True)
    (config.ASIDE_DIR / "bilibili_2026-11-25.json").write_text(
        json.dumps(_aside_json(["2025-03-31 20:17", "2025-04-01 11:00", recent]), ensure_ascii=False), encoding="utf-8")
    j = aside_import.load_json()
    assert len(j["videos"]) == 3 and j["videos"][0]["coin"] == 96790 and j["videos"][0]["mission_id"] == 4030240
    assert j["events"][0] == {"name": "鸣潮创作者激励计划", "event_id": 4030240, "videos": 3, "total_view": 3607389 * 3}
    sup = BiliSupervisor(alias_store=alias)
    rep = sup.run_dry(BiliTask(intent="event_watch")).to_dict()
    norm = sup.last_ws.cache["normalize"]
    assert norm["old_by_source"] == {"aside:游戏区排行榜": 2}                # 1년 넘은 랭킹 영상 2개 제외
    assert "BVnew2" in {v["bvid"] for v in sup.last_ws.videos}
    assert any("공개 API" in s["name"] for s in rep["data_sources"])       # 신선한 영상이 30개 미만 → 보충
    assert sup.last_ws.keywords[0]["keyword"] == "将加盟LPL的韩援新面孔有哪些"   # Aside 순위가 먼저


# ── 정규화 · 6단계 구조 ─────────────────────────────────

def test_normalizer_uses_tags(no_net, alias):
    sup = BiliSupervisor(alias_store=alias)
    sup.run_dry(BiliTask(intent="event_watch"))
    bv4 = next(v for v in sup.last_ws.videos if v["bvid"] == "BV4")
    assert bv4["game_ids"] == ["genshin_impact"]  # 제목엔 없고 태그에만 있는 게임


def test_six_agents_match_figma_chapter_12():
    assert [s.stage.split()[0] for s in WORKERS.values()] == ["1", "2", "3", "4", "5", "6"]
    assert WORKERS["scorer"].uses_llm is False                         # 3 점수화: 코드만
    chain = {n: s.requires for n, s in WORKERS.items()}
    assert chain == {"collector": None, "normalizer": "collector", "scorer": "normalizer",
                     "analyst": "scorer", "planner": "analyst", "performance": None}


def test_dry_run_report_and_db_rows(no_net, alias):
    sup = BiliSupervisor(alias_store=alias)
    d = sup.run_dry(BiliTask(intent="game_deep_dive", game="원신", user_title="原神新角色怎么配队")).to_dict()
    assert d["opportunities"] and all(o["score"] is not None for o in d["opportunities"])
    assert d["title_diagnosis"]["title"] == "原神新角色怎么配队"
    assert list(d["agent_stages"]) == ["collector", "normalizer", "scorer", "analyst"]
    rows = team_db.build_rows(sup.last_ws, d)
    assert len(rows["videos"]) == len(VIDEOS) and rows["videos"][0]["platform"] == "bilibili"
    assert {"coins", "favorites"} <= set(rows["videos"][0]) and rows["topic_scores"]
    json.dumps(rows, default=str)


# ── 6 성과 기록 ────────────────────────────────────────

def test_performance_weights_need_8_samples():
    comp = lambda d, o: {"demand": d, "outlier": o, "freshness": 0.5, "competition": 0.3}  # noqa: E731
    few = [{"components": comp(0.1 * i, 0.5), "view": 1000 * i} for i in range(1, 5)]
    assert perf.propose_weights(few)["ready"] is False
    many = [{"components": comp(0.1 * i, 0.5), "view": 1000 * (2 ** i)} for i in range(1, 10)]
    p = perf.propose_weights(many)
    assert p["ready"] and p["proposed_weights"]["demand"] > 0 and "승인" in p["note"]


def test_register_upload_and_checkpoints(no_net, alias):
    report = {"plan": {"plan_id": "bili-x-genshin-v1", "game_id": "genshin_impact", "status": "validated",
                       "score_reference": {"score": 1.2, "components": {"demand": 1, "outlier": 0.5, "freshness": 0.8, "competition": 0.2}}}}
    perf.register_upload("BVmine", report)
    write_aside(config.ASIDE_DIR, "bilibili_performance.csv", "bvid,수집시각,조회수,좋아요,코인,즐겨찾기,댓글\n"
                                                             "BVmine,2026-11-20 10:00,5000,300,120,200,40\n")
    d = BiliSupervisor(alias_store=alias).run_dry(BiliTask(intent="performance_review")).to_dict()
    up = d["performance"]["uploads"][0]
    assert up["plan_id"] == "bili-x-genshin-v1" and up["latest"]["view"] == 5000


def test_task_validation():
    with pytest.raises(ValueError):
        BiliTask(intent="unknown")
    with pytest.raises(ValueError):
        BiliTask(intent="title_check")
