"""오프라인 테스트: 네트워크·API 키 없이 실행된다 (가짜 데이터 + 가짜 LLM)."""
import json
import time
from types import SimpleNamespace

import pytest

from bili_agent import config
from bili_agent.agents import supervisor as sup_mod
from bili_agent.agents.supervisor import BiliSupervisor
from bili_agent.contracts import BiliTask
from bili_agent.tools import bilibili_api, metrics
from bili_agent.tools.alias_store import AliasStore

NOW = time.time()


def video(bvid, title, view, coin=0, fav=0, like=0, share=0, dur=300, hours_ago=10, mission=None):
    return {"bvid": bvid, "title": title, "tid": 172, "tname": "手机游戏", "pubdate": NOW - hours_ago * 3600,
            "duration_sec": dur, "view": view, "like": like, "coin": coin, "favorite": fav, "share": share,
            "reply": 0, "danmaku": 0, "author": "x", "mission_id": mission, "source": "test"}


VIDEOS = [
    video("BV1", "【原神】新版本角色攻略 平民配队", 100000, coin=2000, fav=3000, like=5000, share=100, mission=11),
    video("BV2", "《明日方舟》TL-S-4 平民单核", 50000, coin=5000, fav=4000, like=6000, share=300, dur=700),
    video("BV3", "BLG夺冠！S16决赛赛后数据", 900000, coin=10000, fav=8000, like=30000, share=2000, dur=200),
    video("BV4", "原神 实况 第一视角 全流程", 30000, coin=100, fav=200, like=800, share=10, dur=2400),
    video("BV5", "某个没收录的新游戏 PV", 20000, coin=50, fav=60, like=300, share=5, dur=90),
]
KEYWORDS = [{"keyword": "原神新角色", "rank": 3, "heat_score": 1}, {"keyword": "三角洲行动新赛季", "rank": 8, "heat_score": 1},
            {"keyword": "今日天气", "rank": 1, "heat_score": 1}]


@pytest.fixture
def alias():
    return AliasStore.load()


def test_alias_resolve_all_scripts(alias):
    assert alias.resolve("원신")["game_id"] == "genshin_impact"
    assert alias.resolve("Genshin Impact")["zh"] == "原神"
    assert [g["game_id"] for g in alias.find_in_text("BLG夺冠！S16决赛")] == ["league_of_legends"]
    assert alias.find_in_text("今日天气") == []


def test_engagement_and_multiple():
    r = metrics.rank_by_engagement(VIDEOS, top=5)
    assert r["top"][0]["bvid"] == "BV2"  # 명일방주 영상의 반응률이 가장 높다
    assert r["top"][0]["engagement_multiple"] > 1


def test_distribution_and_types():
    d = metrics.duration_and_type_distribution(VIDEOS)
    assert sum(b["count"] for b in d["duration_buckets"]) == len(VIDEOS)
    assert metrics.classify_type("BLG夺冠！S16决赛") == "e스포츠"
    assert metrics.classify_type("新版本角色攻略") == "공략"


def test_title_diagnosis():
    bench = metrics.title_benchmark(VIDEOS)
    diag = metrics.diagnose_title("【攻略】原神新角色", bench)
    assert diag["features"]["square_brackets"] == 1
    assert diag["length_gap_vs_median"] == diag["features"]["length"] - bench["median_length"]


def test_scores_include_leading_signal_game(alias):
    scores = metrics.score_games(VIDEOS, KEYWORDS, alias, now=NOW)
    ids = [s["game_id"] for s in scores]
    assert "delta_force" in ids  # 핫서치에만 있고 영상은 없는 게임도 후보에 포함
    sig = metrics.hot_keyword_signals(KEYWORDS, VIDEOS, alias)
    assert any(s["game_id"] == "delta_force" and s["leading_signal"] for s in sig)


def test_dry_run_report(monkeypatch, alias):
    monkeypatch.setattr(bilibili_api, "fetch_popular_game_videos",
                        lambda pages=None: {"videos": VIDEOS, "origin": "snapshot", "snapshot_file": "t.json"})
    monkeypatch.setattr(bilibili_api, "fetch_trending_keywords", lambda: {"keywords": KEYWORDS, "origin": "live"})
    monkeypatch.setattr(bilibili_api, "load_ranking_snapshot", lambda: None)
    report = BiliSupervisor(alias_store=alias).run_dry(
        BiliTask(intent="game_deep_dive", game="원신", user_title="原神新角色怎么配队"))
    d = report.to_dict()
    assert d["platform"] == "bilibili" and d["opportunities"]
    assert all(o["score"] is not None for o in d["opportunities"])
    assert d["title_diagnosis"]["title"] == "原神新角色怎么配队"
    assert any("스냅샷" in w for w in d["warnings"])  # 스냅샷 사용 사실이 경고로 남는다
    json.dumps(d, ensure_ascii=False)  # 직렬화 가능


def test_task_validation():
    with pytest.raises(ValueError):
        BiliTask(intent="unknown")
    with pytest.raises(ValueError):
        BiliTask(intent="title_check")


# ── 가짜 LLM 으로 슈퍼바이저 루프 검증 ─────────────────────

def _tool_use(name, inp, i):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id="tu_%d" % i)


class FakeLLM:
    """정해진 순서대로 도구를 호출하는 가짜 모델. 시스템 프롬프트로 어떤 에이전트인지 구분."""

    def __init__(self):
        self.calls = []
        self.n = 0

    def create(self, system, messages, tools):
        self.n += 1
        names = [t["name"] for t in tools]
        self.calls.append(names)
        last = messages[-1]["content"]
        first_turn = len(messages) == 1
        if "delegate" in names:  # 슈퍼바이저
            done = sum(1 for m in messages if m["role"] == "user" and isinstance(m["content"], list))
            if done == 0:  # 수집 전에 분석 워커부터 부르는 실수 → 가드레일이 막아야 함
                block = _tool_use("delegate", {"worker": "engagement_analyst", "instruction": "분석"}, self.n)
            elif done == 1:
                block = _tool_use("delegate", {"worker": "collector", "instruction": "수집"}, self.n)
            elif done == 2:
                block = _tool_use("delegate", {"worker": "engagement_analyst", "instruction": "분석"}, self.n)
            else:
                block = _tool_use("submit_report", {"summary_ko": "요약", "warnings": []}, self.n)
            return SimpleNamespace(stop_reason="tool_use", content=[block])
        if first_turn:  # 워커 첫 턴: 자기 도구 하나 호출
            return SimpleNamespace(stop_reason="tool_use", content=[_tool_use(names[0], {}, self.n)])
        submit = {"summary_ko": "워커 요약", "data_quality_notes": [], "opportunities": [
            {"game_zh": "原神", "reason_ko": "테스트"}], "duration_advice": {"recommended_bucket": "3–10분", "reason_ko": "t"}}
        return SimpleNamespace(stop_reason="tool_use", content=[_tool_use("submit_findings", submit, self.n)])


def test_supervisor_loop_with_fake_llm(monkeypatch, alias):
    monkeypatch.setattr(bilibili_api, "fetch_popular_game_videos",
                        lambda pages=None: {"videos": VIDEOS, "origin": "live"})
    monkeypatch.setattr(bilibili_api, "fetch_trending_keywords", lambda: {"keywords": KEYWORDS, "origin": "live"})
    report = BiliSupervisor(llm=FakeLLM(), alias_store=alias).run(BiliTask(intent="trend_scan"))
    d = report.to_dict()
    errors = [r for r in d["agent_trace"] if not r["ok"]]
    assert errors and errors[0]["event"] == "tool:delegate"  # 수집 전 분석 시도는 거부됨
    assert d["summary_ko"] == "요약"
    assert d["opportunities"][0]["game_zh"] == "原神" and d["opportunities"][0]["score"] is not None
