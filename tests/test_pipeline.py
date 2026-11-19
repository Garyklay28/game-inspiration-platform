"""오프라인 테스트 (네트워크·API 키 불필요). 영상 테스트는 ffmpeg 이 있을 때만 돈다.

실행: python -m pytest -q
"""
import copy
import json
import shutil
import subprocess
import uuid

import pytest

from yt_pipeline import analyze, collect, normalize, performance, qa, score, validate, video
from yt_pipeline.common import ROOT, RUNS_DIR, load_config, read_json, run_dir, write_json
from yt_pipeline.plan_rules import check_analysis, check_plan, find_predictions

EX = ROOT / "docs" / "examples"
HAS_FF = shutil.which("ffmpeg") and shutil.which("ffprobe")


@pytest.fixture
def rid():
    r = "pytest-" + uuid.uuid4().hex[:6]
    yield r
    shutil.rmtree(RUNS_DIR / r, ignore_errors=True)


def _data(rid):
    collect.run(rid, "sample")
    normalize.run(rid)
    score.run(rid)
    analyze.run(rid)
    d = run_dir(rid)
    return (read_json(d / "02_normalized.json"), read_json(d / "03_scores.json"), read_json(d / "04_evidence.json"))


def test_iso_duration_and_alias():
    assert normalize.iso_duration_sec("PT1M5S") == 65
    assert normalize.iso_duration_sec("PT2H") == 7200
    a = normalize.AliasStore()
    assert [t["topic_id"] for t in a.find("Steal a Brainrot 시크릿")] == ["steal_a_brainrot"]
    assert [t["topic_id"] for t in a.find("숲속의99밤 생존")] == ["99_nights"]


def test_data_stages(rid):
    norm, scores, ev = _data(rid)
    assert norm["is_sample"] and ev["is_sample"]
    s = [t["score"] for t in scores["topics"]]
    assert s == sorted(s, reverse=True)
    assert scores["disclaimer"] == load_config()["score"]["disclaimer"]
    assert any(c["text"] == "Forsaken" for c in ev["alias_candidates"])
    assert any("샘플" in q for q in ev["data_quality"])
    # 같은 데이터 → 같은 점수 (재현성)
    assert score.score_topics(norm["videos"], normalize.AliasStore(), load_config()["score"]) == scores["topics"]


def test_example_plan_passes_rules(rid):
    norm, scores, ev = _data(rid)
    vids = {v["video_id"] for v in norm["videos"]}
    plan = read_json(EX / "05_plan.example.json")
    r = check_plan(plan, load_config(), scores, ev, vids, is_sample=True)
    assert r["passed"], r["errors"]
    assert any("샘플" in w["problem"] for w in r["warnings"])
    a = check_analysis(read_json(EX / "04_analysis.example.json"), scores, ev, vids)
    assert a["passed"], a["errors"]


@pytest.mark.parametrize("mutate,field", [
    (lambda p: p["hooks"][0].update(line="이 영상은 조회수 100만 나올 것 같아요"), "prediction"),
    (lambda p: p["score_reference"].update(topic_score=0.99), "score_reference"),
    (lambda p: p.update(copyright_checklist=["타인 소재 안 씀"]), "copyright_checklist"),
    (lambda p: p["script_sections"][2].update(start_sec=14), "script_sections"),
    (lambda p: p.update(titles=p["titles"][:2]), "titles"),
    (lambda p: p.update(evidence_refs=["evidence.topics.nope"]), "evidence_refs"),
    (lambda p: p.update(target_duration_sec=120), "target_duration_sec"),
])
def test_plan_rule_errors(rid, mutate, field):
    norm, scores, ev = _data(rid)
    plan = copy.deepcopy(read_json(EX / "05_plan.example.json"))
    mutate(plan)
    r = check_plan(plan, load_config(), scores, ev, {v["video_id"] for v in norm["videos"]})
    assert not r["passed"] and any(e["field"] == field for e in r["errors"]), r["errors"]


def test_prediction_patterns():
    assert find_predictions("조회수 10만 돌파할 것으로 예상됩니다")
    assert find_predictions("무조건 떡상")
    assert not find_predictions("가장 크게 터진 영상은 채널 평균의 5.44배였다")


def test_validation_loop_and_revision_limit(rid):
    _data(rid)
    d = run_dir(rid)
    shutil.copy(EX / "04_analysis.example.json", d / "04_analysis.json")
    plan = read_json(EX / "05_plan.example.json")
    write_json(d / "05_plan.json", plan)
    assert validate.run(rid)["errors"] == []
    write_json(d / "rv.json", {"passed": True, "issues": []})
    validate.merge_review(rid, str(d / "rv.json"))
    assert read_json(d / "06_validation.json")["status"] == "validated"
    # 실패하는 기획안을 3번(첫 제출 + 수정 2회) 내면 needs_review
    for i in range(3):
        bad = dict(plan, titles=["a" * 10, "b" * 10, "c 조회수 %d만 나올 것" % (i + 1)])
        write_json(d / "05_plan.json", bad)
        validate.run(rid)
    assert read_json(d / "06_validation.json")["status"] == "needs_review"


@pytest.mark.skipif(not HAS_FF, reason="ffmpeg 없음")
def test_video_render_and_qa(rid, tmp_path):
    _data(rid)
    d = run_dir(rid)
    shutil.copy(EX / "04_analysis.example.json", d / "04_analysis.json")
    shutil.copy(EX / "05_plan.example.json", d / "05_plan.json")
    validate.run(rid)
    write_json(d / "rv.json", {"passed": True, "issues": []})
    validate.merge_review(rid, str(d / "rv.json"))

    vd = video.vdir(rid)
    script = read_json(EX / "script.example.json")[:4]
    for l in script:
        l["shot"] = "pytest_shot"
    write_json(vd / "script.json", script)
    t = video.build_timing(rid)
    assert "추정" in t["summary"]
    (vd / "voice").mkdir()
    for c in read_json(vd / "timing.json")["captions"]:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=%.2f" % c["dur"],
                        str(vd / "voice" / ("%s.wav" % c["id"]))], check=True)
    assert "음성 기준" in video.build_timing(rid)["summary"]

    clip = ROOT / "clips" / "pytest_shot.mp4"
    created = not clip.exists()
    if created:
        clip.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=20",
                        "-c:v", "libx264", "-preset", "ultrafast", str(clip)], check=True)
    try:
        edit = read_json(vd / "edit.draft.json")
        edit.pop("_note")
        write_json(vd / "edit.json", edit)
        assert video.check_edit(rid, edit)["passed"]
        r = video.render(rid, "preview")
        assert r["output"].endswith("preview_v1.mp4"), r
        q = qa.run(rid, r["output"])
        assert q["failed"] == [], q
        # 화면 검토 전에는 최종 렌더가 막힌다
        assert "프리뷰 먼저" in video.render(rid, "final")["summary"]
        write_json(d / "vis.json", {"passed": True, "issues": []})
        qa.merge_visual(rid, r["output"], str(d / "vis.json"))
        f = video.render(rid, "final")
        assert f["output"].endswith("final_v1.mp4")
        assert qa.run(rid, f["output"])["failed"] == []
        # 다시 렌더하면 덮어쓰지 않고 버전이 올라간다
        assert video.render(rid, "preview")["output"].endswith("preview_v2.mp4")
    finally:
        if created:
            clip.unlink()


def test_calibrate_proposal(tmp_path, monkeypatch):
    monkeypatch.setattr(performance, "PERF_DIR", tmp_path)
    monkeypatch.setattr(performance, "UPLOADS", tmp_path / "uploads.json")
    monkeypatch.setattr(performance, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(performance, "CONFIG_DIR", tmp_path)
    ups = []
    for i in range(10):
        vid = "V%02d" % i
        comp = {"demand": i / 10, "outlier": 0.5, "freshness": 0.5, "competition": 1 - i / 10}
        ups.append({"video_id": vid, "plan_id": "p%d" % i, "topic_id": "t", "components": comp,
                    "published_at": "2026-11-01T00:00:00Z", "is_sample_data": False})
        performance.manual(vid, views=1000 * (i + 1) ** 2, at="2026-11-04T00:00:00Z")  # 72시간 시점
    write_json(tmp_path / "uploads.json", ups)
    r = performance.calibrate(72)
    prop = r["proposal"]
    assert prop["samples"] == 10
    assert prop["proposed_weights"]["demand"] > prop["current_weights"]["demand"]
    assert prop["proposed_weights"]["competition"] > prop["current_weights"]["competition"]
    assert prop["proposed_weights"]["outlier"] == prop["current_weights"]["outlier"]  # 분산 0 → 유지
