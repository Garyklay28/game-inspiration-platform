"""docs/structure.md 의 Mermaid 그림을 장(##)별 보드로 묶는 HTML 을 만든다. 렌더·변환·저장은 브라우저에서."""
import json, re, sys
src = open(sys.argv[1], encoding="utf-8").read()
out = sys.argv[2]
FILES = {"0": "board0_legend", "1": "board1_overview", "2": "board2_team_supervisor", "3": "board3_bilibili",
         "4": "board4_youtube", "5": "board5_tiktok", "6": "board6_team_db", "7": "board7_cross_platform"}
boards, seen = {}, {}
for m in re.finditer(r"```mermaid\n(.*?)```", src, re.S):
    before = src[:m.start()]
    h2 = re.findall(r"^## (.+)$", before, re.M)[-1].strip()
    h3s = [(x.start(), x.group(1).strip()) for x in re.finditer(r"^### (.+)$", before, re.M)]
    h2pos = before.rfind("\n## " + h2)
    sub = h3s[-1][1] if h3s and h3s[-1][0] > h2pos else ""
    key = h2.split(".")[0]
    b = boards.setdefault(key, {"file": FILES[key], "title": h2, "items": []})
    n = seen[(key, sub)] = seen.get((key, sub), 0) + 1
    # HTML 라벨을 끄면 Mermaid 가 *글자* 를 마크다운 기울임으로 바꿔 별표가 사라진다 → 모양이 같은 ∗(U+2217)로 바꾸고, Figma 에 넣은 뒤 다시 * 로 되돌린다
    code = "\n".join(l if l.strip().startswith("classDef") else l.replace("*", "\u2217") for l in m.group(1).splitlines())
    b["items"].append({"sub": sub, "n": n, "code": code})
for b in boards.values():  # 제목의 마크다운 백틱 제거
    b["title"] = b["title"].replace("`", "")
    for it in b["items"]: it["sub"] = it["sub"].replace("`", "")
for b in boards.values():  # 같은 소제목이 두 번이면 ①② 붙이기
    cnt = {}
    for it in b["items"]: cnt[it["sub"]] = cnt.get(it["sub"], 0) + 1
    for it in b["items"]:
        if cnt[it["sub"]] > 1: it["sub"] += " " + "①②③④"[it["n"] - 1]
NOTES = {"0": ["실선 화살표: 실제 호출·데이터 이동 · 점선 화살표: 선택 경로이거나 참고용 전달",
               "원칙(세 분기 공통): 숫자는 코드가, 해석은 LLM 이 · 점수는 정렬 참고용(조회수 예측 아님) · 순서·안전장치는 코드가 강제"]}
for k, b in boards.items(): b["notes"] = NOTES.get(k, [])
data = json.dumps([boards[k] for k in sorted(boards)], ensure_ascii=False)
html = open(sys.argv[3], encoding="utf-8").read().replace("__BOARDS__", data)
open(out, "w", encoding="utf-8").write(html)
print({b["file"]: len(b["items"]) for b in boards.values()})
