"""공용: 설정 읽기, 실행 폴더(runs/<run_id>/), JSON 입출력, 실행 기록(trace).

모든 단계는 앞 단계의 파일을 읽고 자기 파일을 쓴다. 세션이 바뀌어도 파일만 있으면 이어서 돌릴 수 있다.
"""
import datetime as _dt
import json
import os
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
RUNS_DIR = ROOT / "runs"
PERF_DIR = ROOT / "performance"

# 단계별 산출물 파일 이름 (번호 = 파이프라인 순서)
FILES = {
    "raw": "01_raw.json",
    "normalized": "02_normalized.json",
    "scores": "03_scores.json",
    "evidence": "04_evidence.json",      # 코드가 만든 분석 근거 팩
    "analysis": "04_analysis.json",      # trend-analyst 에이전트의 해석
    "plan": "05_plan.json",              # plan-writer 에이전트의 기획안
    "plan_md": "05_plan.md",
    "validation": "06_validation.json",  # 규칙 검사 + plan-validator 검토
    "report": "report.json",             # 팀 총괄 슈퍼바이저에게 넘기는 YouTubeReport
    "trace": "trace.jsonl",
}


def load_config(name: str = "pipeline.json") -> Dict[str, Any]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def load_env() -> None:
    """.env 를 읽는다(python-dotenv 가 없으면 직접 파싱). 키 값은 출력하지 않는다."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def new_run_id() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def run_dir(run_id: str, create: bool = False) -> Path:
    d = RUNS_DIR / run_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    elif not d.exists():
        raise FileNotFoundError("실행 폴더가 없습니다: %s (먼저 collect 를 실행하세요)" % d)
    return d


def latest_run_id() -> Optional[str]:
    if not RUNS_DIR.exists():
        return None
    runs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))
    return runs[-1] if runs else None


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_stage(run_id: str, key: str) -> Any:
    p = run_dir(run_id) / FILES[key]
    if not p.exists():
        raise FileNotFoundError("%s 이(가) 없습니다. 앞 단계를 먼저 실행하세요." % p.name)
    return read_json(p)


def write_stage(run_id: str, key: str, data: Any) -> Path:
    return write_json(run_dir(run_id, create=True) / FILES[key], data)


def trace(run_id: str, stage: str, message: str, ok: bool = True, **extra) -> None:
    """단계 실행 기록. 무엇을 했고 성공했는지 한 줄씩 남긴다."""
    rec = {"at": now_iso(), "stage": stage, "ok": ok, "message": message}
    rec.update(extra)
    p = run_dir(run_id, create=True) / FILES["trace"]
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def median(values: List[float], default: float = 0.0) -> float:
    return statistics.median(values) if values else default


def rnd(d: Dict, nd: int = 4) -> Dict:
    return {k: (round(v, nd) if isinstance(v, float) else v) for k, v in d.items()}
