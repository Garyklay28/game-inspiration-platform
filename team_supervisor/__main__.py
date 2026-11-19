"""팀 총괄 슈퍼바이저 CLI.

  python -m team_supervisor --intent trend_scan --bilibili-dry-run
  python -m team_supervisor --intent deep_dive --game 英雄联盟
  python -m team_supervisor --intent deep_dive --platforms youtube --youtube-run 20261119-101500
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .contracts import PLATFORMS, TEAM_INTENTS, TeamTask
from .supervisor import TeamSupervisor


def main() -> int:
    ap = argparse.ArgumentParser(description="팀 총괄 슈퍼바이저 (빌리빌리 + YouTube)")
    ap.add_argument("--intent", choices=TEAM_INTENTS, default="trend_scan")
    ap.add_argument("--platforms", default=",".join(PLATFORMS), help="쉼표로 구분: bilibili,youtube")
    ap.add_argument("--game", help="빌리빌리 게임 이름")
    ap.add_argument("--topic", help="YouTube 주제 (참고용; YouTube 실행은 Claude Code 에서)")
    ap.add_argument("--title", help="title_check 용 중국어 제목")
    ap.add_argument("--youtube-run", help="YouTube 실행 폴더 id (기본: 최근)")
    ap.add_argument("--bilibili-dry-run", action="store_true", help="빌리빌리를 LLM 없이 실행")
    ap.add_argument("--out", help="저장 경로 (기본: outputs/team_report_<시각>.json)")
    a = ap.parse_args()

    task = TeamTask(intent=a.intent, platforms=tuple(p.strip() for p in a.platforms.split(",") if p.strip()),
                    game=a.game, topic=a.topic, title=a.title, youtube_run_id=a.youtube_run)
    rep = TeamSupervisor().run(task, bilibili_dry_run=a.bilibili_dry_run).to_dict()

    print("=== 팀 요약 ===\n" + rep["summary_ko"])
    if rep["warnings"]:
        print("\n=== 경고 ===\n- " + "\n- ".join(rep["warnings"]))
    out = Path(a.out) if a.out else Path("outputs") / ("team_report_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n저장: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
