"""두 플랫폼의 策划案/기획안(plan-v1)을 팀 공통 보기(team-plan-view-v1)로 바꾸는 어댑터.

각 파트의 코드는 고치지 않는다. 차이는 여기서만 흡수한다.

| 차이 | 빌리빌리 | YouTube | 공통 보기 |
|---|---|---|---|
| 텍스트 필드 | line_zh, points_zh, text_zh ... | line, points, text ... | text + language |
| 유형 이름 | 攻略 / 先看结果 / 开场 | 공략 / 결과 먼저 / 훅 | guide / result_first / hook (ID) |
| 게임 | game_id, game | topic_id, topic_name | game.id, game.name |
| 점수 | score_reference.score | score_reference.topic_score | score.value |
"""
from typing import Any, Dict, List, Optional, Tuple

VIEW_SCHEMA = "team-plan-view-v1"

CONTENT_TYPE_IDS = {
    "攻略": "guide", "공략": "guide",
    "实况": "lets_play", "실황": "lets_play",
    "分析": "analysis", "분석": "analysis",
    "评测": "review", "리뷰": "review",
    "밈·하이라이트": "meme_highlight",
}
HOOK_IDS = {
    "先看结果": "result_first", "결과 먼저": "result_first",
    "提问": "question", "질문": "question",
    "挑战/反转": "challenge_twist", "도전/반전": "challenge_twist",
}
SECTION_IDS = {
    "开场": "hook", "훅": "hook",
    "问题": "problem", "문제": "problem",
    "正文": "body", "본문": "body",
    "CTA": "cta",
    "结尾": "ending", "엔딩": "ending",
}

# 공통 보기에서 직접 다루는 원본 키 (나머지는 extras 로 보존)
_CONSUMED = {
    "schema", "plan_id", "platform", "language", "game", "game_id", "topic_id", "topic_name", "content_type",
    "target_duration_sec", "hooks", "selected_hook", "script_sections", "titles", "thumbnail_brief",
    "copyright_checklist", "score_reference", "data_sources", "rationale", "rationale_zh", "status",
}


def _text(d: Dict, key: str) -> str:
    """'line_zh' 가 있으면 그것을, 없으면 'line' 을 쓴다."""
    return d.get(key + "_zh") or d.get(key) or ""


def _map(table: Dict[str, str], label: Optional[str], what: str, warnings: List[str]) -> str:
    if label in table:
        return table[label]
    warnings.append("알 수 없는 %s: %r" % (what, label))
    return "unknown:%s" % label


def detect_language(plan: Dict) -> str:
    if plan.get("language"):
        return plan["language"]
    hooks = plan.get("hooks") or [{}]
    return "zh" if "line_zh" in hooks[0] or "rationale_zh" in plan else "ko"


def normalize_plan(plan: Dict, validation: Optional[Dict] = None) -> Tuple[Dict[str, Any], List[str]]:
    """원본 plan-v1 → (공통 보기, 경고 목록). 원본은 바꾸지 않는다."""
    w: List[str] = []
    platform = plan.get("platform") or "unknown"
    sr = plan.get("score_reference") or {}
    score = sr.get("score") if sr.get("score") is not None else sr.get("topic_score")

    if plan.get("status"):
        status = plan["status"]
    elif validation is not None:
        status = "validated" if validation.get("passed") else "needs_review"
    else:
        status = "unknown"

    view = {
        "schema": VIEW_SCHEMA,
        "source_schema": plan.get("schema"),
        "platform": platform,
        "language": detect_language(plan),
        "plan_id": plan.get("plan_id"),
        "status": status,
        "game": {"id": plan.get("game_id") or plan.get("topic_id"),
                 "name": plan.get("game") or plan.get("topic_name")},
        "content_type": {"id": _map(CONTENT_TYPE_IDS, plan.get("content_type"), "content_type", w),
                         "label": plan.get("content_type")},
        "target_duration_sec": plan.get("target_duration_sec"),
        "hooks": [{"type": _map(HOOK_IDS, h.get("type"), "hook type", w), "label": h.get("type"),
                   "text": _text(h, "line")} for h in plan.get("hooks") or []],
        "selected_hook": _map(HOOK_IDS, plan.get("selected_hook"), "selected_hook", w),
        "sections": [{"id": _map(SECTION_IDS, s.get("section"), "section", w), "label": s.get("section"),
                      "start_sec": s.get("start_sec"), "end_sec": s.get("end_sec"),
                      "text": _text(s, "points")} for s in plan.get("script_sections") or []],
        "titles": list(plan.get("titles") or []),
        "thumbnail": {"aspect_ratio": (plan.get("thumbnail_brief") or {}).get("aspect_ratio"),
                      "text": _text(plan.get("thumbnail_brief") or {}, "text"),
                      "style": _text(plan.get("thumbnail_brief") or {}, "style"),
                      # 이미지 생성용 프롬프트 (YouTube 썸네일 단계가 씀, 없으면 None)
                      "image_prompt": (plan.get("thumbnail_brief") or {}).get("image_prompt")},
        "copyright_checklist": list(plan.get("copyright_checklist") or []),
        "score": {"value": score, "note": sr.get("note")},
        "rationale": plan.get("rationale_zh") or plan.get("rationale") or "",
        "data_sources": plan.get("data_sources") or [],
        "extras": {k: v for k, v in plan.items() if k not in _CONSUMED},
    }
    return view, w
