"""팀 총괄 슈퍼바이저 테스트 (네트워크·API 키 불필요). 두 파트의 실제 예시 기획안을 픽스처로 쓴다."""
import json
from pathlib import Path

import pytest

from team_supervisor.contracts import INTENT_MAP, PLATFORMS, TEAM_INTENTS, TeamTask
from team_supervisor.plan_adapter import normalize_plan
from team_supervisor.supervisor import TeamSupervisor

ROOT = Path(__file__).resolve().parent.parent
BILI_REPORT = json.loads((ROOT / "bilibili/docs/example_report_plan_run4.json").read_text(encoding="utf-8"))
YT_PLAN = json.loads((ROOT / "youtube/docs/examples/05_plan.example.json").read_text(encoding="utf-8"))
SECTION_IDS = ["hook", "problem", "body", "cta", "ending"]


def test_normalize_bilibili_plan():
    v, w = normalize_plan(BILI_REPORT["plan"], BILI_REPORT["plan_validation"])
    assert w == []
    assert v["platform"] == "bilibili" and v["language"] == "zh"
    assert v["game"] == {"id": "league_of_legends", "name": "英雄联盟"}
    assert v["content_type"]["id"] == "analysis"
    assert sorted(h["type"] for h in v["hooks"]) == ["challenge_twist", "question", "result_first"]
    assert [s["id"] for s in v["sections"]] == SECTION_IDS and all(s["text"] for s in v["sections"])
    assert v["score"]["value"] == BILI_REPORT["plan"]["score_reference"]["score"]
    assert "platform_extras" in v["extras"]


def test_normalize_bilibili_six_agent_plan():
    # 빌리빌리 수직 구조(에이전트 6개) 실제 실행 보고서도 같은 공통 보기로 바뀌어야 한다
    rep = json.loads((ROOT / "bilibili/docs/example_report_six_agents.json").read_text(encoding="utf-8"))
    v, w = normalize_plan(rep["plan"], rep["plan_validation"])
    assert w == [] and v["status"] == "validated" and v["language"] == "zh"
    assert [s["id"] for s in v["sections"]] == SECTION_IDS
    assert set(rep["agent_stages"]) == {"collector", "normalizer", "scorer", "analyst", "planner"}


def test_performance_review_routes_to_both():
    rep = TeamSupervisor(fake_bili, fake_yt).run(TeamTask(intent="performance_review")).to_dict()
    assert rep["platforms"]["bilibili"]["sub_intent"] == "performance_review"
    assert rep["platforms"]["youtube"]["sub_intent"] == "performance_review"


def test_normalize_youtube_plan():
    v, w = normalize_plan(YT_PLAN)
    assert w == []
    assert v["platform"] == "youtube" and v["language"] == "ko"
    assert v["game"]["id"] == "steal_a_brainrot"
    assert v["content_type"]["id"] == "guide"
    assert [s["id"] for s in v["sections"]] == SECTION_IDS
    assert v["score"]["value"] == YT_PLAN["score_reference"]["topic_score"]
    assert v["thumbnail"]["aspect_ratio"] == "9:16"
    assert {"shot_list", "hashtags", "evidence_refs"} <= set(v["extras"])


def test_both_views_share_shape():
    b, _ = normalize_plan(BILI_REPORT["plan"], BILI_REPORT["plan_validation"])
    y, _ = normalize_plan(YT_PLAN)
    assert set(b) == set(y)
    assert set(b["hooks"][0]) == set(y["hooks"][0]) and set(b["sections"][0]) == set(y["sections"][0])


def test_unknown_label_is_reported_not_dropped():
    plan = dict(YT_PLAN, content_type="브이로그")
    v, w = normalize_plan(plan)
    assert v["content_type"]["id"] == "unknown:브이로그" and w


def test_intent_map_is_complete():
    assert set(INTENT_MAP) == set(TEAM_INTENTS)
    assert all(set(m) == set(PLATFORMS) for m in INTENT_MAP.values())


# ── 라우터 ─────────────────────────────────────────────────

def fake_bili(intent, **kw):
    return dict(BILI_REPORT, intent=intent, overseas_trend_cards=[{"title_ko": "카드", "source_bvid": "BV1"}])


def fake_yt(intent, **kw):
    return {"platform": "youtube", "intent": intent, "run_id": "r1", "summary_ko": "유튜브 요약",
            "opportunities": [{"topic_id": "doors", "name_ko": "도어즈", "score": 0.7}],  # 실제 YouTube 필드명
            "plan": YT_PLAN, "plan_validation": {"passed": True},
            "data_sources": [{"name": "sample", "is_sample": True}], "warnings": []}


def test_route_both_platforms():
    rep = TeamSupervisor(fake_bili, fake_yt).run(TeamTask(intent="deep_dive")).to_dict()
    assert rep["platforms"]["bilibili"]["sub_intent"] == "game_deep_dive"
    assert rep["platforms"]["youtube"]["sub_intent"] == "topic_deep_dive"
    assert {p["platform"] for p in rep["plans"]} == {"bilibili", "youtube"}
    assert {o["platform"] for o in rep["opportunities"]} == {"bilibili", "youtube"}
    assert {"platform": "youtube", "id": "doors", "name": "도어즈", "score": 0.7, "reason": None} in rep["opportunities"]
    assert rep["cross_platform"]["bilibili_to_youtube"]["cards"]
    assert any("샘플 데이터" in w for w in rep["warnings"])          # YouTube 연습 데이터 경고 전달
    assert any("검증 미통과" in w for w in rep["warnings"])          # 빌리빌리 run4 기획안은 needs_review


def test_unsupported_intent_and_missing_run():
    rep = TeamSupervisor(fake_bili, lambda *a, **k: None).run(TeamTask(intent="title_check", title="标题")).to_dict()
    assert rep["platforms"]["youtube"]["status"] == "unsupported"
    rep = TeamSupervisor(fake_bili, lambda *a, **k: None).run(TeamTask(intent="trend_scan")).to_dict()
    assert rep["platforms"]["youtube"]["status"] == "no_run" and rep["platforms"]["bilibili"]["status"] == "ok"


def test_one_platform_failure_keeps_other():
    def broken(*a, **k):
        raise RuntimeError("API 키 없음")
    rep = TeamSupervisor(broken, fake_yt).run(TeamTask(intent="trend_scan")).to_dict()
    assert rep["platforms"]["bilibili"]["status"] == "error"
    assert rep["platforms"]["youtube"]["status"] == "ok" and rep["plans"]


def test_task_validation():
    with pytest.raises(ValueError):
        TeamTask(intent="nope")
    with pytest.raises(ValueError):
        TeamTask(intent="trend_scan", platforms=("tiktok",))
