"""팀 총괄 슈퍼바이저 (코드 라우터 + 보고서 병합, LLM 없음).

TeamTask ──┬─▶ 빌리빌리 서브 슈퍼바이저 (Python 호출, BiliReport)
           └─▶ YouTube 파트 (Claude Code 실행 결과 → YouTubeReport)
                         │
TeamReport ◀── 병합: 플랫폼별 상태·요약 / 策划案 공통 보기 / 기회 목록 / 빌리빌리→YouTube 소재

LLM 을 쓰지 않는 이유: 어느 플랫폼에 보낼지는 intent 표(INTENT_MAP)로 정해지고,
YouTube 의 LLM 단계는 Claude Code 안에서만 돌기 때문에 총괄 단계에서 판단할 거리가 적다.
판단(분석·기획·검증)은 각 플랫폼 서브 슈퍼바이저가 한다.
"""
from typing import Any, Callable, Dict, List, Optional

from . import platforms
from .contracts import INTENT_MAP, TeamReport, TeamTask
from .plan_adapter import normalize_plan


class TeamSupervisor:
    def __init__(self, run_bilibili: Optional[Callable[..., Dict]] = None,
                 load_youtube: Optional[Callable[..., Optional[Dict]]] = None):
        # 테스트에서 가짜 함수를 끼워 넣을 수 있게 주입 가능
        self.run_bilibili = run_bilibili or platforms.run_bilibili
        self.load_youtube = load_youtube or platforms.load_youtube

    def run(self, task: TeamTask, bilibili_dry_run: bool = False) -> TeamReport:
        status: Dict[str, Dict[str, Any]] = {}
        reports: Dict[str, Dict[str, Any]] = {}
        warnings: List[str] = []

        for p in task.platforms:
            sub_intent = INTENT_MAP[task.intent][p]
            if sub_intent is None:
                status[p] = {"status": "unsupported", "note": "%s 는 '%s' 를 지원하지 않음" % (p, task.intent)}
                continue
            try:
                if p == "bilibili":
                    rep = self.run_bilibili(sub_intent, game=task.game, title=task.title,
                                            task_id=task.task_id, dry_run=bilibili_dry_run)
                else:
                    rep = self.load_youtube(sub_intent, run_id=task.youtube_run_id, task_id=task.task_id)
            except Exception as exc:  # 한 플랫폼이 실패해도 다른 플랫폼 결과는 살린다
                status[p] = {"status": "error", "error": "%s: %s" % (type(exc).__name__, exc)}
                warnings.append("%s 실행 실패: %s" % (p, exc))
                continue
            if rep is None:
                status[p] = {"status": "no_run",
                             "note": "YouTube 실행 기록이 없습니다. youtube/ 폴더에서 Claude Code 로 "
                                     "/youtube-pipeline 을 먼저 실행하세요."}
                warnings.append(status[p]["note"])
                continue
            reports[p] = rep
            status[p] = {"status": "ok", "sub_intent": sub_intent, "summary_ko": rep.get("summary_ko"),
                         "run_id": rep.get("run_id"), "warnings": len(rep.get("warnings", [])),
                         "data_sources": rep.get("data_sources", [])}
            if p == "youtube" and any(d.get("is_sample") for d in rep.get("data_sources", [])):
                warnings.append("youtube: 연습용 샘플 데이터(지어낸 데이터)로 만든 결과입니다")

        plans = []
        for p, rep in reports.items():
            if rep.get("plan"):
                view, w = normalize_plan(rep["plan"], rep.get("plan_validation"))
                plans.append(view)
                warnings += ["%s 기획안 변환: %s" % (p, x) for x in w]
                if view["status"] != "validated":
                    warnings.append("%s 기획안 %s 은(는) 검증 미통과(%s)" % (p, view["plan_id"], view["status"]))

        return TeamReport(
            task_id=task.task_id, intent=task.intent,
            summary_ko=_summary(task, status, plans),
            platforms={p: dict(s, report=reports.get(p)) for p, s in status.items()},
            plans=plans,
            opportunities=_opportunities(reports),
            cross_platform=_cross_platform(reports),
            warnings=warnings,
        )


def _opportunities(reports: Dict[str, Dict]) -> List[Dict]:
    rows = []
    for o in reports.get("bilibili", {}).get("opportunities", []):
        rows.append({"platform": "bilibili", "id": o.get("game_zh"), "name": o.get("game_ko") or o.get("game_zh"),
                     "score": o.get("score"), "reason": o.get("reason_ko")})
    for o in reports.get("youtube", {}).get("opportunities", []):
        rows.append({"platform": "youtube", "id": o.get("topic_id"),
                     "name": o.get("name_ko") or o.get("topic_name") or o.get("topic_id"),
                     "score": o.get("score"), "reason": o.get("reason_ko")})
    return rows  # 점수는 플랫폼별 기준이 달라 서로 비교·정렬하지 않는다


def _cross_platform(reports: Dict[str, Dict]) -> Dict[str, Any]:
    cards = reports.get("bilibili", {}).get("overseas_trend_cards", [])
    return {"bilibili_to_youtube": {
        "note": "빌리빌리 상위 반응 소재를 한국어로 옮긴 '해외 트렌드 소재'. YouTube 기획 시 참고용(그대로 복제 금지).",
        "cards": cards}} if cards else {}


def _summary(task: TeamTask, status: Dict[str, Dict], plans: List[Dict]) -> str:
    lines = ["[팀 %s] 플랫폼 %d개 중 %d개 결과 있음." % (
        task.intent, len(status), sum(1 for s in status.values() if s["status"] == "ok"))]
    for p, s in status.items():
        if s["status"] == "ok":
            lines.append("- %s: %s" % (p, s.get("summary_ko") or "(요약 없음)"))
        else:
            lines.append("- %s: %s" % (p, s.get("note") or s.get("error") or s["status"]))
    if plans:
        lines.append("기획안: " + ", ".join("%s %s(%s)" % (v["platform"], v["plan_id"], v["status"]) for v in plans))
    return "\n".join(lines)
