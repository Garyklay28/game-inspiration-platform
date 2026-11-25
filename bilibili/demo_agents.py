"""에이전트별 Proof of Concept 데모 — 에이전트 하나씩 「입력 → 코드가 한 일 → LLM 결과」를 보여 준다.

  python demo_agents.py --agent collector          # 1 수집
  python demo_agents.py --agent analyst            # 4 분석 (기본: 실제 실행 기록 재생, 비용 0)
  python demo_agents.py --agent analyst --live     # 4 분석을 Claude 로 지금 다시 실행 (앞 단계는 코드·기록으로 준비)
  python demo_agents.py --all                      # 6개 전부
  python demo_agents.py --all --markdown docs/agent_outputs.md   # 문서로 저장

데이터
- 1~3 단계와 4·5 단계의 '코드 도구' 결과는 data/aside/ 의 실제 Aside 수집(2026-11-25)으로 지금 다시 계산한다.
- 4·5 단계의 LLM 결과는 2026-11-25 실제 실행 기록(docs/example_report_six_agents.json)을 그대로 보여 준다(--live 가 아니면).
- 6 성과 기록은 아직 올린 영상이 없어 **가상의 예시 데이터**로 보여 준다(임시 폴더, 저장소 데이터는 건드리지 않음).
"""
import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

from bili_agent import config
from bili_agent.agents.supervisor import BiliSupervisor
from bili_agent.agents.workers import WORKERS
from bili_agent.agents.workers import w6_performance as perf
from bili_agent.agents.workers.w4_analyst import (h_get_duration_type_distribution, h_get_engagement_ranking,
                                                  h_get_event_signals, h_get_hot_keyword_signals)
from bili_agent.agents.workers.w5_planner import h_get_plan_context
from bili_agent.contracts import BiliTask
from bili_agent.workspace import Workspace

ROOT = Path(__file__).resolve().parent
RUN_FILE = ROOT / "docs/example_report_six_agents.json"
DB_FILE = ROOT / "docs/example_team_db_rows.json"
ORDER = ["collector", "normalizer", "scorer", "analyst", "planner", "performance"]
RECORD = "실제 실행 기록 2026-11-25 (claude-sonnet-5-5)"


class Out:
    """터미널 출력과 Markdown 문서를 같은 내용으로 만든다."""

    def __init__(self):
        self.lines = []

    def h1(self, s):
        self.lines += ["", "## " + s, ""]

    def h2(self, s):
        self.lines += ["", "**" + s + "**", ""]

    def p(self, s):
        self.lines.append(s)

    def li(self, s):
        self.lines.append("- " + s)

    def table(self, cols, rows):
        self.lines.append("")
        self.lines.append("| " + " | ".join(cols) + " |")
        self.lines.append("|" + "---|" * len(cols))
        for r in rows:
            self.lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in r) + " |")
        self.lines.append("")

    def text(self):
        return "\n".join(self.lines) + "\n"


def load_record():
    return json.loads(RUN_FILE.read_text(encoding="utf-8")), json.loads(DB_FILE.read_text(encoding="utf-8"))


def prepare(upto: str, rec: dict):
    """upto 앞 단계까지 작업 공간을 준비한다: 코드 부분은 지금 다시 실행, LLM 부분은 실제 실행 기록을 넣는다."""
    sup = BiliSupervisor()
    ws = sup.last_ws = Workspace(BiliTask(intent="trend_scan"), sup.alias)
    stages = rec["agent_stages"]
    for name in ORDER[:ORDER.index(upto)]:
        spec = WORKERS[name]
        if name == "collector":
            h = spec.handlers
            a = h["load_aside"](ws)
            if not a["videos"].get("used") or a["videos"]["freshness"]["need_supplement"]:
                h["collect_popular_games"](ws)
            h["collect_trending"](ws)
            ws.cache["demo_collector"] = a
            ws.findings[name] = {"summary_ko": stages.get(name, "")}
        elif name == "normalizer":
            spec.pre_run(ws)
            ws.findings[name] = {"summary_ko": stages.get(name, ""), "alias_candidates": rec["alias_candidates"]}
        elif name == "scorer":
            spec.run_code(ws)
        elif name == "analyst":
            ws.findings[name] = {"summary_ko": stages.get(name, ""), "opportunities": rec["opportunities"],
                                 "events": rec["events"], "duration_advice": rec.get("duration_advice"),
                                 "overseas_trend_cards": rec["overseas_trend_cards"]}
        elif name == "planner":
            ws.findings[name] = {"summary_ko": stages.get(name, "")}
    return sup, ws


def live(sup, ws, agent: str, out: Out):
    from bili_agent.agents.loop import LLM
    sup.llm = LLM()
    res = sup._delegate(ws, agent, "에이전트별 데모: 이 단계의 역할대로 처리하세요. (intent=trend_scan)")
    u = ws.cache.get("usage") or {}
    out.h2("LLM 결과 (지금 실행, --live)")
    out.p("```json\n" + json.dumps(res, ensure_ascii=False, indent=1, default=str)[:4000] + "\n```")
    out.li("LLM 호출 %s회, 입력 %s · 출력 %s 토큰" % (u.get("llm_calls"), u.get("input_tokens"), u.get("output_tokens")))


# ── 에이전트별 화면 ─────────────────────────────────────

def demo_collector(out, ws, rec, db):
    a = ws.cache["demo_collector"]
    v = a["videos"]
    if not v.get("used"):
        out.p("Aside 파일이 없거나 오래돼 공개 API 로 수집했습니다: " + ", ".join(s["name"] for s in ws.data_sources))
        return
    out.h2("입력")
    out.li("Aside 수집 파일 `data/aside/%s` (수집 후 %.1f시간)" % (v.get("file"), v.get("age_h", 0)))
    out.li("기준: 파일 %d시간 이내 · 영상 게시 %d일 이내 · 신선한 영상 %d개 미만이면 공개 API 보충" % (
        config.ASIDE_MAX_AGE_H, config.MAX_VIDEO_AGE_DAYS, config.MIN_FRESH_VIDEOS))
    out.h2("코드가 한 일 (도구 결과)")
    out.table(["출처", "영상", "게시일 범위", "30일 초과"],
              [(s, r["count"], "%s ~ %s" % (r["oldest"], r["newest"]), r["old"]) for s, r in v["freshness"]["by_source"].items()])
    out.li("핫키워드 %d개 (Aside %d개 + 공개 API 핫서치 보충)" % (len(ws.keywords), a["keywords"].get("count", 0)))
    out.li("공식 활동·화제 %d개: %s" % (len(ws.aside_events), ", ".join(e["name"] for e in ws.aside_events[:4])))
    out.li("데이터 출처 기록: " + ", ".join("%s(%s)" % (s["name"], s.get("origin")) for s in ws.data_sources))
    out.h2("LLM 결과 — " + RECORD)
    out.p("> " + rec["agent_stages"]["collector"])
    for w in rec["warnings"]:
        if w.startswith("collector:"):
            out.li(w)


def demo_normalizer(out, ws, rec, db):
    n = ws.cache["normalize"]
    out.h2("입력")
    out.li("1 수집 결과 영상 %d개 + 별칭 사전 %d개 게임 (`data/alias_dictionary.json`)" % (len(ws.raw_videos), len(ws.alias.games)))
    out.h2("코드가 한 일")
    out.table(["항목", "값"], [("정규화 후 영상", n["videos"]), ("게임 매칭", n["matched_to_game"]), ("미매칭", n["unmatched"]),
                              ("30일 초과로 제외", n["old_videos_dropped"]), ("중복 제거", n["duplicates_removed"])])
    um = WORKERS["normalizer"].handlers["list_unmatched_titles"](ws, n=5)["titles"]
    out.li("미매칭 상위: " + " / ".join(t["title"][:22] for t in um))
    out.h2("LLM 결과 — 별칭 후보 제안 (" + RECORD + ", 사람 검토 후 사전에 반영)")
    out.table(["중국어", "한국어", "근거 제목"],
              [(c["zh"], c.get("ko") or "(모름 — 비워 둠)", c.get("evidence_title", "")[:30]) for c in rec["alias_candidates"]])


def demo_scorer(out, ws, rec, db):
    s = ws.cache["game_scores"]
    out.h2("입력")
    out.li("정규화된 영상 %d개, 핫키워드 %d개, Aside 공식 활동 %d개" % (len(ws.videos), len(ws.keywords), len(ws.aside_events)))
    out.h2("코드가 한 일 — Score_bili = 수요 + 아웃라이어 + 신선도 − 경쟁도 (LLM 없음, 정렬 참고용)")
    out.table(["게임", "점수", "수요", "아웃라이어", "신선도", "경쟁도", "영상 수"],
              [(x["game_ko"], x["score"], x["components"]["demand"], x["components"]["outlier"],
                x["components"]["freshness"], x["components"]["competition"], x["videos_in_pool"]) for x in s[:8]])
    out.p("※ 신선도는 지금 시각 기준으로 다시 계산되므로 실제 실행 당시 값과 조금 다를 수 있습니다.")


def demo_analyst(out, ws, rec, db):
    out.h2("코드 도구 결과 (에이전트가 보는 숫자)")
    ev = h_get_event_signals(ws)
    out.li("공식 활동 참여 영상 비율 %.0f%% · 상위 활동: %s" % (ev["mission_video_share"] * 100, ", ".join(
        "%s %s(%d개)" % (e["game_zh"], e["mission_id"], e["videos"]) for e in ev["mission_events"][:3])))
    kw = h_get_hot_keyword_signals(ws)
    out.li("핫키워드 %d개 중 게임 관련 %d개: %s" % (kw["total_keywords"], kw["game_related"],
                                              ", ".join(x["keyword"] for x in kw["signals"][:4])))
    er = h_get_engagement_ranking(ws, top=3)
    out.li("반응률 상위: " + " / ".join("%s (배수 %.2f)" % (t["title"][:18], t["engagement_multiple"]) for t in er["top"]))
    du = h_get_duration_type_distribution(ws)
    out.li("길이 정보가 있는 영상 %d개 / 없는 영상 %d개 (Aside JSON 에는 길이가 없음)" % (
        du["videos_with_duration"], du["videos_without_duration"]))
    out.h2("LLM 결과 — " + RECORD)
    out.p("> " + rec["agent_stages"]["analyst"])
    out.table(["기회 게임", "점수", "이유"], [(o.get("game_ko") or o["game_zh"], o.get("score"), o["reason_ko"][:60]) for o in rec["opportunities"]])
    out.h2("이벤트 신호")
    for e in rec["events"][:4]:
        out.li("[%s] %s — %s" % (e["kind"], e.get("game_zh", ""), e["recommendation_ko"][:80]))
    out.h2("해외 트렌드 카드 (YouTube·TikTok 모드로 전달)")
    out.table(["원제(중)", "한국어 제목", "왜 지금"], [(c["title_zh"][:26], c["title_ko"][:30], c["why_ko"][:50]) for c in rec["overseas_trend_cards"]])
    out.h2("분석 주장과 근거 (DB analyses.claims)")
    for c in db["analyses"][0]["claims"][:4]:
        out.li("%s  ← %s" % (c["claim_ko"][:70], "; ".join(c["evidence"])[:90]))


def demo_planner(out, ws, rec, db):
    plan, val = rec["plan"], rec["plan_validation"]
    ctx = h_get_plan_context(ws, game_id=plan["game_id"])
    out.h2("입력 (get_plan_context)")
    out.li("대상 게임 %s · 점수 %s · 공식 활동 %s" % (ctx["game"]["zh"], (ctx["score"] or {}).get("score"),
                                              [a["mission_id"] for a in ctx["official_activities"]]))
    out.li("제목 벤치마크: 중앙값 %s자 · 【】 %.0f%%" % (ctx["title_benchmark"]["median_length"], ctx["title_benchmark"]["pct_square_brackets"] * 100))
    out.h2("흐름: 작성(LLM) → 규칙 검사(코드) → 검토(LLM), 실패 시 1회 수정")
    for t in rec["agent_trace"]:
        if t["event"] == "validation":
            out.li(t["detail"])
    out.h2("LLM 결과 — 策划案 (" + RECORD + ", status=%s)" % plan["status"])
    out.table(["항목", "내용"], [
        ("plan_id", plan["plan_id"]), ("내용 유형 / 길이", "%s / %s초" % (plan["content_type"], plan["target_duration_sec"])),
        ("선택한 훅", "%s — %s" % (plan["selected_hook"], next(h["line_zh"] for h in plan["hooks"] if h["type"] == plan["selected_hook"]))),
        ("제목 후보", " / ".join(plan["titles"])),
        ("구간", " → ".join("%s %s-%ss" % (s["section"], s["start_sec"], s["end_sec"]) for s in plan["script_sections"])),
        ("공식 활동·태그", "%s · %s" % ((plan.get("platform_extras") or {}).get("activity_mission_id"), ", ".join((plan.get("platform_extras") or {}).get("tags_zh", [])))),
        ("저작권 체크", len(plan["copyright_checklist"])), ("점수 표기", plan["score_reference"]["note"]),
        ("규칙 검사 / 검토", "%s / %s" % (val["rule_check"]["passed"], val["reviewer"]["passed"])),
    ])
    out.p("전체 기획안 문서: `docs/example_plan_six_agents.md`")


def demo_performance(out, ws, rec, db):
    out.p("> ⚠️ **가상의 예시 데이터**입니다. 아직 기획안대로 영상을 올리지 않아 실제 성과가 없습니다. "
          "실제로는 `main.py register-upload` → Aside 로 성과 수집(`*performance*.csv`) 후 실행합니다.")
    tmp = Path(tempfile.mkdtemp(prefix="bili_perf_demo_"))
    config.PERFORMANCE_DIR, config.ASIDE_DIR = tmp / "performance", tmp / "aside"
    config.ASIDE_DIR.mkdir(parents=True)
    plan = rec["plan"]
    rows = ["bvid,수집시각,조회수,좋아요,코인,즐겨찾기,댓글"]
    for i in range(9):  # 가상 업로드 9개: 수요가 높을수록 조회수가 높게 만든 예시
        comp = {"demand": round(0.2 + 0.08 * i, 2), "outlier": 0.5, "freshness": 0.6 + 0.02 * (i % 3), "competition": 0.4}
        rep = {"plan": dict(plan, plan_id="%s-예시%d" % (plan["plan_id"], i + 1),
                            score_reference={"score": None, "components": comp})}
        perf.register_upload("BV_EXAMPLE_%02d" % (i + 1), rep)
        views = int(3000 * math.exp(0.35 * i))
        rows.append("BV_EXAMPLE_%02d,2026-11-28 12:00,%d,%d,%d,%d,%d" % (i + 1, views, views // 12, views // 40, views // 30, views // 90))
    (config.ASIDE_DIR / "bilibili_performance_example.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    h = WORKERS["performance"].handlers
    up = h["list_uploads"](ws)
    out.h2("코드가 한 일 (예시 데이터)")
    out.table(["bvid", "기획안", "최신 조회수"], [(u["bvid"], u["plan_id"].rsplit("-", 1)[-1], u["latest"]["view"]) for u in up["uploads"][:5]])
    out.li("… 등록 %d개, 성과 있는 영상 %d개" % (len(up["uploads"]), up["with_data"]))
    w = h["propose_weights"](ws)
    out.li("가중치 보정안(8개 이상일 때): 상관 %s → 제안 가중치 %s" % (w.get("correlation_with_log_views"), w.get("proposed_weights")))
    out.li(w.get("note", ""))
    out.h2("LLM 결과")
    out.p("이 단계의 LLM 해석은 실제 성과가 쌓인 뒤에 실행합니다. 예시 데이터로 보려면 `--agent performance --live`.")


DEMOS = {"collector": demo_collector, "normalizer": demo_normalizer, "scorer": demo_scorer,
         "analyst": demo_analyst, "planner": demo_planner, "performance": demo_performance}


def main() -> int:
    ap = argparse.ArgumentParser(description="에이전트별 PoC 데모")
    ap.add_argument("--agent", choices=ORDER)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--live", action="store_true", help="해당 에이전트를 Claude 로 지금 다시 실행 (과금)")
    ap.add_argument("--markdown", help="결과를 Markdown 파일로 저장")
    a = ap.parse_args()
    if not a.agent and not a.all:
        ap.error("--agent 또는 --all 이 필요합니다")
    if a.live and a.all:
        ap.error("--live 는 에이전트 하나씩만 (--agent)")
    rec, db = load_record()
    out = Out()
    if a.markdown:
        out.p("# 에이전트별 Proof of Concept 결과 (빌리빌리 파트, 1차 결과물)")
        out.p("")
        out.p("`python demo_agents.py --all --markdown docs/agent_outputs.md` 로 생성. 코드 도구 결과는 실제 Aside 수집 데이터로 다시 계산했고, "
              "LLM 결과는 %s 입니다. 6 성과 기록만 가상의 예시 데이터입니다." % RECORD)
    for name in (ORDER if a.all else [a.agent]):
        spec = WORKERS[name]
        out.h1("%s · %s  (%s, DB: %s)" % (spec.stage, name, "LLM" if spec.uses_llm else "코드만", ", ".join(spec.db_tables)))
        sup, ws = prepare(name, rec)
        if name == "collector":
            a_ = ws.cache["demo_collector"] = WORKERS["collector"].handlers["load_aside"](ws)
            if not a_["videos"].get("used") or a_["videos"]["freshness"]["need_supplement"]:
                WORKERS["collector"].handlers["collect_popular_games"](ws)
            WORKERS["collector"].handlers["collect_trending"](ws)
        elif name == "normalizer":
            WORKERS["normalizer"].pre_run(ws)
        elif name == "scorer":
            WORKERS["scorer"].run_code(ws)
        DEMOS[name](out, ws, rec, db)
        if a.live and spec.uses_llm:
            live(sup, ws, name, out)
    text = out.text()
    if a.markdown:
        Path(a.markdown).write_text(text, encoding="utf-8")
        print("저장: %s" % a.markdown)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
