"""5단계 안 · 썸네일 이미지 생성 (기획안 에이전트가 쓰는 도구).

  thumbnail --run ID                 05_plan.json 의 thumbnail_brief 로 이미지 프롬프트를 만들고,
                                     provider 가 openai 면 배경 이미지를 생성한 뒤 문구를 얹는다
  thumbnail --run ID --background F  가지고 있는 이미지(직접 찍은 게임 화면 등)에 문구만 얹는다

결과: runs/<id>/05_thumbnails/thumb_vN.png 와 thumb_vN.json (프롬프트·모델·출처 기록)
- 이미지 모델은 글자를 자주 틀리게 그리므로, 문구는 이미지에 그리게 하지 않고 FFmpeg 로 따로 얹는다.
- 프롬프트에 게임 로고, 실존 인물, 저작권 있는 캐릭터를 넣지 않는다(설정의 thumbnail.avoid).
- 기획안이 validated 가 아니면 만들지 않는다. API 호출은 과금되므로 사람이 승인한 뒤 실행한다.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from . import ff
from .common import ROOT, load_config, load_env, now_iso, read_json, read_stage, run_dir, trace, write_json

OPENAI_URL = "https://api.openai.com/v1/images/generations"


class ThumbnailError(RuntimeError):
    pass


def tdir(run_id: str) -> Path:
    d = run_dir(run_id) / "05_thumbnails"
    d.mkdir(exist_ok=True)
    return d


def _next_version(d: Path) -> int:
    ns = [int(m.group(1)) for p in d.glob("thumb_v*.png") for m in [re.search(r"_v(\d+)\.png$", p.name)] if m]
    return max(ns, default=0) + 1


def build_prompt(plan: Dict, cfg: Dict) -> Dict:
    tb = plan.get("thumbnail_brief") or {}
    ratio = tb.get("aspect_ratio", "9:16")
    if ratio not in cfg["sizes"]:
        raise ThumbnailError("thumbnail_brief.aspect_ratio 는 %s 중 하나" % ", ".join(cfg["sizes"]))
    prompt = (
        "YouTube %s thumbnail background for a Roblox-style game video about \"%s\". "
        "Scene: %s. Bright, high contrast, one clear focal point, empty space at the top third for a title. "
        "No text, no letters, no logos, no real people, no existing copyrighted characters."
        % ("Shorts" if ratio == "9:16" else "video", plan.get("topic_name", plan.get("topic_id", "")),
           tb.get("image_prompt") or tb.get("style", ""))
    )
    return {"ratio": ratio, "size": cfg["sizes"][ratio], "prompt": prompt, "overlay_text": tb.get("text", ""),
            "avoid": cfg["avoid"]}


def _openai_generate(prompt: str, size: str, model: str, n: int) -> List[bytes]:
    load_env()
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ThumbnailError("OPENAI_API_KEY 가 .env 에 없습니다. provider 를 none 으로 두면 프롬프트만 만듭니다.")
    body = json.dumps({"model": model, "prompt": prompt, "size": size, "n": n}).encode()
    req = urllib.request.Request(OPENAI_URL, data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise ThumbnailError("이미지 API 오류 %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:300].replace(key, "***")))
    out = []
    for item in data.get("data", []):
        if item.get("b64_json"):
            out.append(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=60) as r:
                out.append(r.read())
    if not out:
        raise ThumbnailError("이미지 API 응답에 이미지가 없습니다")
    return out


def overlay_text(src: Path, dst: Path, text: str, cfg: Dict) -> None:
    """배경 이미지를 비율에 맞게 자르고 위쪽 1/3 에 문구를 얹는다."""
    ff.require()
    w, h = (int(x) for x in cfg["sizes_out"].split("x"))
    fs = int(h * cfg["font_size_ratio"]) if h > w else int(h * cfg["font_size_ratio"] * 1.4)
    fs = min(fs, int(w * 0.9 / max(len(text), 1)))  # 문구가 길면 화면 폭 90% 안에 들어가게 줄인다
    esc = text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'").replace("%", r"\%")
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d," % (w, h, w, h) +
          "drawtext=font='%s':text='%s':fontcolor=white:fontsize=%d:borderw=%d:bordercolor=black:"
          "x=(w-text_w)/2:y=h*0.12" % (cfg["font"], esc, fs, max(4, fs // 12)))
    ff.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", vf, "-frames:v", "1", str(dst)])


def run(run_id: str, background: Optional[str] = None, force: bool = False) -> Dict:
    cfg = load_config()["thumbnail"]
    plan = read_stage(run_id, "plan")
    status_p = run_dir(run_id) / "05_plan.status.json"
    status = read_json(status_p).get("status") if status_p.exists() else "draft"
    if status != "validated" and not force:
        return {"run_id": run_id, "summary": "기획안 상태가 %s 입니다. validated 이후에 썸네일을 만듭니다." % status}
    spec = build_prompt(plan, cfg)
    d = tdir(run_id)
    write_json(d / "prompt.json", spec)
    out_size = {"9:16": "1080x1920", "16:9": "1280x720"}[spec["ratio"]]
    ocfg = dict(cfg, sizes_out=out_size)

    sources: List[Path] = []
    origin = "prompt_only"
    if background:
        p = Path(background) if Path(background).is_absolute() else ROOT / background
        if not p.exists():
            raise ThumbnailError("배경 이미지가 없습니다: %s" % background)
        sources, origin = [p], "user_image"
    elif cfg["provider"] == "openai":
        for i, img in enumerate(_openai_generate(spec["prompt"], spec["size"], cfg["model"], cfg["count"])):
            raw = d / ("bg_%s_%d.png" % (now_iso().replace(":", "").replace("-", "")[:15], i))
            raw.write_bytes(img)
            sources.append(raw)
        origin = "openai:" + cfg["model"]
    elif cfg["provider"] != "none":
        raise ThumbnailError("알 수 없는 thumbnail.provider: %s" % cfg["provider"])

    made = []
    for src in sources:
        v = _next_version(d)
        dst = d / ("thumb_v%d.png" % v)
        overlay_text(src, dst, spec["overlay_text"], ocfg)
        write_json(dst.with_suffix(".json"), {"plan_id": plan.get("plan_id"), "file": str(dst.relative_to(ROOT)),
                                              "ratio": spec["ratio"], "source": origin, "background": str(src.name),
                                              "prompt": spec["prompt"] if origin.startswith("openai") else None,
                                              "overlay_text": spec["overlay_text"], "created_at": now_iso()})
        made.append(str(dst.relative_to(ROOT)))
    msg = ("썸네일 %d장: %s" % (len(made), ", ".join(made))) if made else \
        "프롬프트만 저장(05_thumbnails/prompt.json). provider=none 이라 이미지는 만들지 않았습니다."
    trace(run_id, "thumbnail", msg, source=origin)
    return {"run_id": run_id, "summary": msg, "files": made,
            "next": "썸네일을 사람이 보고 고른다. 상업 이용 전 이미지 API 약관을 확인한다." if made else
            "config 의 thumbnail.provider 를 openai 로 바꾸거나 --background 로 이미지를 지정"}
