"""CLI: python -m yt_pipeline <명령>. 결과는 JSON 한 덩어리로 출력한다(에이전트가 읽기 쉽게)."""
import argparse
import json
import sys

from . import analyze, collect, db, normalize, performance, qa, report, score, thumbnail, validate, video
from .common import FILES, latest_run_id, new_run_id, run_dir

STAGES = [("raw", "1 수집", "collect"), ("normalized", "2 정규화", "normalize"), ("scores", "3 점수화", "score"),
          ("evidence", "4a 근거 팩", "analyze"), ("analysis", "4b 분석(trend-analyst)", "에이전트"),
          ("plan", "5 기획안(plan-writer)", "에이전트"), ("validation", "6 검증", "validate → review")]


def _rid(a) -> str:
    rid = a.run or latest_run_id()
    if not rid:
        sys.exit("실행 폴더가 없습니다. collect 부터 실행하세요.")
    return rid


def status(rid: str) -> dict:
    d = run_dir(rid)
    rows, nxt = [], None
    for key, label, how in STAGES:
        ok = (d / FILES[key]).exists()
        rows.append({"stage": label, "done": ok, "file": FILES[key]})
        if not ok and nxt is None:
            nxt = "%s (%s)" % (label, how)
    st = (d / "05_plan.status.json")
    plan_status = json.loads(st.read_text(encoding="utf-8"))["status"] if st.exists() else None
    v = d / "07_video"
    vid = {f: (v / f).exists() for f in ("script.json", "timing.json", "edit.json")}
    outs = sorted(p.name for p in (v / "output").glob("*.mp4")) if (v / "output").exists() else []
    qas = {p.name.replace(".qa.json", ".mp4"): json.loads(p.read_text(encoding="utf-8")).get("verdict")
           for p in (v / "output").glob("*.qa.json")} if (v / "output").exists() else {}
    if nxt is None:
        if plan_status != "validated":
            nxt = "6 검증 통과 필요"
        elif any(n.startswith("final") and qas.get(n) == "PASS" for n in outs):
            nxt = "사람 최종 확인·업로드 후 8 성과 기록 (perf register)"
        else:
            nxt = "7 영상 생성"
    return {"run_id": rid, "stages": rows, "plan_status": plan_status, "video": vid,
            "renders": [{"file": n, "qa": qas.get(n)} for n in outs], "next": nxt}


def main(argv=None):
    p = argparse.ArgumentParser(prog="yt_pipeline", description="YouTube 쇼츠 에이전트 파이프라인")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("--run", help="실행 ID (기본: 가장 최근)")
        return sp

    c = add("collect", help="1 수집")
    c.add_argument("--source", choices=["api", "file", "sample"], default="api")
    c.add_argument("--path")
    c.add_argument("--keywords", help="쉼표로 구분")
    d = add("data", help="1~4a 한 번에 (collect→normalize→score→analyze)")
    d.add_argument("--source", choices=["api", "file", "sample"], default="api")
    d.add_argument("--path")
    d.add_argument("--keywords")
    for n, h in [("normalize", "2 정규화"), ("score", "3 점수화"), ("analyze", "4a 근거 팩"),
                 ("validate", "6 규칙 검사"), ("status", "진행 상황")]:
        add(n, help=h)
    r = add("review", help="6 plan-validator 검토 합치기")
    r.add_argument("--file", required=True)
    rp = add("report", help="YouTubeReport 생성")
    rp.add_argument("--intent", default="make_video")

    th = add("thumbnail", help="5 썸네일 이미지 (기획안 에이전트 도구)")
    th.add_argument("--background", help="문구를 얹을 이미지 경로 (없으면 설정의 provider 사용)")
    th.add_argument("--force", action="store_true", help="검증 전에도 실행(테스트용)")
    dbp = add("db", help="Supabase 저장")
    dbp.add_argument("action", choices=["export", "push"])

    v = add("video", help="7 영상 생성")
    v.add_argument("action", choices=["timing", "check", "render"])
    v.add_argument("--final", action="store_true", help="최종 화질(기본은 720p 프리뷰)")
    v.add_argument("--plan-only", action="store_true", help="ffmpeg 명령만 보여 주고 실행하지 않음")
    v.add_argument("--force", action="store_true", help="검증·프리뷰 게이트 무시(테스트용)")

    q = add("qa", help="7 검수")
    q.add_argument("--file", required=True)
    q.add_argument("--visual", help="qa-reviewer 화면 검토 JSON 합치기")

    pf = add("perf", help="8 성과 기록")
    pf.add_argument("action", choices=["register", "fetch", "manual", "summary", "calibrate", "apply"])
    pf.add_argument("--video-id")
    pf.add_argument("--published-at")
    pf.add_argument("--views", type=int)
    pf.add_argument("--likes", type=int, default=0)
    pf.add_argument("--comments", type=int, default=0)
    pf.add_argument("--checkpoint", type=int, default=72)

    a = p.parse_args(argv)
    kw = lambda: [k.strip() for k in a.keywords.split(",")] if getattr(a, "keywords", None) else None  # noqa: E731

    try:
        if a.cmd in ("collect", "data"):
            rid = a.run or new_run_id()
            out = [collect.run(rid, a.source, a.path, kw())]
            if a.cmd == "data":
                out += [normalize.run(rid), score.run(rid), analyze.run(rid)]
            res = {"run_id": rid, "steps": out}
        elif a.cmd == "normalize":
            res = normalize.run(_rid(a))
        elif a.cmd == "score":
            res = score.run(_rid(a))
        elif a.cmd == "analyze":
            res = analyze.run(_rid(a))
        elif a.cmd == "validate":
            res = validate.run(_rid(a))
        elif a.cmd == "review":
            res = validate.merge_review(_rid(a), a.file)
        elif a.cmd == "status":
            res = status(_rid(a))
        elif a.cmd == "report":
            res = report.build(_rid(a), a.intent)
        elif a.cmd == "thumbnail":
            res = thumbnail.run(_rid(a), a.background, a.force)
        elif a.cmd == "db":
            res = db.export(_rid(a)) if a.action == "export" else db.push(_rid(a))
        elif a.cmd == "video":
            rid = _rid(a)
            if a.action == "timing":
                res = video.build_timing(rid)
            elif a.action == "check":
                res = video.check_edit(rid, json.loads((video.vdir(rid) / "edit.json").read_text(encoding="utf-8")))
            else:
                res = video.render(rid, "final" if a.final else "preview", a.plan_only, a.force)
        elif a.cmd == "qa":
            res = qa.merge_visual(_rid(a), a.file, a.visual) if a.visual else qa.run(_rid(a), a.file)
        elif a.cmd == "perf":
            act = a.action
            if act == "register":
                res = performance.register(_rid(a), a.video_id, a.published_at)
            elif act == "fetch":
                res = performance.fetch()
            elif act == "manual":
                res = performance.manual(a.video_id, a.views, a.likes, a.comments)
            elif act == "summary":
                res = performance.summary()
            elif act == "calibrate":
                res = performance.calibrate(a.checkpoint)
            else:
                res = performance.apply_proposed()
    except Exception as e:  # 에이전트가 읽고 고칠 수 있게 오류도 JSON 으로
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(dict(ok=True, **res) if isinstance(res, dict) else res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
