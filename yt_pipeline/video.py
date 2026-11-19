"""7단계 · 영상 생성 (기획안 → 대본 → 타이밍·자막 → edit.json → 720p 프리뷰 → 최종 렌더).

파일 (runs/<id>/07_video/)
  script.json        script-writer 에이전트가 쓴다. 한 줄 = 자막 하나
                     [{"id":"c01","text":"자막(숫자는 아라비아)","say":"읽을 문장(숫자는 한글)","pause":0.3,"shot":"shot_01"}]
  voice/<id>.wav     문장별 내레이션(직접 녹음·TTS). 없으면 길이를 음절 수로 추정한다
  timing.json        자막 시각표 — 자동 생성, 직접 고치지 않는다
  subs.srt, subs.ass 자막 (srt 는 업로드용, ass 는 화면에 굽는 용도)
  voice.wav          문장 음성을 시각표대로 붙인 트랙
  edit.draft.json    샷별 타임라인 초안 → 사람이 확인하고 edit.json 으로 확정
  edit.json          편집의 유일한 기준. FFmpeg 은 이 파일대로만 실행한다
  output/preview_vN.mp4, final_vN.mp4   결과물(덮어쓰지 않고 버전을 올린다)
원본 clips/ 는 읽기만 한다.
"""
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import ff
from .common import ROOT, load_config, read_json, read_stage, run_dir, trace, write_json

LEAD, GAP, TAIL = 0.2, 0.08, 0.8


def vdir(run_id: str) -> Path:
    d = run_dir(run_id) / "07_video"
    d.mkdir(exist_ok=True)
    return d


def rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(ROOT))


def _syllables(s: str) -> int:
    return len(re.findall(r"[가-힣]", s)) + len(re.findall(r"[A-Za-z]+", s)) * 2


def wrap(text: str, max_chars: int) -> List[str]:
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def _ts(t: float, ass: bool = False) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    if ass:
        return "%d:%02d:%05.2f" % (h, m, s)
    return "%02d:%02d:%06.3f" % (h, m, s)


def check_script(lines: List[Dict], scfg: Dict) -> Tuple[List[str], List[str]]:
    errors, warnings, ids = [], [], set()
    limit = scfg["max_chars_per_line"] * scfg["max_lines"]
    for i, l in enumerate(lines):
        for k in ("id", "text", "say"):
            if not l.get(k):
                errors.append("%d번째 줄에 %s 없음" % (i + 1, k))
        if l.get("id") in ids:
            errors.append("id 중복: %s" % l.get("id"))
        ids.add(l.get("id"))
        if len(l.get("text", "")) > limit:
            warnings.append("%s 자막 %d자 — %d자×%d줄 넘음" % (l.get("id"), len(l["text"]), scfg["max_chars_per_line"], scfg["max_lines"]))
        if re.search(r"\d", l.get("say", "")):
            warnings.append("%s say 에 숫자 — TTS 오독 방지를 위해 한글로 풀어 쓰기" % l.get("id"))
        if len(wrap(l.get("text", ""), scfg["max_chars_per_line"])) > scfg["max_lines"]:
            warnings.append("%s 줄바꿈하면 %d줄 이상" % (l.get("id"), scfg["max_lines"] + 1))
    return errors, warnings


def build_timing(run_id: str) -> Dict:
    cfg = load_config()["video"]
    d = vdir(run_id)
    lines = read_json(d / "script.json")
    errors, warnings = check_script(lines, cfg["subtitle"])
    if errors:
        raise ValueError("script.json 오류: " + "; ".join(errors))

    wavs = [d / "voice" / ("%s.wav" % l["id"]) for l in lines]
    have = [w.exists() for w in wavs]
    if any(have) and not all(have):
        missing = [l["id"] for l, h in zip(lines, have) if not h]
        raise ValueError("음성 파일이 일부만 있습니다. 없는 문장: %s" % ", ".join(missing))
    mode = "voice" if all(have) and lines else "estimate"
    if mode == "voice":
        ff.require()

    t, caps = LEAD, []
    for l, w in zip(lines, wavs):
        dur = ff.duration(str(w)) if mode == "voice" else max(1.0, _syllables(l["say"]) / cfg["est_syllables_per_sec"] + 0.15)
        t += float(l.get("pause", 0) or 0)
        start = round(t, 3)
        caps.append({"id": l["id"], "text": l["text"], "shot": l.get("shot", "shot_01"),
                     "start": start, "dur": round(dur, 3)})
        t = start + dur + GAP
    for i, c in enumerate(caps):
        c["end"] = round(caps[i + 1]["start"] - 0.04 if i < len(caps) - 1 else c["start"] + c["dur"] + 0.6, 3)
    total = round(t + TAIL, 2)
    timing = {"mode": mode, "total": total, "captions": caps,
              "note": "자동 생성 파일. 직접 고치지 말고 script.json(pause·문구)이나 음성을 고친 뒤 다시 만든다."}
    write_json(d / "timing.json", timing)
    _write_srt(d / "subs.srt", caps, cfg["subtitle"])
    _write_ass(d / "subs.ass", caps, cfg)
    if mode == "voice":
        _build_voice(d, caps, wavs, total)
    draft = _edit_draft(run_id, caps, total, mode == "voice")
    write_json(d / "edit.draft.json", draft)
    if mode == "estimate":
        warnings.append("음성 파일이 없어 길이를 추정했습니다. 녹음/TTS 후 다시 timing 을 실행하세요.")
    try:
        target = read_stage(run_id, "plan").get("target_duration_sec")
        if target and abs(total - target) > target * 0.2:
            warnings.append("길이 %.1f초가 기획안 목표 %s초와 20%% 넘게 다름 — 대본 분량이나 pause 조정" % (total, target))
    except FileNotFoundError:
        pass
    msg = "자막 %d개, 길이 %.1f초 (%s)" % (len(caps), total, "음성 기준" if mode == "voice" else "추정")
    trace(run_id, "video.timing", msg, warnings=warnings)
    return {"run_id": run_id, "summary": msg, "warnings": warnings,
            "next": "edit.draft.json 의 clip·in·out 을 확인해 edit.json 으로 저장(승인 필요)"}


def _write_srt(path: Path, caps: List[Dict], scfg: Dict) -> None:
    out = []
    for i, c in enumerate(caps, 1):
        txt = "\n".join(wrap(c["text"], scfg["max_chars_per_line"]))
        out.append("%d\n%s --> %s\n%s\n" % (i, _ts(c["start"]).replace(".", ","), _ts(c["end"]).replace(".", ","), txt))
    path.write_text("\n".join(out), encoding="utf-8")


def _write_ass(path: Path, caps: List[Dict], vcfg: Dict) -> None:
    w, h = (int(x) for x in vcfg["final"]["size"].split("x"))
    s = vcfg["subtitle"]
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,%s,%d,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,0,2,60,60,%d,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            % (w, h, s["font"], s["font_size"], s["margin_v"]))
    ev = ["Dialogue: 0,%s,%s,Default,,0,0,0,,%s" % (_ts(c["start"], True), _ts(c["end"], True),
                                                    r"\N".join(wrap(c["text"], s["max_chars_per_line"])))
          for c in caps]
    path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


def _build_voice(d: Path, caps: List[Dict], wavs: List[Path], total: float) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for w in wavs:
        cmd += ["-i", str(w)]
    parts, labels = [], []
    for i, c in enumerate(caps):
        ms = int(round(c["start"] * 1000))
        parts.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,adelay=%d|%d[v%d]" % (i, ms, ms, i))
        labels.append("[v%d]" % i)
    parts.append("%samix=inputs=%d:normalize=0:dropout_transition=0,apad[out]" % ("".join(labels), len(labels)))
    ff.run(cmd + ["-filter_complex", ";".join(parts), "-map", "[out]", "-t", "%.3f" % total,
                  "-ar", "48000", str(d / "voice.wav")])


def _edit_draft(run_id: str, caps: List[Dict], total: float, has_voice: bool) -> Dict:
    vcfg = load_config()["video"]
    groups: List[Dict] = []
    for c in caps:
        if groups and groups[-1]["shot"] == c["shot"]:
            groups[-1]["captions"].append(c["id"])
        else:
            groups.append({"shot": c["shot"], "start": c["start"], "captions": [c["id"]]})
    groups[0]["start"] = 0.0 if groups else 0.0
    timeline = []
    for i, g in enumerate(groups):
        end = groups[i + 1]["start"] if i < len(groups) - 1 else total
        timeline.append({"clip": "clips/%s.mp4" % g["shot"], "in": 0.0, "out": round(end - g["start"], 3),
                         "crop_x": 0.5, "transition": "cut", "captions": g["captions"]})
    try:
        plan_id = read_stage(run_id, "plan").get("plan_id")
    except FileNotFoundError:
        plan_id = None
    d = vdir(run_id)
    return {"plan_id": plan_id, "output": {"size": vcfg["final"]["size"], "fps": vcfg["final"]["fps"]},
            "timeline": timeline, "captions": rel(d / "subs.ass"),
            "voice": rel(d / "voice.wav") if has_voice else None, "clip_audio": 0.0,
            "bgm": None, "_note": "clip 의 in/out 을 실제 장면에 맞춰 고친다. out−in 합계가 timing 의 total 과 같아야 한다. "
                                  "BGM 은 {\"file\":\"audio/xxx.mp3\",\"volume\":0.25,\"fade_out\":1.0,\"duck\":true} 형식, 출처는 CREDITS.txt"}


# ── edit.json 검사 ─────────────────────────────────────────

def edit_hash(edit: Dict) -> str:
    return hashlib.sha1(json.dumps(edit, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]


def check_edit(run_id: str, edit: Dict) -> Dict:
    cfg = load_config()
    vcfg, qcfg = cfg["video"], cfg["qa"]
    errors, warnings = [], []
    if edit.get("output", {}).get("size") != vcfg["final"]["size"] or edit.get("output", {}).get("fps") != vcfg["final"]["fps"]:
        errors.append("output 이 설정(%s, %sfps)과 다름" % (vcfg["final"]["size"], vcfg["final"]["fps"]))
    tl = edit.get("timeline") or []
    if not tl:
        errors.append("timeline 비어 있음")
    total = 0.0
    for i, s in enumerate(tl):
        clip = ROOT / s.get("clip", "")
        if not clip.exists():
            errors.append("[%d] 클립 없음: %s" % (i, s.get("clip")))
            continue
        a, b = s.get("in"), s.get("out")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a < 0 or b <= a:
            errors.append("[%d] in/out 잘못됨 (%s→%s)" % (i, a, b))
            continue
        cd = ff.duration(str(clip))
        if b > cd + 0.05:
            errors.append("[%d] out %.2f초가 클립 길이 %.2f초보다 김: %s" % (i, b, cd, s["clip"]))
        if not 0 <= float(s.get("crop_x", 0.5)) <= 1:
            errors.append("[%d] crop_x 는 0~1" % i)
        if s.get("transition", "cut") not in ("cut", "fadein"):
            errors.append("[%d] transition 은 cut 또는 fadein" % i)
        total += b - a
    for k in ("captions", "voice"):
        if edit.get(k) and not (ROOT / edit[k]).exists():
            errors.append("%s 파일 없음: %s" % (k, edit[k]))
    bgm = edit.get("bgm")
    if bgm:
        if not (ROOT / bgm.get("file", "")).exists():
            errors.append("BGM 파일 없음: %s" % bgm.get("file"))
        if not 0 < float(bgm.get("volume", vcfg["bgm_volume"])) <= 1:
            errors.append("BGM volume 은 0~1")
        credits = (ROOT / "CREDITS.txt").read_text(encoding="utf-8") if (ROOT / "CREDITS.txt").exists() else ""
        if Path(bgm.get("file", "")).name not in credits:
            errors.append("CREDITS.txt 에 BGM(%s) 출처·라이선스가 없음" % Path(bgm.get("file", "")).name)
    tpath = vdir(run_id) / "timing.json"
    if tpath.exists():
        tt = read_json(tpath)["total"]
        if abs(tt - total) > qcfg["duration_tolerance_sec"]:
            errors.append("타임라인 합계 %.2f초 ≠ 내레이션 시각표 %.2f초" % (total, tt))
    if total > cfg["normalize"]["shorts_max_sec"]:
        errors.append("길이 %.1f초 — 쇼츠 상한 %d초 초과" % (total, cfg["normalize"]["shorts_max_sec"]))
    return {"passed": not errors, "errors": errors, "warnings": warnings, "expected_duration": round(total, 3),
            "edit_hash": edit_hash(edit)}


# ── 렌더 ──────────────────────────────────────────────────

def _next_version(out_dir: Path, kind: str) -> int:
    ns = [int(m.group(1)) for p in out_dir.glob("%s_v*.mp4" % kind) for m in [re.search(r"_v(\d+)\.mp4$", p.name)] if m]
    return max(ns, default=0) + 1


def build_command(run_id: str, edit: Dict, kind: str, out_path: Path) -> List[str]:
    vcfg = load_config()["video"]
    spec = vcfg[kind]
    W, H = (int(x) for x in spec["size"].split("x"))
    fps = spec["fps"]
    tl = edit["timeline"]
    total = sum(s["out"] - s["in"] for s in tl)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for s in tl:
        cmd += ["-ss", "%.3f" % s["in"], "-to", "%.3f" % s["out"], "-i", str(ROOT / s["clip"])]
    n = len(tl)
    f, vl = [], []
    for i, s in enumerate(tl):
        cx = float(s.get("crop_x", 0.5))
        chain = ("[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:(iw-%d)*%.3f:(ih-%d)/2,"
                 "setsar=1,fps=%d,format=yuv420p,setpts=PTS-STARTPTS" % (i, W, H, W, H, W, cx, H, fps))
        if s.get("transition") == "fadein":
            chain += ",fade=t=in:st=0:d=0.25"
        f.append(chain + "[v%d]" % i)
        vl.append("[v%d]" % i)
    f.append("%sconcat=n=%d:v=1:a=0[vc]" % ("".join(vl), n))
    vout = "[vc]"
    if edit.get("captions"):
        sub = str(ROOT / edit["captions"]).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        fonts = ROOT / "assets" / "fonts"
        fd = (":fontsdir='%s'" % str(fonts).replace("\\", "/").replace(":", r"\:")) if fonts.exists() else ""
        f.append("[vc]ass='%s'%s[vout]" % (sub, fd))
        vout = "[vout]"

    # 오디오: 내레이션 + (원본 클립 소리) + BGM
    idx, alabels = n, []
    if edit.get("voice"):
        cmd += ["-i", str(ROOT / edit["voice"])]
        f.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.0[av]" % idx)
        alabels.append("[av]")
        idx += 1
    ca = float(edit.get("clip_audio", 0) or 0)
    if ca > 0:
        if all(ff.probe(str(ROOT / s["clip"]))["has_audio"] for s in tl):
            f.append("%sconcat=n=%d:v=0:a=1,aresample=48000,aformat=channel_layouts=stereo,volume=%.2f[ac]"
                     % ("".join("[%d:a]" % i for i in range(n)), n, ca))
            alabels.append("[ac]")
    bgm = edit.get("bgm")
    if bgm:
        cmd += ["-stream_loop", "-1", "-i", str(ROOT / bgm["file"])]
        fo = float(bgm.get("fade_out", vcfg["bgm_fade_out_sec"]))
        f.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,volume=%.3f,atrim=0:%.3f,"
                 "afade=t=in:st=0:d=0.5,afade=t=out:st=%.3f:d=%.3f[ab0]"
                 % (idx, float(bgm.get("volume", vcfg["bgm_volume"])), total, max(total - fo, 0), fo))
        if bgm.get("duck") and "[av]" in alabels:  # 내레이션이 나올 때 BGM 을 자동으로 낮춘다
            f.append("[av]asplit=2[av1][avsc]")
            alabels[alabels.index("[av]")] = "[av1]"
            f.append("[ab0][avsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[ab]")
        else:
            f.append("[ab0]anull[ab]")
        alabels.append("[ab]")
        idx += 1
    if not alabels:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        f.append("[%d:a]atrim=0:%.3f[aout]" % (idx, total))
    else:
        f.append("%samix=inputs=%d:normalize=0:duration=longest,atrim=0:%.3f,alimiter=limit=0.89[aout]"
                 % ("".join(alabels), len(alabels), total))
    cmd += ["-filter_complex", ";".join(f), "-map", vout, "-map", "[aout]",
            "-c:v", spec["codec"], "-preset", spec["preset"], "-crf", str(spec["crf"]), "-r", str(fps),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", spec["audio_bitrate"], "-ar", "48000",
            "-t", "%.3f" % total, "-movflags", "+faststart", str(out_path)]
    return cmd


def render(run_id: str, kind: str = "preview", plan_only: bool = False, force: bool = False) -> Dict:
    ff.require()
    d = vdir(run_id)
    if not (d / "edit.json").exists():
        raise FileNotFoundError("edit.json 이 없습니다. edit.draft.json 을 확인·승인한 뒤 edit.json 으로 저장하세요.")
    edit = read_json(d / "edit.json")
    chk = check_edit(run_id, edit)
    if not chk["passed"]:
        return {"run_id": run_id, "summary": "edit.json 검사 실패 — 렌더하지 않음", "errors": chk["errors"]}
    if not force:
        status = read_json(run_dir(run_id) / "05_plan.status.json").get("status") \
            if (run_dir(run_id) / "05_plan.status.json").exists() else "draft"
        if status != "validated":
            return {"run_id": run_id, "summary": "기획안 상태가 %s — 검증 통과(validated) 후 렌더" % status, "errors": []}
        if kind == "final":
            qa_ok = [r for r in _qa_reports(d) if r.get("kind") == "preview" and r.get("verdict") == "PASS"
                     and (r.get("visual_review") or {}).get("passed") and r.get("edit_hash") == chk["edit_hash"]]
            if not qa_ok:
                return {"run_id": run_id, "summary": "같은 edit.json 의 프리뷰 QA PASS(측정+화면 검토) 기록이 없음 — 프리뷰 먼저",
                        "errors": []}
    out_dir = d / "output"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / ("%s_v%d.mp4" % (kind, _next_version(out_dir, kind)))
    cmd = build_command(run_id, edit, kind, out)
    if plan_only:
        return {"run_id": run_id, "summary": "렌더 계획(실행 안 함)", "output": rel(out),
                "expected_duration": chk["expected_duration"], "command": ff.show(cmd)}
    ff.run(cmd)
    log = {"output": rel(out), "kind": kind, "edit_hash": chk["edit_hash"], "command": ff.show(cmd)}
    write_json(out.with_suffix(".render.json"), log)
    msg = "%s 렌더 완료: %s (예상 %.2f초)" % (kind, rel(out), chk["expected_duration"])
    trace(run_id, "video.render", msg, edit_hash=chk["edit_hash"])
    return {"run_id": run_id, "summary": msg, "output": rel(out), "next": "qa 실행"}


def _qa_reports(d: Path) -> List[Dict]:
    return [read_json(p) for p in sorted((d / "output").glob("*.qa.json"))] if (d / "output").exists() else []
