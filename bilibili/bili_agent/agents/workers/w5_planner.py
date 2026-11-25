"""에이전트 5 · 기획안 (기획안 12장 '5 기획안' — 작성 + 규칙 검사 코드 + 별도 검토 단계)

단계 안의 흐름 (코드가 순서를 강제):
  plan_writer(LLM) → 규칙 검사(코드, plan_rules) → plan_reviewer(LLM, 별도 검토)
      └─ 미통과면 issues 를 붙여 plan_writer 에게 1회 되돌림 → 다시 규칙 검사 + 검토
      └─ 그래도 미통과면 status = needs_review (사람 검토)
策划案 본문은 간체 중국어(빌리빌리 주 시청자), 내부 요약은 한국어.
DB(13장): plans (plan-v1 jsonb, status)
"""
from typing import Dict, Optional

from ... import config
from ...tools import metrics, plan_rules
from ...workspace import Workspace
from ..base import GAME_ID_PROP, STR_LIST, WorkerSpec, submit, tool
from .w4_analyst import LOOKUP_EVIDENCE, h_get_top_titles, h_lookup_evidence

MAX_REVISIONS = 1


def _target_game(ws: Workspace, game_id: Optional[str]) -> Optional[Dict]:
    if game_id:
        return ws.alias.resolve_id(game_id)
    if ws.requested_game:
        return ws.requested_game
    scores = ws.cache.get("game_scores") or []
    return ws.alias.resolve_id(scores[0]["game_id"]) if scores else None


def h_get_plan_context(ws: Workspace, game_id: Optional[str] = None) -> Dict:
    g = _target_game(ws, game_id)
    if not g:
        raise ValueError("기획 대상 게임을 정할 수 없습니다. game_id 를 지정하세요.")
    gid = g["game_id"]
    scores = ws.cache.get("game_scores") or []
    analyst = ws.findings.get("analyst", {})
    ctx = {
        "game": {"game_id": gid, "zh": g["zh"], "ko": g["ko"], "en": g["en"]},
        "score": next((s for s in scores if s["game_id"] == gid), None),
        "official_activities": [e for e in metrics.event_signals(ws.videos, ws.alias) if e["game_id"] == gid][:3],
        "aside_official_topics": [e for e in ws.aside_events if any(x["game_id"] == gid for x in ws.alias.find_in_text(e["name"]))][:5],
        "duration_distribution": metrics.duration_and_type_distribution(ws.videos_for(gid))["duration_buckets"],
        "content_type_map(분석 유형→기획 유형, null=가장 가까운 것)": plan_rules.CONTENT_TYPE_MAP,
        "title_benchmark": metrics.title_benchmark(ws.videos_for(gid)),
        "top_titles": h_get_top_titles(ws, n=8, game_id=gid)["titles"],
        "analysis": {k: analyst.get(k) for k in ("summary_ko", "duration_advice", "title_review", "claims")},
        "constraints": {"content_type": plan_rules.CONTENT_TYPES, "hook_types": plan_rules.HOOK_TYPES,
                        "sections_in_order": plan_rules.SECTIONS, "copyright_must_cover": list(plan_rules.COPYRIGHT_REQUIRED)},
    }
    last = ws.cache.get("plan_validation")
    if last and not last.get("passed"):
        ctx["previous_validation_failed"] = last
    return ctx


def assemble_plan(ws: Workspace) -> Optional[Dict]:
    p = ws.cache.get("plan_draft")
    if not p:
        return None
    g = ws.alias.resolve_id(p.get("game_id", "")) or _target_game(ws, None) or {}
    s = next((x for x in ws.cache.get("game_scores") or [] if x["game_id"] == g.get("game_id")), None)
    plan = {k: p.get(k) for k in ("content_type", "target_duration_sec", "hooks", "selected_hook", "script_sections",
                                  "titles", "thumbnail_brief", "copyright_checklist", "rationale_zh", "platform_extras")}
    plan.update({"schema": plan_rules.PLAN_SCHEMA_VERSION,
                 "plan_id": "bili-%s-%s-v%d" % (ws.run_id, g.get("game_id", "unknown"), ws.cache.get("plan_version", 1)),
                 "platform": "bilibili", "language": "zh", "game": g.get("zh"), "game_id": g.get("game_id"),
                 "score_reference": {"score": s and s["score"], "components": s and s["components"],
                                     "note": plan_rules.SCORE_DISCLAIMER},
                 "data_sources": ws.data_sources})
    return plan


def _rule_check(ws: Workspace) -> Dict:
    plan = assemble_plan(ws)
    has_activity = any(e["game_id"] == plan["game_id"] for e in metrics.event_signals(ws.videos, ws.alias))
    result = plan_rules.check_plan(plan, require_activity_tag=has_activity)
    ws.cache["plan_rule_check"] = result
    return result


def h_get_plan(ws: Workspace) -> Dict:
    return assemble_plan(ws) or {"error": "아직 기획안이 없습니다"}


def h_run_rule_checks(ws: Workspace) -> Dict:
    return _rule_check(ws)


PLAN_PROPS = {
    "game_id": {"type": "string"},
    "content_type": {"type": "string", "enum": plan_rules.CONTENT_TYPES},
    "target_duration_sec": {"type": "integer"},
    "hooks": {"type": "array", "items": {"type": "object", "properties": {
        "type": {"type": "string", "enum": plan_rules.HOOK_TYPES}, "line_zh": {"type": "string"}}, "required": ["type", "line_zh"]}},
    "selected_hook": {"type": "string", "enum": plan_rules.HOOK_TYPES},
    "script_sections": {"type": "array", "items": {"type": "object", "properties": {
        "section": {"type": "string", "enum": plan_rules.SECTIONS}, "start_sec": {"type": "integer"},
        "end_sec": {"type": "integer"}, "points_zh": {"type": "string"}}, "required": ["section", "start_sec", "end_sec", "points_zh"]}},
    "titles": STR_LIST,
    "thumbnail_brief": {"type": "object", "properties": {"aspect_ratio": {"type": "string"}, "text_zh": {"type": "string"},
                                                         "style_zh": {"type": "string"}}, "required": ["aspect_ratio", "text_zh", "style_zh"]},
    "copyright_checklist": STR_LIST,
    "rationale_zh": {"type": "string"},
    "platform_extras": {"type": "object", "properties": {"activity_mission_id": {"type": "integer"}, "tags_zh": STR_LIST}},
}

WRITER = WorkerSpec(
    name="plan_writer", stage="5 기획안 · 작성", db_tables=["plans"], prompt_file="w5_plan_writer.md",
    tools=[tool("get_plan_context", "기획 근거(점수·공식 활동·길이 분포·제목 벤치마크·상위 제목·분석 결과·제약)와 이전 검증 실패 내용.",
                GAME_ID_PROP), LOOKUP_EVIDENCE],
    handlers={"get_plan_context": h_get_plan_context, "lookup_evidence": h_lookup_evidence},
    submit_tool=submit(PLAN_PROPS, [k for k in PLAN_PROPS if k != "platform_extras"]),
)
REVIEWER = WorkerSpec(
    name="plan_reviewer", stage="5 기획안 · 검토", db_tables=["plans"], prompt_file="w5_plan_reviewer.md",
    tools=[tool("get_plan", "검토할 기획안 JSON (plan_id·점수·데이터 출처는 코드가 채움)."),
           tool("run_rule_checks", "결정적 규칙 검사: 구조·시간 구간·저작권 필수 항목·'仅供排序参考'·예측 표현."),
           LOOKUP_EVIDENCE],
    handlers={"get_plan": h_get_plan, "run_rule_checks": h_run_rule_checks, "lookup_evidence": h_lookup_evidence},
    submit_tool=submit({"passed": {"type": "boolean"}, "issues": {"type": "array", "items": {"type": "object", "properties": {
        "field": {"type": "string"}, "problem": {"type": "string"}, "fix_hint": {"type": "string"}},
        "required": ["field", "problem"]}}}, ["passed", "issues"]),
)


def _sub(ws: Workspace, llm, spec: WorkerSpec, message: str) -> Optional[Dict]:
    from ..loop import run_tool_loop  # 순환 import 방지
    result, warns = run_tool_loop(llm, ws, spec.name, spec.system_prompt, spec.all_tools, spec.handlers,
                                  message, "submit_findings", config.WORKER_MAX_STEPS)
    ws.warnings += warns
    return result


def run(ws: Workspace, llm, instruction: str, context: str = "") -> Dict:
    """기획안 단계 전체: 작성 → 규칙 검사 → 검토 → (1회 수정)."""
    for attempt in range(MAX_REVISIONS + 1):
        ws.cache["plan_version"] = attempt + 1
        draft = _sub(ws, llm, WRITER, context + "\n\n[지시]\n" + instruction +
                     ("" if attempt == 0 else "\n\n이전 기획안이 검증을 통과하지 못했습니다. get_plan_context 의 "
                                              "previous_validation_failed 를 모두 고쳐 다시 제출하세요."))
        if draft is None:
            return {"ok": False, "reason": "plan_writer 가 기획안을 제출하지 못함"}
        ws.cache["plan_draft"] = draft
        rule = _rule_check(ws)
        review = _sub(ws, llm, REVIEWER, context + "\n\n기획안 %s 를 검토하세요." % assemble_plan(ws)["plan_id"]) or \
            {"passed": False, "issues": [{"field": "review", "problem": "검토 에이전트가 결과를 내지 못함"}]}
        rule = ws.cache.get("plan_rule_check") or rule
        passed = bool(rule["passed"] and review.get("passed"))
        ws.cache["plan_validation"] = {"plan_id": assemble_plan(ws)["plan_id"], "passed": passed, "rule_check": rule,
                                       "reviewer": {"passed": review.get("passed"), "issues": review.get("issues", [])},
                                       "attempt": attempt + 1}
        ws.log("planner", "validation", "attempt=%d passed=%s" % (attempt + 1, passed), ok=passed)
        if passed:
            break
    v = ws.cache["plan_validation"]
    ws.findings["planner"] = {"summary_ko": draft.get("summary_ko", ""), "plan_id": v["plan_id"],
                              "status": "validated" if v["passed"] else "needs_review"}
    return {"ok": True, "plan_id": v["plan_id"], "status": ws.findings["planner"]["status"], "attempts": v["attempt"],
            "remaining_issues": v["reviewer"]["issues"] + v["rule_check"]["errors"] if not v["passed"] else []}


SPEC = WorkerSpec(name="planner", stage="5 기획안", db_tables=["plans"], requires="analyst", run_code=run)
