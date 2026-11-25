"""빌리빌리 서브 슈퍼바이저 — 수직(계층형) 구조.

총괄 슈퍼바이저 ──BiliTask──▶ BiliSupervisor(Claude) ──delegate──▶ 에이전트 6개 (기획안 12장)
                ◀─BiliReport─                       ◀── 작업 공간(Workspace)으로 결과 공유 ──

  1 collector → 2 normalizer → 3 scorer(코드) → 4 analyst → 5 planner(작성+검토) │ 6 performance(별도)

- 에이전트끼리는 직접 대화하지 않는다. 모든 지시는 슈퍼바이저가, 모든 데이터는 작업 공간이 전달한다.
- 순서는 슈퍼바이저(LLM)가 정하지만, 앞 단계 없이 뒤 단계를 부르는 일은 코드가 막는다(requires 체인).
- run_dry(): LLM 없이 intent별 기본 계획을 코드로 실행 (API 키 없이 데이터 파이프라인 확인·테스트용).
"""
from typing import Dict, Optional

from .. import config
from ..contracts import BiliReport, BiliTask
from ..tools import metrics, plan_rules
from ..tools.alias_store import AliasStore
from ..workspace import Workspace
from .loop import LLM, run_tool_loop
from .workers import WORKERS
from .workers.w4_analyst import h_get_duration_type_distribution, h_get_top_titles
from .workers.w5_planner import assemble_plan

PIPELINE = ["collector", "normalizer", "scorer", "analyst", "planner"]
DEFAULT_PLANS = {
    "trend_scan": PIPELINE,
    "game_deep_dive": PIPELINE,
    "title_check": ["collector", "normalizer", "scorer", "analyst"],
    "event_watch": ["collector", "normalizer", "scorer", "analyst"],
    "performance_review": ["performance"],
}

SUPERVISOR_TOOLS = [
    {"name": "delegate",
     "description": "에이전트 하나에게 일을 맡기고 결과를 받는다. 앞 단계가 끝나지 않았으면 코드가 거부한다.",
     "input_schema": {"type": "object", "properties": {
         "worker": {"type": "string", "enum": list(WORKERS)},
         "instruction": {"type": "string", "description": "에이전트에게 줄 구체적인 지시(한국어). 에이전트는 이 대화를 볼 수 없다."}},
         "required": ["worker", "instruction"]}},
    {"name": "submit_report",
     "description": "최종 보고서를 총괄 슈퍼바이저에게 제출하고 종료한다. 반드시 마지막에 한 번 호출.",
     "input_schema": {"type": "object", "properties": {
         "summary_ko": {"type": "string", "description": "한국어 3~5문장, 이번 주 행동 제안 포함"},
         "warnings": {"type": "array", "items": {"type": "string"}}},
         "required": ["summary_ko"]}},
]


class BiliSupervisor:
    def __init__(self, llm: Optional[LLM] = None, alias_store: Optional[AliasStore] = None):
        self.llm = llm
        self.alias = alias_store or AliasStore.load()
        self.last_ws: Optional[Workspace] = None  # 마지막 실행의 작업 공간 (DB 행 만들기용)

    # ── LLM 슈퍼바이저 ─────────────────────────────────────
    def run(self, task: BiliTask) -> BiliReport:
        self.llm = self.llm or LLM()
        ws = self.last_ws = Workspace(task, self.alias)
        ws.log("supervisor", "task", task.to_prompt().replace("\n", " | "))
        system = (config.PROMPT_DIR / "supervisor.md").read_text(encoding="utf-8")
        first = task.to_prompt() + "\n\n위 BiliTask를 처리하세요."
        result, warns = run_tool_loop(self.llm, ws, "supervisor", system, SUPERVISOR_TOOLS,
                                      {"delegate": self._delegate}, first, "submit_report",
                                      config.SUPERVISOR_MAX_STEPS,
                                      terminal_check=lambda inp: check_report_submission(ws, inp))
        ws.warnings += warns
        if result is None:
            return build_report(ws, "슈퍼바이저가 보고서를 완성하지 못했습니다. warnings 를 확인하세요.")
        ws.warnings += result.get("warnings", [])
        return build_report(ws, result["summary_ko"])

    def _delegate(self, ws: Workspace, worker: str, instruction: str) -> Dict:
        spec = WORKERS.get(worker)
        if spec is None:
            raise ValueError("unknown worker %r" % worker)
        if spec.requires and spec.requires not in ws.findings:
            # 수직 구조의 순서 가드레일: 순서는 LLM 이 정하지만 앞 단계를 건너뛰는 일은 막는다.
            raise RuntimeError("%s(%s) 는 %s 가 먼저 끝나야 합니다." % (worker, spec.stage, spec.requires))
        if spec.requires and not ws.collected:
            raise RuntimeError("수집된 영상이 0개라 %s 를 진행할 수 없습니다. collector 에게 다른 출처(공개 API 등)를 쓰도록 다시 지시하세요." % worker)
        if worker in ws.findings and worker != "performance":
            raise RuntimeError("%s 는 이미 실행했습니다. 결과는 작업 공간에 있습니다." % worker)
        ws.log("supervisor", "delegate→" + worker, instruction)
        context = worker_context(ws)
        if spec.run_code:  # 코드가 단계를 진행 (3 점수화: LLM 없음 / 5 기획안: 작성·검토 루프)
            return {"worker": worker, "stage": spec.stage, **spec.run_code(ws, self.llm, instruction, context)} \
                if worker == "planner" else {"worker": worker, "stage": spec.stage, **spec.run_code(ws, self.llm, instruction)}
        pre = spec.pre_run(ws) if spec.pre_run else None
        msg = context + ("\n\n[코드가 먼저 처리한 결과]\n%s" % pre if pre else "") + "\n\n[지시]\n" + instruction
        findings, warns = run_tool_loop(self.llm, ws, worker, spec.system_prompt, spec.all_tools, spec.handlers,
                                        msg, "submit_findings", config.WORKER_MAX_STEPS)
        ws.warnings += warns
        if findings is None:
            return {"worker": worker, "ok": False, "warnings": warns}
        if worker == "collector" and not ws.collected:
            return {"worker": worker, "ok": False, "findings": findings,
                    "error": "수집된 영상이 0개입니다. 다른 출처를 쓰도록 collector 를 다시 부르세요."}
        ws.findings[worker] = findings
        return {"worker": worker, "stage": spec.stage, "ok": True, "findings": findings}

    # ── LLM 없는 실행 (dry-run) ────────────────────────────
    def run_dry(self, task: BiliTask) -> BiliReport:
        """intent별 기본 계획을 코드로 실행. 문장은 템플릿이고, 숫자는 실제 계산 결과다. 기획안 단계는 건너뛴다."""
        ws = self.last_ws = Workspace(task, self.alias)
        ws.log("supervisor(dry)", "task", task.to_prompt().replace("\n", " | "))
        gid = ws.requested_game["game_id"] if ws.requested_game else None
        for worker in DEFAULT_PLANS[task.intent]:
            spec = WORKERS[worker]
            ws.log("supervisor(dry)", "delegate→" + worker, spec.stage)
            if worker == "collector":
                h = spec.handlers
                a = h["load_aside"](ws)
                if not a["videos"].get("used") or a["videos"]["freshness"]["need_supplement"]:
                    h["collect_popular_games"](ws)  # Aside 가 없거나, 최근 게시 영상이 부족하면 보충
                h["collect_trending"](ws)
                h["load_ranking_snapshot"](ws)
                ws.findings[worker] = {"summary_ko": "(dry-run) 게임 영상 %d개, 핫키워드 %d개 수집" % (
                    len(ws.raw_videos), len(ws.keywords)), "data_quality_notes": []}
            elif worker == "normalizer":
                n = spec.pre_run(ws)
                ws.findings[worker] = {"summary_ko": "(dry-run) 정규화 %d개 (게임 매칭 %d)" % (n["videos"], n["matched_to_game"]),
                                       "alias_candidates": []}
            elif worker == "scorer":
                spec.run_code(ws)
            elif worker == "analyst":
                scores = ws.cache.get("game_scores") or []
                dist = h_get_duration_type_distribution(ws, game_id=gid)
                if task.user_title:
                    spec.handlers["get_title_benchmark"](ws, game_id=gid)
                    spec.handlers["diagnose_title"](ws, title=task.user_title)
                ev = metrics.event_signals(ws.videos, ws.alias)
                ws.findings[worker] = {
                    "summary_ko": "(dry-run) 점수 상위 게임 %d개" % len(scores[:5]),
                    "opportunities": [{"game_zh": s["game_zh"], "game_ko": s["game_ko"],
                                       "reason_ko": "반응률 배수 %.2f, 풀 내 영상 %d개" % (s["engagement_multiple"], s["videos_in_pool"])}
                                      for s in scores[:5]],
                    "events": [{"game_zh": e["game_zh"], "kind": "official_activity",
                                "evidence": "활동 %s 참여 영상 %d개" % (e["mission_id"], e["videos"]),
                                "recommendation_ko": "(dry-run)"} for e in ev[:3]],
                    "duration_advice": {"recommended_bucket": dist["best_median_bucket(count>=2)"] or "-",
                                        "reason_ko": "(dry-run) 2개 이상 구간 중 조회수 중앙값 최고"},
                    "overseas_trend_cards": [{"source_bvid": t["bvid"], "title_zh": t["title"], "title_ko": "(LLM 실행 시 번역)",
                                              "why_ko": "반응률 배수 %.2f" % t["engagement_multiple"]}
                                             for t in h_get_top_titles(ws, n=5, game_id=gid)["titles"]],
                    "claims": []}
            elif worker == "planner":
                ws.log("supervisor(dry)", "skip", "기획안(작성+검토)은 LLM 실행 시에만 생성")
            elif worker == "performance":
                up = spec.handlers["list_uploads"](ws)
                w = spec.handlers["propose_weights"](ws)
                ws.findings[worker] = {"summary_ko": "(dry-run) 업로드 %d개, 성과 있는 영상 %d개, 보정안 %s" % (
                    len(up["uploads"]), up["with_data"], "있음" if w["ready"] else "표본 부족"),
                    "per_video": [], "next_actions_ko": []}
        return build_report(ws, "(dry-run) LLM 없이 기본 계획으로 실행한 결과입니다. 숫자는 실제 계산값입니다.")


def worker_context(ws: Workspace) -> str:
    lines = [ws.task.to_prompt(), "run_id: %s" % ws.run_id]
    if ws.requested_game:
        g = ws.requested_game
        lines.append("requested_game: game_id=%s zh=%s ko=%s" % (g["game_id"], g["zh"], g["ko"]))
    elif ws.task.game:
        lines.append("requested_game: '%s' 은(는) 별칭 사전에 없음" % ws.task.game)
    if ws.collected:
        lines.append("data: 수집 %d개 / 정규화 %d개, 핫키워드 %d개, Aside 공식 활동 %d개" % (
            len(ws.raw_videos), len(ws.videos), len(ws.keywords), len(ws.aside_events)))
    for name, f in ws.findings.items():
        lines.append("[%s 요약] %s" % (name, f.get("summary_ko", "")))
    return "\n".join(lines)


def check_report_submission(ws: Workspace, inp: Dict) -> Optional[str]:
    text = " ".join([inp.get("summary_ko", "")] + list(inp.get("warnings", [])))
    hits = plan_rules.find_prediction_phrases(text)
    if hits:
        return ("summary_ko/warnings 에 조회수·반응 예측 표현이 있습니다: %s. 점수는 정렬 참고용이므로 과거 데이터 사실로만 다시 쓰세요."
                % " / ".join("「%s」" % h for h in hits))
    return None


def _usage_with_cost(ws: Workspace) -> Dict:
    u = dict(ws.cache.get("usage") or {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0})
    price = config.PRICE_PER_MTOK.get(config.MODEL)
    if price:
        u["model"] = config.MODEL
        u["estimated_cost_usd"] = round(u["input_tokens"] / 1e6 * price[0] + u["output_tokens"] / 1e6 * price[1], 4)
    return u


def build_report(ws: Workspace, summary_ko: str) -> BiliReport:
    """에이전트 결과 + 결정적 계산값을 BiliReport 로 조립. 점수는 코드 계산값을 붙인다(전사 오류 방지)."""
    f = ws.findings
    a = f.get("analyst", {})
    scores = {s["game_zh"]: s for s in ws.cache.get("game_scores") or []}
    opportunities = [dict(o, score=(scores.get(o.get("game_zh")) or {}).get("score"),
                          components=(scores.get(o.get("game_zh")) or {}).get("components"))
                     for o in a.get("opportunities", [])]
    title_diag = None
    if ws.cache.get("title_diagnosis") or a.get("title_review"):
        title_diag = dict(ws.cache.get("title_diagnosis") or {"benchmark": ws.cache.get("title_benchmark")},
                          **(a.get("title_review") or {}))
    duration = None
    if a.get("duration_advice"):
        gid = ws.requested_game["game_id"] if ws.requested_game else "all"
        duration = dict(a["duration_advice"], distribution=ws.cache.get("distribution:%s" % gid) or ws.cache.get("distribution:all"))
    for name in ("collector", "normalizer"):
        for note in f.get(name, {}).get("data_quality_notes", []) or []:
            ws.warnings.append("%s: %s" % (name, note))

    plan, validation = assemble_plan(ws), ws.cache.get("plan_validation")
    if plan is not None:
        plan["status"] = "validated" if validation and validation["passed"] else "needs_review"
        if plan["status"] == "needs_review":
            ws.warnings.append("策划案 %s 未通过校验，需要人工审核" % plan["plan_id"])
    perf = None
    if "performance" in f:
        perf = {"agent": f["performance"], "uploads": ws.cache.get("performance_uploads"),
                "weight_proposal": ws.cache.get("weight_proposal")}

    return BiliReport(
        task_id=ws.task.task_id, intent=ws.task.intent, summary_ko=summary_ko, run_id=ws.run_id,
        opportunities=opportunities, events=a.get("events", []),
        title_diagnosis=title_diag, duration_advice=duration,
        overseas_trend_cards=a.get("overseas_trend_cards", []),
        alias_candidates=f.get("normalizer", {}).get("alias_candidates", []),
        plan=plan, plan_validation=validation, performance=perf,
        agent_stages={k: v.get("summary_ko") for k, v in f.items()},
        data_sources=ws.data_sources, agent_trace=ws.trace, usage=_usage_with_cost(ws),
        warnings=list(dict.fromkeys(ws.warnings)),
    )
