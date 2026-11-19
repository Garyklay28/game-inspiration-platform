"""5~6단계 · 기획안 규격(plan-v1)과 결정적 검증 규칙.

plan-writer 에이전트가 05_plan.json 을 쓰면, 이 규칙 검사가 먼저 돈다(LLM 없이 항상 같은 결과).
plan-validator 에이전트는 이 결과를 보고 규칙이 못 잡는 의미 문제(근거 없는 주장, 저작권 위험)를 본다.
필드 구조는 빌리빌리 파트의 策划案 plan-v1 과 같고, 텍스트 필드는 한국어다.
"""
import re
from typing import Any, Dict, List, Optional

PLAN_SCHEMA = "plan-v1"
CONTENT_TYPES = ["공략", "실황", "분석", "리뷰", "밈·하이라이트"]
HOOK_TYPES = ["결과 먼저", "질문", "도전/반전"]
SECTIONS = ["훅", "문제", "본문", "CTA", "엔딩"]
SHOT_SOURCES = ["직접 녹화", "AI 생성", "자체 제작 그래픽", "라이선스 소재"]

# 조회수·반응 '예측' 표현 차단. 과거 사실 인용("조회수 120만 회")은 허용.
PREDICTION_PATTERNS = [
    r"(조회수|조회|뷰|구독자?|좋아요).{0,12}(나올|찍을|달성할|돌파할|넘을|오를) ?(것|거|수)",
    r"(예상|예측)(되는|된다|됩니다|돼요)?.{0,8}(조회|구독|반응|뷰)",
    r"(조회|구독|반응|뷰).{0,10}(예상|예측)(됩니다|돼요|된다|합니다)",
    r"(떡상|대박|터질|터집|떡상할).{0,6}(것|거|확실|보장|예정)",
    r"(무조건|반드시|100%|확실히|보장).{0,8}(터|뜸|뜰|떡상|대박|조회)",
    r"(가능성이|확률이) ?(높|큽|크|큰)",
    r"will go viral|guaranteed",
]
_PRED = [re.compile(p, re.IGNORECASE) for p in PREDICTION_PATTERNS]

COPYRIGHT_REQUIRED = {
    "게임 화면": r"게임.{0,8}(화면|영상|녹화|플레이|소스)|직접 녹화|플레이 영상",
    "음악(BGM)": r"BGM|배경음악|음악|음원|효과음",
    "타인 소재": r"타인|다른 (크리에이터|채널|유튜버)|재업로드|퍼온|클립 인용|남의|원작자|출처",
}


def find_predictions(text: str) -> List[str]:
    return [m.group(0) for rx in _PRED for m in rx.finditer(text or "")]


def resolve_ref(ref: str, evidence: Dict, video_ids: Optional[set] = None) -> bool:
    """근거 경로가 실제로 있는지 확인. 예: evidence.topics.doors.duration_buckets / video:abc123"""
    if ref.startswith("video:"):
        return video_ids is not None and ref[6:] in video_ids
    path = ref[len("evidence."):] if ref.startswith("evidence.") else ref
    cur: Any = evidence
    for part in re.split(r"\.|\[(\d+)\]", path):
        if part is None or part == "":
            continue
        if isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    return True


def _plan_text(plan: Dict) -> str:
    parts = [h.get("line", "") for h in plan.get("hooks", [])]
    parts += [s.get("points", "") for s in plan.get("script_sections", [])]
    parts += list(plan.get("titles", [])) + [plan.get("description", ""), plan.get("angle", ""),
                                               plan.get("rationale", "")]
    tb = plan.get("thumbnail_brief") or {}
    parts += [tb.get("text", ""), tb.get("style", "")]
    return "\n".join(str(p) for p in parts)


def check_analysis(analysis: Dict, scores: Dict, evidence: Dict, video_ids: set) -> Dict:
    errors, warnings = [], []
    ids = {t["topic_id"] for t in scores.get("topics", [])}
    if analysis.get("selected_topic_id") not in ids:
        errors.append({"field": "selected_topic_id", "problem": "03_scores.json 에 없는 주제"})
    claims = analysis.get("claims") or []
    if not claims:
        errors.append({"field": "claims", "problem": "근거 있는 주장(claims)이 하나도 없음"})
    for i, c in enumerate(claims):
        refs = c.get("evidence_refs") or []
        if not refs:
            errors.append({"field": "claims[%d]" % i, "problem": "evidence_refs 없음: %s" % c.get("claim", "")[:40]})
        for r in refs:
            if not resolve_ref(r, evidence, video_ids):
                errors.append({"field": "claims[%d]" % i, "problem": "존재하지 않는 근거 경로: %s" % r})
    text = " ".join([analysis.get("summary", "")] + [c.get("claim", "") for c in claims])
    for p in find_predictions(text):
        errors.append({"field": "prediction", "problem": "예측 표현: 「%s」" % p})
    return {"passed": not errors, "errors": errors, "warnings": warnings}


def check_plan(plan: Dict, cfg: Dict, scores: Optional[Dict] = None, evidence: Optional[Dict] = None,
               video_ids: Optional[set] = None, is_sample: bool = False) -> Dict:
    """규칙 검사. 반환 {passed, errors[], warnings[]} — errors 가 있으면 실패."""
    pcfg = cfg["plan"]
    errors, warnings = [], []

    def err(field, msg):
        errors.append({"field": field, "problem": msg})

    def warn(field, msg):
        warnings.append({"field": field, "problem": msg})

    if plan.get("schema") != PLAN_SCHEMA:
        err("schema", "schema 는 %s" % PLAN_SCHEMA)
    if plan.get("content_type") not in CONTENT_TYPES:
        err("content_type", "다음 중 하나: %s" % " / ".join(CONTENT_TYPES))
    if scores is not None and plan.get("topic_id") not in {t["topic_id"] for t in scores["topics"]}:
        err("topic_id", "03_scores.json 에 없는 주제")

    hooks = plan.get("hooks") or []
    if sorted(h.get("type", "") for h in hooks) != sorted(HOOK_TYPES):
        err("hooks", "훅 3종을 하나씩: %s" % ", ".join(HOOK_TYPES))
    if plan.get("selected_hook") not in HOOK_TYPES:
        err("selected_hook", "hooks 의 type 중 하나여야 함")

    total = plan.get("target_duration_sec") or 0
    if not pcfg["min_duration_sec"] <= total <= pcfg["max_duration_sec"]:
        err("target_duration_sec", "%s초 — 설정 범위 %d~%d초" % (total, pcfg["min_duration_sec"], pcfg["max_duration_sec"]))
    secs = plan.get("script_sections") or []
    if [s.get("section") for s in secs] != SECTIONS:
        err("script_sections", "구간 순서: %s" % " → ".join(SECTIONS))
    prev = 0
    for s in secs:
        st, en = s.get("start_sec"), s.get("end_sec")
        if not isinstance(st, (int, float)) or not isinstance(en, (int, float)) or st >= en:
            err("script_sections", "%s 시작·끝 시간이 잘못됨" % s.get("section"))
            continue
        if abs(st - prev) > 0.5:
            err("script_sections", "%s 앞에 빈 구간이나 겹침(%s→%s)" % (s.get("section"), prev, st))
        prev = en
        if not s.get("points"):
            err("script_sections", "%s 내용(points) 없음" % s.get("section"))
    if secs and abs(prev - total) > 0.5:
        err("target_duration_sec", "마지막 구간 끝 %s초 ≠ 목표 %s초" % (prev, total))
    if secs and secs[0].get("section") == "훅" and isinstance(secs[0].get("end_sec"), (int, float)) \
            and secs[0]["end_sec"] > 3 and plan.get("format", "shorts") == "shorts":
        warn("script_sections", "쇼츠 훅이 3초를 넘음(%s초)" % secs[0]["end_sec"])

    titles = plan.get("titles") or []
    if len(titles) != 3 or len(set(titles)) != 3:
        err("titles", "서로 다른 제목 후보 3개")
    for t in titles:
        if len(t) > pcfg["title_max_chars"]:
            err("titles", "제목 %d자 — 유튜브 제목 상한 %d자" % (len(t), pcfg["title_max_chars"]))
        elif len(t) > 40:
            warn("titles", "「%s…」 %d자 — 쇼츠 피드에서 잘릴 수 있음" % (t[:12], len(t)))
    tags = plan.get("hashtags") or []
    if len(tags) > 15:
        err("hashtags", "해시태그 %d개 — 15개 이하로" % len(tags))
    elif len(tags) > 5:
        warn("hashtags", "해시태그 %d개 — 제목 위에는 앞 3개만 보임" % len(tags))

    tb = plan.get("thumbnail_brief") or {}
    if tb.get("aspect_ratio") not in ("9:16", "16:9"):
        err("thumbnail_brief", "aspect_ratio 는 9:16 또는 16:9")
    if not tb.get("text"):
        err("thumbnail_brief", "썸네일 문구(text) 없음")

    shots = plan.get("shot_list") or []
    if not shots:
        err("shot_list", "필요한 샷 목록 없음")
    for s in shots:
        if s.get("source") not in SHOT_SOURCES:
            err("shot_list", "%s source 는 %s 중 하나" % (s.get("shot"), " / ".join(SHOT_SOURCES)))

    cl = " ".join(plan.get("copyright_checklist") or [])
    for label, pat in COPYRIGHT_REQUIRED.items():
        if not re.search(pat, cl):
            err("copyright_checklist", "「%s」 관련 항목 없음" % label)

    sr = plan.get("score_reference") or {}
    if sr.get("note") != cfg["score"]["disclaimer"]:
        err("score_reference", "note 는 정확히 「%s」" % cfg["score"]["disclaimer"])
    if scores is not None:
        real = {t["topic_id"]: t["score"] for t in scores["topics"]}.get(plan.get("topic_id"))
        if real is not None and sr.get("topic_score") != real:
            err("score_reference", "topic_score %s ≠ 계산값 %s (점수는 코드 값을 그대로 쓴다)" % (sr.get("topic_score"), real))

    refs = plan.get("evidence_refs") or []
    if not refs:
        err("evidence_refs", "근거 경로 없음")
    if evidence is not None:
        for r in refs:
            if not resolve_ref(r, evidence, video_ids):
                err("evidence_refs", "존재하지 않는 근거 경로: %s" % r)
    if not plan.get("data_sources"):
        err("data_sources", "데이터 출처 없음")
    if is_sample:
        warn("data_sources", "샘플 데이터 기반 — 연습용. 공개용 기획안으로 쓰지 말 것")

    for p in find_predictions(_plan_text(plan)):
        err("prediction", "조회수·반응 예측 표현: 「%s」" % p)

    return {"passed": not errors, "errors": errors, "warnings": warnings}


def plan_to_markdown(plan: Dict, validation: Optional[Dict] = None) -> str:
    sr = plan.get("score_reference") or {}
    L = ["# 기획안 %s" % plan.get("plan_id", ""), "",
         "| 항목 | 내용 |", "|---|---|",
         "| 플랫폼 | YouTube %s |" % plan.get("format", ""),
         "| 주제 | %s |" % plan.get("topic_name", plan.get("topic_id", "")),
         "| 유형 | %s |" % plan.get("content_type", ""),
         "| 목표 길이 | %s초 |" % plan.get("target_duration_sec", ""),
         "| 주제 점수 | %s (%s) |" % (sr.get("topic_score"), sr.get("note")),
         "| 상태 | %s |" % plan.get("status", "draft"),
         "", "## 각도", plan.get("angle", ""), "", "## 기획 근거", plan.get("rationale", ""), "",
         "## 훅 3종"]
    for h in plan.get("hooks", []):
        mark = " ✅ 채택" if h.get("type") == plan.get("selected_hook") else ""
        L.append("- **%s**%s: %s" % (h.get("type"), mark, h.get("line")))
    L += ["", "## 구간별 대본", "| 구간 | 시간 | 내용 | 화면 |", "|---|---|---|---|"]
    for s in plan.get("script_sections", []):
        L.append("| %s | %s–%s초 | %s | %s |" % (s.get("section"), s.get("start_sec"), s.get("end_sec"),
                                              str(s.get("points", "")).replace("\n", " "),
                                              str(s.get("visual", "")).replace("\n", " ")))
    L += ["", "## 제목 후보"] + ["%d. %s" % (i + 1, t) for i, t in enumerate(plan.get("titles", []))]
    L += ["", "## 설명란", plan.get("description", ""), "", "해시태그: " + " ".join(plan.get("hashtags", []))]
    tb = plan.get("thumbnail_brief") or {}
    L += ["", "## 썸네일", "- 비율: %s" % tb.get("aspect_ratio"), "- 문구: %s" % tb.get("text"),
          "- 스타일: %s" % tb.get("style"), "", "## 필요한 샷"]
    L += ["- %s (%s): %s" % (s.get("shot"), s.get("source"), s.get("need")) for s in plan.get("shot_list", [])]
    L += ["", "## 저작권 체크리스트"] + ["- [ ] %s" % c for c in plan.get("copyright_checklist", [])]
    L += ["", "## 근거·출처"] + ["- `%s`" % r for r in plan.get("evidence_refs", [])]
    L += ["- %s (%s)" % (d.get("name"), d.get("origin")) for d in plan.get("data_sources", [])]
    if validation:
        rc = validation.get("rule_check", {})
        L += ["", "## 검증", "- 규칙 검사: %s" % ("통과" if rc.get("passed") else "실패")]
        L += ["  - ❌ %s: %s" % (e["field"], e["problem"]) for e in rc.get("errors", [])]
        L += ["  - ⚠️ %s: %s" % (w["field"], w["problem"]) for w in rc.get("warnings", [])]
        rv = validation.get("review")
        if rv:
            L.append("- 의미 검토: %s" % ("통과" if rv.get("passed") else "수정 필요"))
            L += ["  - %s: %s" % (i.get("field"), i.get("problem")) for i in rv.get("issues", [])]
    return "\n".join(L) + "\n"
