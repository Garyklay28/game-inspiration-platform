"""策划案(기획안) 규격과 결정적 검증 규칙 (流水线设计 A 6단계 '校验'의 코드 부분).

LLM validator 는 이 규칙 검사 결과를 보고 의미 수준의 문제를 추가로 판단한다.
규칙 검사는 LLM 없이 항상 같은 결과를 내므로, 보고서에 '통과/실패'의 근거로 남긴다.
"""
import re
from typing import Dict, List, Optional

PLAN_SCHEMA_VERSION = "plan-v1"

# 流水线设计 문서의 4개 내용 유형
CONTENT_TYPES = ["攻略", "实况", "分析", "评测"]
# 분석 단계의 세분류(metrics.TYPE_RULES) → 기획안 content_type. None 은 기획 워커가 가장 가까운 것을 고른다.
CONTENT_TYPE_MAP = {"공략": "攻略", "실황": "实况", "리뷰·평가": "评测", "e스포츠": "分析", "PV·공식": "分析",
                    "밈·2차창작": None, "AI창작": None, "기타": None}
HOOK_TYPES = ["先看结果", "提问", "挑战/反转"]
SECTIONS = ["开场", "问题", "正文", "CTA", "结尾"]
SCORE_DISCLAIMER = "仅供排序参考，非播放量预测"

# 조회수·반응 '예측' 표현 (流水线设计: 播放量预测类表述 拦截). 과거 사실 인용("播放254万")은 허용.
PREDICTION_PATTERNS = [
    r"预计.{0,8}(播放|观看|涨粉|三连|爆)",
    r"(播放量?|观看量?|粉丝).{0,6}(将|会|能|可以|有望).{0,4}(达到|突破|超过|破)",
    r"(保证|稳|一定会?|必定|肯定会?).{0,4}(爆|火|上热门|破万|百万)",
    r"(예상|예측).{0,8}(조회|구독|반응)",
    r"(조회수|조회|구독자).{0,12}(달성할|돌파할|넘을|나올) (것|겁니다|수 있)",
    # 한글은 음절 단위라 '크+ㅂ니다'='큽니다', '크+ㄴ'='큰' 처럼 글자가 바뀐다 → 활용형을 모두 나열
    r"(조회|반응|배).{0,25}(가능성이 (크|큽|큰|높)|것으로 (예상|보입|보인))",
]
_PRED_RE = [re.compile(p) for p in PREDICTION_PATTERNS]

# 체크리스트에 반드시 다뤄야 하는 항목(정규식). 4차 실제 실행에서 '游戏与赛事画面'을 단순 키워드
# '游戏画面'으로 못 잡는 오판이 있어, 사이에 몇 글자가 끼어도 인식하도록 정규식으로 바꿈.
COPYRIGHT_REQUIRED = {
    "游戏画面": r"游戏.{0,6}(画面|素材|截图|录屏)|二创|二次创作|官方素材",
    "BGM": r"BGM|背景音乐|音乐|配乐|音源|歌曲",
    "他人素材": r"他人|第三方|转载|搬运|引用|片段|其他UP主|二次上传",
}


def find_prediction_phrases(text: str) -> List[str]:
    hits = []
    for rx in _PRED_RE:
        for m in rx.finditer(text or ""):
            hits.append(m.group(0))
    return hits


def _all_text(plan: Dict) -> str:
    parts = [h.get("line_zh", "") for h in plan.get("hooks", [])]
    parts += [s.get("points_zh", "") for s in plan.get("script_sections", [])]
    parts += list(plan.get("titles", []))
    tb = plan.get("thumbnail_brief") or {}
    parts += [tb.get("text_zh", ""), tb.get("style_zh", "")]
    return "\n".join(str(p) for p in parts)


def check_plan(plan: Dict, require_activity_tag: bool = False) -> Dict:
    """규칙 검사. 반환: {passed, errors[], warnings[]} — errors 가 있으면 실패."""
    errors, warnings = [], []

    def err(field, msg):
        errors.append({"field": field, "problem": msg})

    if plan.get("content_type") not in CONTENT_TYPES:
        err("content_type", "必须是 %s 之一" % "/".join(CONTENT_TYPES))

    hooks = plan.get("hooks") or []
    if sorted(h.get("type") for h in hooks) != sorted(HOOK_TYPES):
        err("hooks", "需要 3 种钩子各一个: %s" % ", ".join(HOOK_TYPES))
    if plan.get("selected_hook") not in HOOK_TYPES:
        err("selected_hook", "必须是 hooks 中的一种类型")

    titles = plan.get("titles") or []
    if len(titles) != 3 or len(set(titles)) != 3:
        err("titles", "需要 3 个互不相同的标题候选")
    for t in titles:
        if not 8 <= len(t) <= 80:
            warnings.append({"field": "titles", "problem": "标题长度 %d 字，B站标题上限 80 字" % len(t)})

    secs = plan.get("script_sections") or []
    names = [s.get("section") for s in secs]
    if names != SECTIONS:
        err("script_sections", "段落顺序必须是 %s" % " → ".join(SECTIONS))
    total = plan.get("target_duration_sec") or 0
    prev_end = 0
    for s in secs:
        st, en = s.get("start_sec"), s.get("end_sec")
        if not isinstance(st, (int, float)) or not isinstance(en, (int, float)) or st >= en:
            err("script_sections", "%s 的起止时间无效" % s.get("section"))
            continue
        if abs(st - prev_end) > 1:
            err("script_sections", "%s 与上一段之间有空档或重叠(%s→%s)" % (s.get("section"), prev_end, st))
        prev_end = en
    if secs and total and abs(prev_end - total) > 1:
        err("target_duration_sec", "最后一段结束于 %ss，与目标时长 %ss 不一致" % (prev_end, total))

    tb = plan.get("thumbnail_brief") or {}
    if tb.get("aspect_ratio") not in ("16:9", "4:3", "9:16"):
        err("thumbnail_brief", "aspect_ratio 需为 16:9 / 4:3 / 9:16")
    if not tb.get("text_zh"):
        err("thumbnail_brief", "缺少缩略图文案")

    checklist = " ".join(plan.get("copyright_checklist") or [])
    for label, pattern in COPYRIGHT_REQUIRED.items():
        if not re.search(pattern, checklist):
            err("copyright_checklist", "缺少「%s」相关检查项" % label)

    sr = plan.get("score_reference") or {}
    if sr.get("note") != SCORE_DISCLAIMER:
        err("score_reference", "必须标注「%s」" % SCORE_DISCLAIMER)
    if not plan.get("data_sources"):
        err("data_sources", "缺少数据来源")

    for phrase in find_prediction_phrases(_all_text(plan)):
        err("prediction", "出现播放量/反响预测类表述: 「%s」" % phrase)

    if require_activity_tag and not (plan.get("platform_extras") or {}).get("activity_mission_id"):
        warnings.append({"field": "platform_extras", "problem": "该游戏有官方活动，但策划案未填写活动 ID"})

    return {"passed": not errors, "errors": errors, "warnings": warnings}


def plan_to_markdown(plan: Dict, validation: Optional[Dict] = None) -> str:
    """策划案 JSON → 团队共享用 Markdown (LLM 미사용)."""
    L = ["# 策划案 %s" % plan.get("plan_id", ""), "",
         "| 项目 | 内容 |", "|---|---|",
         "| 平台 | %s |" % plan.get("platform", ""),
         "| 游戏 | %s |" % plan.get("game", ""),
         "| 内容类型 | %s |" % plan.get("content_type", ""),
         "| 目标时长 | %s 秒 |" % plan.get("target_duration_sec", ""),
         "| 分数 | %s（%s） |" % ((plan.get("score_reference") or {}).get("score"), SCORE_DISCLAIMER)]
    ex = plan.get("platform_extras") or {}
    if ex.get("activity_mission_id"):
        L.append("| 官方活动 ID | %s |" % ex["activity_mission_id"])
    if ex.get("tags_zh"):
        L.append("| 标签 | %s |" % " / ".join(ex["tags_zh"]))
    L += ["", "## 选题依据", plan.get("rationale_zh", ""), "", "## 开场钩子（3 种）"]
    for h in plan.get("hooks", []):
        mark = " ✅ 采用" if h.get("type") == plan.get("selected_hook") else ""
        L.append("- **%s**%s：%s" % (h.get("type"), mark, h.get("line_zh")))
    L += ["", "## 分段脚本", "| 段落 | 时间 | 要点 |", "|---|---|---|"]
    for s in plan.get("script_sections", []):
        L.append("| %s | %s–%ss | %s |" % (s.get("section"), s.get("start_sec"), s.get("end_sec"),
                                         str(s.get("points_zh", "")).replace("\n", " ")))
    L += ["", "## 标题候选"] + ["%d. %s" % (i + 1, t) for i, t in enumerate(plan.get("titles", []))]
    tb = plan.get("thumbnail_brief") or {}
    L += ["", "## 缩略图 brief", "- 比例：%s" % tb.get("aspect_ratio"), "- 文案：%s" % tb.get("text_zh"),
          "- 风格：%s" % tb.get("style_zh"), "", "## 版权检查清单"]
    L += ["- [ ] %s" % c for c in plan.get("copyright_checklist", [])]
    L += ["", "## 数据来源"] + ["- %s（%s）" % (d.get("name"), d.get("origin")) for d in plan.get("data_sources", [])]
    if validation:
        L += ["", "## 校验结果", "- 规则检查：%s" % ("通过" if validation.get("rule_check", {}).get("passed") else "未通过")]
        for e in validation.get("rule_check", {}).get("errors", []):
            L.append("  - ❌ %s：%s" % (e["field"], e["problem"]))
        if validation.get("reviewer"):
            r = validation["reviewer"]
            L.append("- 审核意见：%s" % ("通过" if r.get("passed") else "需修改"))
            for i in r.get("issues", []):
                L.append("  - %s：%s" % (i.get("field"), i.get("problem")))
    return "\n".join(L) + "\n"
