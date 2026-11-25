"""CLI 데모: 총괄 슈퍼바이저를 흉내 내어 BiliTask 하나를 보내고 BiliReport 를 출력한다.

예)
  python main.py --intent trend_scan                       # Aside CSV(있으면) → 6단계 에이전트
  python main.py --intent game_deep_dive --game 英雄联盟 --db-export
  python main.py --intent title_check --title "【S16】BLG夺冠全过程复盘"
  python main.py --intent performance_review
  python main.py --intent trend_scan --dry-run             # API 키 없이 데이터 파이프라인만
  python main.py register-upload --bvid BV1xx --report outputs/report_x.json   # 올린 영상을 기획안과 연결
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from bili_agent.agents.supervisor import BiliSupervisor
from bili_agent.agents.workers.w6_performance import register_upload
from bili_agent.contracts import INTENTS, BiliTask
from bili_agent.tools import team_db
from bili_agent.tools.plan_rules import plan_to_markdown


def cmd_register(argv) -> int:
    ap = argparse.ArgumentParser(prog="main.py register-upload", description="업로드한 영상을 기획안과 연결 (6 성과 기록)")
    ap.add_argument("--bvid", required=True)
    ap.add_argument("--report", required=True, help="기획안이 들어 있는 BiliReport JSON")
    a = ap.parse_args(argv)
    row = register_upload(a.bvid, json.loads(Path(a.report).read_text(encoding="utf-8")))
    print("등록: %s ↔ %s" % (row["bvid"], row["plan_id"]))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "register-upload":
        return cmd_register(sys.argv[2:])
    ap = argparse.ArgumentParser(description="빌리빌리 서브 슈퍼바이저 (수직 구조, 에이전트 6개)")
    ap.add_argument("--intent", choices=INTENTS, default="trend_scan")
    ap.add_argument("--game", help="게임 이름(한·중·영)")
    ap.add_argument("--title", help="title_check 용 중국어 제목")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 기본 계획을 코드로 실행")
    ap.add_argument("--db-export", action="store_true", help="팀 공용 DB(13장) 행을 JSON 으로 저장")
    ap.add_argument("--db-push", action="store_true", help="팀 공용 DB 에 upsert (SUPABASE_URL·SERVICE_ROLE_KEY 필요)")
    ap.add_argument("--out", help="보고서 JSON 저장 경로(기본: outputs/report_<시각>.json)")
    args = ap.parse_args()

    task = BiliTask(intent=args.intent, game=args.game, user_title=args.title, period_days=args.days)
    sup = BiliSupervisor()
    report = sup.run_dry(task) if args.dry_run else sup.run(task)
    data = report.to_dict()

    print("\n=== 에이전트 실행 기록 ===")
    for row in data["agent_trace"]:
        print("%6.1fs %-16s %-30s %s%s" % (row["t"], row["agent"], row["event"], "" if row["ok"] else "[ERROR] ", row["detail"]))
    print("\n=== 단계별 결과 ===")
    for k, v in data["agent_stages"].items():
        print("- %s: %s" % (k, v))
    print("\n=== 요약 ===\n" + data["summary_ko"])
    u = data.get("usage") or {}
    if u.get("llm_calls"):
        print("\n=== 사용량 ===\nLLM 호출 %d회, 입력 %d 토큰, 출력 %d 토큰, 추정 비용 $%s" % (
            u["llm_calls"], u["input_tokens"], u["output_tokens"], u.get("estimated_cost_usd", "?")))
    if data["warnings"]:
        print("\n=== 경고 ===\n- " + "\n- ".join(data["warnings"]))

    out = Path(args.out) if args.out else Path("outputs") / ("report_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n보고서 저장: %s" % out)
    if data.get("plan"):
        stem = out.with_name(out.stem + "_plan")
        stem.with_suffix(".json").write_text(json.dumps(data["plan"], ensure_ascii=False, indent=2), encoding="utf-8")
        stem.with_suffix(".md").write_text(plan_to_markdown(data["plan"], data.get("plan_validation")), encoding="utf-8")
        print("策划案 저장: %s.json / .md (status=%s)" % (stem, data["plan"].get("status")))
    if args.db_export or args.db_push:
        rows = team_db.build_rows(sup.last_ws, data)
        counts = team_db.export(rows, out.with_name(out.stem + "_db_rows.json"))
        print("팀 DB 행 저장: %s" % counts)
        if args.db_push:
            print("팀 DB upsert: %s" % team_db.push(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
