"""6단계 · 검증 실행기.

  validate          : 04_analysis / 05_plan 규칙 검사 → 06_validation.json (review 는 비워 둠)
  review --file F   : plan-validator 에이전트의 의미 검토(JSON)를 합쳐 최종 판정
판정: 규칙 통과 + 검토 통과 → plan.status = "validated"
      실패면 plan-writer 가 고쳐 다시 제출. 수정은 MAX_REVISIONS 회까지, 넘으면 "needs_review"(사람 판단).
"""
import hashlib
import json
from typing import Dict, Optional

from .common import (FILES, load_config, read_json, read_stage, run_dir, trace, write_json, write_stage)
from .plan_rules import check_analysis, check_plan, plan_to_markdown

MAX_REVISIONS = 2


def _hash(plan: Dict) -> str:
    return hashlib.sha1(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]


def _load_prev(run_id: str) -> Dict:
    p = run_dir(run_id) / FILES["validation"]
    return read_json(p) if p.exists() else {}


def run(run_id: str) -> Dict:
    cfg = load_config()
    scores, evidence = read_stage(run_id, "scores"), read_stage(run_id, "evidence")
    norm = read_stage(run_id, "normalized")
    vids = {v["video_id"] for v in norm["videos"]}
    plan = read_stage(run_id, "plan")
    prev = _load_prev(run_id)

    analysis_check = None
    if (run_dir(run_id) / FILES["analysis"]).exists():
        analysis_check = check_analysis(read_stage(run_id, "analysis"), scores, evidence, vids)
    rule = check_plan(plan, cfg, scores, evidence, vids, is_sample=norm.get("is_sample", False))

    h = _hash(plan)
    attempts = prev.get("attempts", 0) + (1 if prev.get("plan_hash") != h else 0)
    val = {"plan_id": plan.get("plan_id"), "plan_hash": h, "attempts": attempts,
           "analysis_check": analysis_check, "rule_check": rule,
           "review": prev.get("review") if prev.get("plan_hash") == h else None}
    val.update(_decide(val))
    write_stage(run_id, "validation", val)
    _sync_plan(run_id, plan, val)
    msg = "규칙 검사 %s (오류 %d, 경고 %d), 시도 %d회 → %s" % (
        "통과" if rule["passed"] else "실패", len(rule["errors"]), len(rule["warnings"]), attempts, val["next"])
    trace(run_id, "validate", msg, ok=rule["passed"])
    return {"run_id": run_id, "summary": msg, "errors": rule["errors"],
            "analysis_errors": (analysis_check or {}).get("errors", [])}


def merge_review(run_id: str, review_path: str) -> Dict:
    review = read_json(review_path)
    if not isinstance(review.get("passed"), bool) or not isinstance(review.get("issues", []), list):
        raise ValueError("review 형식: {\"passed\": bool, \"issues\": [{field, problem, fix_hint}]}")
    val = read_stage(run_id, "validation")
    plan = read_stage(run_id, "plan")
    if val.get("plan_hash") != _hash(plan):
        raise ValueError("기획안이 바뀌었습니다. 먼저 validate 를 다시 실행하세요.")
    val["review"] = review
    val.update(_decide(val))
    write_stage(run_id, "validation", val)
    _sync_plan(run_id, plan, val)
    msg = "의미 검토 %s → %s" % ("통과" if review["passed"] else "수정 필요", val["next"])
    trace(run_id, "review", msg, ok=review["passed"])
    return {"run_id": run_id, "summary": msg}


def _decide(val: Dict) -> Dict:
    rule_ok = val["rule_check"]["passed"] and (val.get("analysis_check") or {"passed": True})["passed"]
    rv: Optional[Dict] = val.get("review")
    if rule_ok and rv and rv.get("passed"):
        return {"passed": True, "status": "validated", "next": "통과 — 사람 승인 후 7단계(영상 생성)로 진행"}
    if rule_ok and rv is None:
        return {"passed": False, "status": "draft", "next": "plan-validator 의미 검토 필요"}
    # 규칙 실패 또는 검토 실패. 첫 제출 + 수정 MAX_REVISIONS 회까지 허용
    if val["attempts"] >= MAX_REVISIONS + 1:
        return {"passed": False, "status": "needs_review", "next": "수정 횟수 초과 — 사람이 판단"}
    return {"passed": False, "status": "draft", "next": "plan-writer 가 오류를 고쳐 다시 제출"}


def _sync_plan(run_id: str, plan: Dict, val: Dict) -> None:
    """status 를 기획안에 반영하고 Markdown 을 다시 만든다(해시에는 status 를 넣지 않기 위해 별도 파일)."""
    md = plan_to_markdown(dict(plan, status=val["status"]), val)
    (run_dir(run_id) / FILES["plan_md"]).write_text(md, encoding="utf-8")
    write_json(run_dir(run_id) / "05_plan.status.json", {"plan_id": plan.get("plan_id"), "status": val["status"]})
