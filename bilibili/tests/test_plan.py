"""策划案 생성·검증 (流水线设计 A-5/A-6) 오프라인 테스트."""
import copy
from types import SimpleNamespace

import pytest

from bili_agent.agents.supervisor import BiliSupervisor
from bili_agent.contracts import BiliTask
from bili_agent.tools import bilibili_api, plan_rules
from bili_agent.tools.alias_store import AliasStore

from .test_pipeline import KEYWORDS, VIDEOS, no_net  # noqa: F401 (fixture)

GOOD_PLAN = {
    "plan_id": "t", "platform": "bilibili", "game": "原神", "content_type": "攻略", "target_duration_sec": 420,
    "hooks": [{"type": "先看结果", "line_zh": "先看这套平民配队打满分的结果。"},
              {"type": "提问", "line_zh": "新角色到底值不值得抽？"},
              {"type": "挑战/反转", "line_zh": "零命也能打？我试了三天。"}],
    "selected_hook": "先看结果",
    "script_sections": [{"section": "开场", "start_sec": 0, "end_sec": 15, "points_zh": "展示结果"},
                        {"section": "问题", "start_sec": 15, "end_sec": 45, "points_zh": "抛出问题"},
                        {"section": "正文", "start_sec": 45, "end_sec": 380, "points_zh": "配队讲解"},
                        {"section": "CTA", "start_sec": 380, "end_sec": 405, "points_zh": "一键三连"},
                        {"section": "结尾", "start_sec": 405, "end_sec": 420, "points_zh": "预告下期"}],
    "titles": ["【原神】新角色平民配队攻略", "《原神》零命新角色能打吗？实测三天", "新角色平民配队：三套方案对比"],
    "thumbnail_brief": {"aspect_ratio": "16:9", "text_zh": "零命也能满分", "style_zh": "角色立绘+大字"},
    "copyright_checklist": ["游戏画面使用遵守官方二创政策", "BGM 使用免版税音乐", "不引用他人视频片段", "角色立绘仅用官方素材"],
    "score_reference": {"score": 1.2, "note": plan_rules.SCORE_DISCLAIMER},
    "data_sources": [{"name": "종합 인기", "origin": "live"}],
}


def test_good_plan_passes():
    r = plan_rules.check_plan(GOOD_PLAN)
    assert r["passed"], r["errors"]


@pytest.mark.parametrize("mutate,field", [
    (lambda p: p["hooks"].pop(), "hooks"),
    (lambda p: p["titles"].pop(), "titles"),
    (lambda p: p["script_sections"][2].update(start_sec=50), "script_sections"),  # 공백 구간
    (lambda p: p.update(target_duration_sec=600), "target_duration_sec"),
    (lambda p: p.update(copyright_checklist=["游戏画面使用遵守官方二创政策"]), "copyright_checklist"),
    (lambda p: p["score_reference"].update(note=""), "score_reference"),
    (lambda p: p.update(content_type="밈"), "content_type"),
    (lambda p: p["titles"].__setitem__(0, "预计播放破百万的原神攻略"), "prediction"),
])
def test_plan_rule_failures(mutate, field):
    plan = copy.deepcopy(GOOD_PLAN)
    mutate(plan)
    r = plan_rules.check_plan(plan)
    assert not r["passed"] and any(e["field"] == field for e in r["errors"])


def test_copyright_rule_accepts_variant_wording():
    # 4차 실제 실행의 실제 문구: '游戏与赛事画面' 도 游戏画面 항목으로 인정해야 한다
    plan = copy.deepcopy(GOOD_PLAN)
    plan["copyright_checklist"] = ["游戏与赛事画面：使用官方允许范围内的素材", "BGM：只用可商用曲库",
                                   "不搬运他人视频", "引用评论注明出处"]
    assert plan_rules.check_plan(plan)["passed"]


def test_prediction_detector():
    # 1차 실제 실행에서 슈퍼바이저가 쓴 문장 → 차단 대상
    assert plan_rules.find_prediction_phrases("반응이 중앙값의 1.3~1.9배 수준에 그칠 가능성이 큽니다")
    assert plan_rules.find_prediction_phrases("这期一定会火")
    # 과거 사실 인용은 허용
    assert not plan_rules.find_prediction_phrases("《仰望星空》播放254万，反应率为中位数的3.63倍")
    assert not plan_rules.find_prediction_phrases("반응률이 중앙값의 3.63배였습니다")


def test_markdown_render():
    md = plan_rules.plan_to_markdown(GOOD_PLAN, {"rule_check": plan_rules.check_plan(GOOD_PLAN)})
    assert "## 开场钩子（3 种）" in md and "✅ 采用" in md and plan_rules.SCORE_DISCLAIMER in md


def test_lookup_evidence_finds_source_data():
    # 3차 실제 실행에서 검토 에이전트가 데이터에 있는 곡을 '근거 없음'으로 오판 → 원본 조회 도구로 해결
    from bili_agent.agents.workers.w4_analyst import h_lookup_evidence
    from bili_agent.workspace import Workspace
    ws = Workspace(BiliTask(intent="trend_scan"), AliasStore.load())
    ws.add_raw([dict(v) for v in VIDEOS])
    r = h_lookup_evidence(ws, keyword="明日方舟")
    assert r["found"] == 1 and r["videos"][0]["bvid"] == "BV2" and r["videos"][0]["multiple_vs_pool"] > 1
    act = h_lookup_evidence(ws, mission_id=11)["activity"]
    assert act and act[0]["game_id"] == "genshin_impact"
    with pytest.raises(ValueError):
        h_lookup_evidence(ws)


# ── 슈퍼바이저 + 가짜 LLM: 수직 구조의 순서 가드레일과 기획안 단계 루프 ──────

def _tu(name, inp, i):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id="tu_%d" % i)


class ScriptedLLM:
    """슈퍼바이저는 정해진 순서로, 에이전트는 '첫 턴: 첫 도구 → 둘째 턴: 제출'. 검토 에이전트는 첫 검토만 불합격."""

    SUPERVISOR_SCRIPT = [
        ("delegate", {"worker": "analyst", "instruction": "분석"}),           # 3 점수화 전 → 거부
        ("delegate", {"worker": "collector", "instruction": "수집"}),
        ("delegate", {"worker": "normalizer", "instruction": "정규화"}),
        ("delegate", {"worker": "scorer", "instruction": "점수"}),            # LLM 없이 코드 실행
        ("delegate", {"worker": "analyst", "instruction": "분석"}),
        ("delegate", {"worker": "planner", "instruction": "기획 game_id=genshin_impact"}),
        ("submit_report", {"summary_ko": "조회수 100만을 달성할 것입니다"}),    # 예측 표현 → 거부
        ("submit_report", {"summary_ko": "원신 공략 기획안을 만들었습니다."}),
    ]

    def __init__(self):
        self.sup_step, self.n, self.reviews, self.agent_calls = 0, 0, 0, []

    def create(self, system, messages, tools):
        self.n += 1
        names = [t["name"] for t in tools]
        if "delegate" in names:
            name, inp = self.SUPERVISOR_SCRIPT[self.sup_step]
            self.sup_step += 1
            return SimpleNamespace(stop_reason="tool_use", content=[_tu(name, inp, self.n)])
        if len(messages) == 1:
            self.agent_calls.append(names[0])
            calls = [_tu(names[0], {}, self.n)]
            if names[0] == "load_aside":  # Aside CSV 가 없으니 공개 API 로 보충 (병렬 호출)
                calls.append(_tu("collect_popular_games", {}, self.n + 1000))
            return SimpleNamespace(stop_reason="tool_use", content=calls)
        if "get_plan_context" in names:
            sub = dict(copy.deepcopy(GOOD_PLAN), game_id="genshin_impact", rationale_zh="依据", summary_ko="기획")
        elif "run_rule_checks" in names:
            self.reviews += 1
            sub = {"summary_ko": "검토", "passed": self.reviews > 1,
                   "issues": [] if self.reviews > 1 else [{"field": "hooks", "problem": "钩子断言过强"}]}
        elif "get_game_scores" in names:
            sub = {"summary_ko": "분석", "opportunities": [{"game_zh": "原神", "reason_ko": "근거"}], "events": [],
                   "claims": [{"claim_ko": "원신 반응률이 높다", "evidence": ["get_engagement_ranking: BV1"]}]}
        elif "list_unmatched_titles" in names:
            sub = {"summary_ko": "정규화", "alias_candidates": []}
        else:
            sub = {"summary_ko": "수집", "data_quality_notes": []}
        return SimpleNamespace(stop_reason="tool_use", content=[_tu("submit_findings", sub, self.n)])


def test_vertical_flow_guards_and_plan_revision(no_net):
    llm = ScriptedLLM()
    d = BiliSupervisor(llm=llm, alias_store=AliasStore.load()).run(
        BiliTask(intent="game_deep_dive", game="原神")).to_dict()
    events = [(r["agent"], r["event"], r["ok"]) for r in d["agent_trace"]]
    assert ("supervisor", "tool:delegate", False) in events                 # 순서 건너뛰기 거부
    assert sum(1 for e in events if e[1] == "submit_rejected") == 1           # 예측 표현 제출 거부
    assert "get_game_scores" in llm.agent_calls and "load_aside" in llm.agent_calls
    assert not any(c == "scorer" for c in llm.agent_calls)                    # 점수화는 LLM 을 부르지 않음
    plan, v = d["plan"], d["plan_validation"]
    assert v["attempt"] == 2 and plan["plan_id"].endswith("-v2")             # 검토 불합격 → 1회 수정 후 통과
    assert plan["status"] == "validated" and plan["score_reference"]["note"] == plan_rules.SCORE_DISCLAIMER
    assert list(d["agent_stages"]) == ["collector", "normalizer", "scorer", "analyst", "planner"]
    assert d["summary_ko"] == "원신 공략 기획안을 만들었습니다."
