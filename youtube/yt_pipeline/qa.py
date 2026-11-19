"""7단계 끝 · 검수 — 렌더 결과를 기계로 측정하고, 화면은 Claude(qa-reviewer)가 프레임 이미지로 본다.

확인 1 · 규격  : ffprobe 해상도·fps·길이·오디오를 설정·edit.json 과 대조
확인 2 · 화면  : 자막 구간 중간 프레임 + 3초·10초 프레임 추출, blackdetect 로 검은 화면 탐지
확인 3 · 소리  : silencedetect 로 의도하지 않은 무음, volumedetect 로 클리핑
결과: <영상>.qa.json (verdict PASS/FAIL). FAIL 이면 edit.json 을 고쳐 _v(N+1) 로 다시 렌더한다.
측정으로 확인할 수 없는 것(직접 청취, 발음, 사실 관계, 음원 라이선스)은 human_checks 로 분리한다.
"""
import re
from pathlib import Path
from typing import Dict, List

from . import ff
from .common import ROOT, load_config, read_json, trace, write_json
from .video import check_edit, rel, vdir

HUMAN_CHECKS = [
    "처음부터 끝까지 한 번 직접 들었다 (Claude 는 소리를 듣지 못한다)",
    "내레이션 발음·억양이 어색한 곳이 없다",
    "자막의 숫자·이름·게임 용어가 맞다",
    "BGM 이 내레이션을 가리지 않고, CREDITS.txt 출처 문구를 설명란에 넣었다",
    "게임 화면은 직접 녹화한 것이고, 다른 크리에이터의 영상·음성을 쓰지 않았다",
    "공개(업로드) 여부는 사람이 결정한다",
]


def _intervals(log: str, key: str) -> List[Dict]:
    out, start = [], None
    if key == "silence":
        for line in log.splitlines():
            m = re.search(r"silence_start: (-?[\d.]+)", line)
            if m:
                start = float(m.group(1))
            m = re.search(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", line)
            if m:
                out.append({"start": round(max(start or 0, 0), 2), "end": float(m.group(1)), "dur": float(m.group(2))})
                start = None
        if start is not None:
            out.append({"start": round(max(start, 0), 2), "end": None, "dur": None})
    else:
        for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", log):
            out.append({"start": float(m.group(1)), "end": float(m.group(2)), "dur": float(m.group(3))})
    return out


def run(run_id: str, file: str) -> Dict:
    ff.require()
    cfg = load_config()
    qcfg = cfg["qa"]
    path = Path(file) if Path(file).is_absolute() else ROOT / file
    kind = "final" if path.name.startswith("final") else "preview"
    spec = cfg["video"][kind]
    W, H = (int(x) for x in spec["size"].split("x"))
    d = vdir(run_id)
    edit = read_json(d / "edit.json")
    ec = check_edit(run_id, edit)
    render_log = path.with_suffix(".render.json")
    rendered_hash = read_json(render_log)["edit_hash"] if render_log.exists() else None
    timing = read_json(d / "timing.json") if (d / "timing.json").exists() else None

    checks = []

    def add(name, ok, detail, severity="fail"):
        checks.append({"check": name, "ok": bool(ok), "severity": severity if not ok else "-", "detail": detail})

    # 확인 1 · 규격
    p = ff.probe(str(path))
    add("해상도", (p["width"], p["height"]) == (W, H), "%sx%s (기준 %dx%d)" % (p["width"], p["height"], W, H))
    add("fps", p["fps"] is not None and abs(p["fps"] - spec["fps"]) < 0.01, "%s (기준 %s)" % (p["fps"], spec["fps"]))
    add("길이", abs(p["duration"] - ec["expected_duration"]) <= qcfg["duration_tolerance_sec"],
        "%.2f초 (edit.json %.2f초 ±%.1f)" % (p["duration"], ec["expected_duration"], qcfg["duration_tolerance_sec"]))
    add("쇼츠 규격", p["height"] > p["width"] and p["duration"] <= cfg["normalize"]["shorts_max_sec"],
        "세로 %s, %.1f초 ≤ %d초" % (p["height"] > p["width"], p["duration"], cfg["normalize"]["shorts_max_sec"]))
    add("오디오 트랙", p["has_audio"], "codec=%s" % p["acodec"])
    add("edit.json 일치", rendered_hash == ec["edit_hash"],
        "렌더 당시 %s / 현재 %s" % (rendered_hash, ec["edit_hash"]), severity="fail")

    # 확인 2 · 화면
    blacks = _intervals(ff.detect(str(path), "blackdetect=d=%.2f:pix_th=0.10" % qcfg["black_min_sec"], "v"), "black")
    add("검은 화면", not blacks, blacks or "없음")
    frames_dir = path.parent / (path.stem + "_frames")
    frames_dir.mkdir(exist_ok=True)
    times = sorted({round(t, 2) for t in ([3.0, 10.0] + ([(c["start"] + c["end"]) / 2 for c in timing["captions"]]
                                                          if timing else [i * 5.0 for i in range(int(p["duration"] // 5) + 1)]))
                    if t < p["duration"] - 0.05})
    frames = []
    for t in times:
        out = frames_dir / ("t%06.2f.png" % t)
        ff.extract_frame(str(path), t, str(out))
        cap = next((c for c in (timing or {}).get("captions", []) if c["start"] <= t <= c["end"]), None)
        frames.append({"t": t, "file": rel(out), "expected_caption": cap and cap["text"]})

    sheet = path.parent / (path.stem + "_sheet.png")  # 한 장으로 모은 프레임 시트 (qa-reviewer 가 먼저 본다)
    cols = 6
    ff.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-pattern_type", "glob", "-i",
            str(frames_dir / "t*.png"), "-vf", "scale=270:-2,tile=%dx%d:padding=6:color=gray" % (cols, -(-len(frames) // cols)),
            "-frames:v", "1", str(sheet)])

    # 확인 3 · 소리
    sil = _intervals(ff.detect(str(path), "silencedetect=noise=%ddB:d=%.2f" % (qcfg["silence_noise_db"], qcfg["silence_min_sec"])), "silence")
    unexpected = sil
    if timing and timing.get("mode") == "voice" and not edit.get("bgm") and not edit.get("clip_audio"):
        # 내레이션만 있으면 문장 사이 pause 는 의도된 무음 — 자막 구간 안의 무음만 문제로 본다
        unexpected = [s for s in sil if any(c["start"] < (s["start"] + (s["dur"] or 0) / 2) < c["start"] + c["dur"]
                                            for c in timing["captions"])]
    add("의도하지 않은 무음", not unexpected, unexpected or "없음")
    vol = ff.detect(str(path), "volumedetect")
    mx = re.search(r"max_volume: (-?[\d.]+) dB", vol)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", vol)
    mxv = float(mx.group(1)) if mx else None
    add("클리핑", mxv is not None and mxv <= -0.5, "max %s dB, mean %s dB" % (mxv, mean and mean.group(1)), severity="warn")

    fails = [c for c in checks if not c["ok"] and c["severity"] == "fail"]
    report = {"file": rel(path), "kind": kind, "edit_hash": ec["edit_hash"], "probe": p,
              "verdict": "PASS" if not fails else "FAIL", "checks": checks, "frame_sheet": rel(sheet), "frames": frames,
              "visual_review": None, "human_checks": HUMAN_CHECKS,
              "next": "qa-reviewer 가 frames 를 보고 visual_review 를 채운다" if not fails
              else "edit.json 을 고쳐 다음 버전으로 다시 렌더"}
    write_json(path.with_suffix(".qa.json"), report)
    msg = "%s %s — 실패 %d개, 프레임 %d장" % (rel(path), report["verdict"], len(fails), len(frames))
    trace(run_id, "qa", msg, ok=not fails)
    return {"run_id": run_id, "summary": msg, "report": rel(path.with_suffix(".qa.json")),
            "failed": [c["check"] for c in fails]}


def merge_visual(run_id: str, file: str, review_path: str) -> Dict:
    """qa-reviewer 의 화면 검토({passed, issues:[{t, problem}]})를 합친다. 화면 문제가 있으면 FAIL."""
    path = Path(file) if Path(file).is_absolute() else ROOT / file
    qa_path = path.with_suffix(".qa.json")
    rep, rv = read_json(qa_path), read_json(review_path)
    if not isinstance(rv.get("passed"), bool):
        raise ValueError("visual review 형식: {\"passed\": bool, \"issues\": [{\"t\": 초, \"problem\": \"...\"}]}")
    rep["visual_review"] = rv
    if not rv["passed"]:
        rep["verdict"] = "FAIL"
        rep["next"] = "화면 문제 수정 후 다음 버전 렌더"
    write_json(qa_path, rep)
    trace(run_id, "qa.visual", "%s 화면 검토 %s" % (rep["file"], "통과" if rv["passed"] else "문제 %d건" % len(rv.get("issues", []))),
          ok=rv["passed"])
    return {"run_id": run_id, "summary": "verdict=%s" % rep["verdict"]}
