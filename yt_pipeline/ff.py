"""ffmpeg / ffprobe 얇은 래퍼. 모든 명령은 실행 전에 문자열로 보여 줄 수 있게 리스트로 만든다."""
import json
import shlex
import shutil
import subprocess
from typing import Dict, List, Optional


class FFError(RuntimeError):
    pass


def require() -> None:
    for b in ("ffmpeg", "ffprobe"):
        if not shutil.which(b):
            raise FFError("%s 이 없습니다. macOS: brew install ffmpeg / Windows: winget install ffmpeg" % b)


def show(cmd: List[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)


def run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise FFError("명령 실패(%d): %s\n%s" % (p.returncode, show(cmd)[:300], p.stderr[-1500:]))
    return p


def probe(path: str) -> Dict:
    """해상도·fps·길이·코덱·오디오 유무."""
    p = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,duration",
             "-of", "json", path])
    d = json.loads(p.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    fps = None
    if v and v.get("avg_frame_rate", "0/0") != "0/0":
        n, m = v["avg_frame_rate"].split("/")
        fps = round(float(n) / float(m), 3) if float(m) else None
    return {"path": path, "duration": round(float(d.get("format", {}).get("duration", 0) or 0), 3),
            "width": v and v.get("width"), "height": v and v.get("height"), "fps": fps,
            "vcodec": v and v.get("codec_name"), "has_audio": a is not None, "acodec": a and a.get("codec_name")}


def duration(path: str) -> float:
    return probe(path)["duration"]


def detect(path: str, filt: str, kind: str = "a") -> str:
    """silencedetect / blackdetect / volumedetect 의 stderr 로그를 돌려준다."""
    flag = "-af" if kind == "a" else "-vf"
    return run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, flag, filt, "-f", "null", "-"]).stderr


def extract_frame(path: str, t: float, out: str, width: Optional[int] = 540) -> str:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % t, "-i", path, "-frames:v", "1"]
    if width:
        cmd += ["-vf", "scale=%d:-2" % width]
    run(cmd + [out])
    return out
