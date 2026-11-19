"""플랫폼 파트 호출부. 각 파트 코드는 그대로 두고, 여기서 불러 쓰기만 한다.

- 빌리빌리: Python 에서 바로 호출 가능 (Anthropic SDK 로 슈퍼바이저·워커가 돈다).
- YouTube : LLM 단계(분석·기획·검증·대본·검수)가 Claude Code 서브에이전트라 Python 에서 부를 수 없다.
            그래서 Claude Code 에서 /youtube-pipeline 으로 만든 실행 폴더(runs/<id>)를 읽어
            팀원 코드의 report.build 로 YouTubeReport 를 만든다.
"""
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
BILIBILI_DIR = ROOT / "bilibili"
YOUTUBE_DIR = ROOT / "youtube"


def _import_path(p: Path) -> None:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def run_bilibili(intent: str, game: Optional[str] = None, title: Optional[str] = None,
                 task_id: str = "team-demo", dry_run: bool = False) -> Dict[str, Any]:
    """빌리빌리 서브 슈퍼바이저 실행 → BiliReport(dict)."""
    _import_path(BILIBILI_DIR)
    from bili_agent.agents.supervisor import BiliSupervisor
    from bili_agent.contracts import BiliTask

    task = BiliTask(intent=intent, game=game, user_title=title, task_id=task_id)
    sup = BiliSupervisor()
    return (sup.run_dry(task) if dry_run else sup.run(task)).to_dict()


def load_youtube(intent: str, run_id: Optional[str] = None, task_id: str = "team-demo") -> Optional[Dict[str, Any]]:
    """YouTube 실행 폴더에서 YouTubeReport(dict)를 만든다. 실행 기록이 없으면 None."""
    _import_path(YOUTUBE_DIR)
    from yt_pipeline import common, report

    rid = run_id or common.latest_run_id()
    if not rid or not common.run_dir(rid).exists():
        return None
    report.build(rid, intent=intent, task_id=task_id)  # 팀원 코드 그대로 사용 (runs/<id>/report.json 생성)
    return common.read_json(common.run_dir(rid) / common.FILES["report"])
