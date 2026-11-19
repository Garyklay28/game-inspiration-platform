"""기획안(Figma) 12·13쪽을 SVG 로 만든다 — 에이전트 아키텍처.

Figma MCP 편집에는 Full 좌석이 필요해, 같은 스타일(1000×1414, 왼쪽 남색 띠, Inter, 회색 카드)의
SVG 를 만들어 Figma 에 끌어다 놓는 방식으로 넣는다. SVG 의 <text> 는 Figma 에서 편집 가능한 텍스트가 된다.

  python docs/figma/make_pages.py   →  docs/figma/page_12_team_architecture.svg, page_13_bilibili_supervisor.svg
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent
W, H = 1000, 1414
X0, CW = 120, 824  # 본문 시작 x(64 띠 + 56 여백), 본문 폭
C = dict(navy="#1f2b4d", ink="#1f1f26", gray="#737885", card="#f4f5f7", line="#e3e5ea", white="#ffffff",
         sub="#c9d0e3", yt="#ff0033", bili="#00a1d6", tt="#25f4ee")
WEIGHT = {"Regular": 400, "Semi Bold": 600, "Bold": 700}
LH = 1.45


def char_w(ch: str, size: float, bold: bool) -> float:
    o = ord(ch)
    # Figma 의 Inter(라틴)·한글 대체 글꼴 폭보다 약간 넉넉하게 잡는다 → 상자 밖으로 넘치지 않게
    if o >= 0x1100 and not (0x2000 <= o <= 0x206F):  # 한글·한자·전각
        return size * 1.0
    if ch == " ":
        return size * 0.3
    if ch in "il.,:;|!'·()[]":
        return size * 0.32
    if ch.isupper() or ch in "mwMW@%":
        return size * (0.74 if bold else 0.7)
    return size * (0.61 if bold else 0.58)


def text_w(s: str, size: float, bold: bool = False) -> float:
    return sum(char_w(c, size, bold) for c in s)


def wrap(s: str, width: float, size: float, bold: bool = False):
    lines = []
    for para in s.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = (line + " " + word) if line else word
            if text_w(cand, size, bold) <= width:
                line = cand
                continue
            if line:
                lines.append(line)
            # 단어 하나가 너무 길면 글자 단위로 자른다
            line = ""
            for ch in word:
                if text_w(line + ch, size, bold) > width and line:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
        lines.append(line)
    return lines


class Page:
    def __init__(self, number: str):
        self.els = []
        self.y = 56
        self.rect(0, 0, W, H, C["white"])
        self.rect(0, 0, 64, H, C["navy"])
        self.text(X0, self.y, "인스피레이션 플랫폼 · 기획안", 11, "Regular", C["gray"])
        self.text(X0 + CW - text_w(number, 11, True), self.y, number, 11, "Semi Bold", C["navy"])
        self.y += 13 + 24

    # ── 기본 도형 ──
    def rect(self, x, y, w, h, fill, rx=0, stroke=None, dash=None, name=None):
        a = 'x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"' % (x, y, w, h, fill)
        if rx:
            a += ' rx="%s"' % rx
        if stroke:
            a += ' stroke="%s" stroke-width="1"' % stroke
        if dash:
            a += ' stroke-dasharray="%s"' % dash
        if name:
            a = 'id="%s" ' % name + a
        self.els.append("<rect %s/>" % a)

    def path(self, d, color=C["navy"], width=2):
        self.els.append('<path d="%s" stroke="%s" stroke-width="%s" fill="none" stroke-linejoin="round"/>' % (d, color, width))

    def text(self, x, top, s, size, style="Regular", color=C["ink"], width=None, anchor_center=False):
        """top 기준으로 텍스트를 놓고, 차지한 높이를 돌려준다."""
        bold = style != "Regular"
        lines = wrap(s, width, size, bold) if width else [s]
        lh = size * LH
        spans = []
        for i, ln in enumerate(lines):
            tx = x - text_w(ln, size, bold) / 2 if anchor_center else x
            spans.append('<tspan x="%.1f" y="%.1f">%s</tspan>' % (tx, top + size * 1.08 + i * lh, escape(ln)))
        self.els.append('<text font-family="Inter" font-size="%s" font-weight="%d" fill="%s">%s</text>'
                        % (size, WEIGHT[style], color, "".join(spans)))
        return len(lines) * lh

    # ── 기획안 공통 블록 ──
    def section(self, num, title):
        bw = text_w(num, 14, True) + 20
        self.rect(X0, self.y, bw, 33, C["navy"], rx=8)
        self.text(X0 + bw / 2, self.y + 7, num, 14, "Bold", C["white"], anchor_center=True)
        self.text(X0 + bw + 12, self.y + 1, title, 24, "Bold", C["ink"])
        self.rect(X0, self.y + 57, CW, 2, C["navy"])
        self.y += 57 + 2 + 22

    def para(self, s, size=13, style="Regular", color=C["ink"], gap=18):
        self.y += self.text(X0, self.y, s, size, style, color, width=CW) + gap

    def subtitle(self, s):
        self.y += self.text(X0, self.y, s, 16, "Bold", C["ink"]) + 10

    def table(self, widths, rows, size=11.5, gap=20):
        top = self.y
        heights = []
        for i, cells in enumerate(rows):
            heights.append(max(len(wrap(c, w - 24, size, i == 0 or j == 0)) for j, (c, w) in enumerate(zip(cells, widths)))
                           * size * LH + 16)
        total = sum(heights)
        self.rect(X0, top, CW, total, C["white"], rx=8, stroke=C["line"])
        y = top
        for i, (cells, h) in enumerate(zip(rows, heights)):
            if i == 0:
                self.els.append('<path d="M%.1f %.1fH%.1fV%.1fH%.1fZ" fill="%s"/>' % (
                    X0 + 8, y, X0 + CW - 8, y + h, X0 + 8, C["navy"]))  # 위 모서리 둥근 머리줄
                self.rect(X0, y, CW, h, C["navy"], rx=8)
                self.rect(X0, y + 8, CW, h - 8, C["navy"])
            elif i % 2 == 0:
                self.rect(X0 + 1, y, CW - 2, h if i < len(rows) - 1 else h - 1, C["card"])
            x = X0
            for j, (c, w) in enumerate(zip(cells, widths)):
                style = "Semi Bold" if (i == 0 or j == 0) else "Regular"
                self.text(x + 12, y + 8, c, size, style, C["white"] if i == 0 else C["ink"], width=w - 24)
                x += w
            y += h
        self.y = top + total + gap

    def cards(self, items, cols=2, gap=12, size=12, title_color=C["navy"], bottom_gap=20):
        cw = (CW - gap * (cols - 1)) / cols
        for r in range(0, len(items), cols):
            row = items[r:r + cols]
            hs = [14 + 13 * LH + 6 + len(wrap(b, cw - 32, size)) * size * LH + 14 for _, b in row]
            h = max(hs)
            for k, (t, b) in enumerate(row):
                x = X0 + k * (cw + gap)
                self.rect(x, self.y, cw, h, C["card"], rx=8)
                self.text(x + 16, self.y + 14, t, 13, "Bold", title_color)
                self.text(x + 16, self.y + 14 + 13 * LH + 6, b, size, "Regular", C["ink"], width=cw - 32)
            self.y += h + gap
        self.y += bottom_gap - gap

    def note(self, s):
        h = len(wrap(s, CW - 32, 12)) * 12 * LH + 24
        self.rect(X0, self.y, CW, h, C["card"], rx=8)
        self.text(X0 + 16, self.y + 12, s, 12, "Regular", C["ink"], width=CW - 32)
        self.y += h + 20

    def arrow_down(self, cx, top, length=20):
        self.path("M%.1f %.1fV%.1f" % (cx, top, top + length - 2))
        self.path("M%.1f %.1fL%.1f %.1fL%.1f %.1f" % (cx - 6, top + length - 8, cx, top + length - 1, cx + 6, top + length - 8))

    def save(self, name):
        if self.y > H - 40:
            raise SystemExit("%s: 내용이 페이지를 넘침 (y=%.0f)" % (name, self.y))
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">%s</svg>'
               % (W, H, W, H, "\n".join(self.els)))
        (OUT / name).write_text(svg, encoding="utf-8")
        print("%s  (content bottom y=%.0f / %d)" % (name, self.y, H))


# ════════════════ Page 12 · 16 팀 에이전트 아키텍처 ════════════════
def page12():
    p = Page("12")
    p.section("16", "팀 에이전트 아키텍처 (Supervisor 구조)")
    p.para("역할 분담이 기능별(A·B·C)에서 플랫폼별로 바뀌었습니다. 플랫폼마다 서브 슈퍼바이저가 수집부터 기획안 검증까지 "
           "맡고, 팀 총괄 슈퍼바이저는 요청을 나눠 보내고 결과를 하나로 합칩니다.")

    # 다이어그램
    top = p.y
    inner_x, inner_w = X0 + 18, CW - 36
    mid = X0 + CW / 2
    y = top + 18
    uw = text_w("크리에이터 · Next.js 화면", 13, True) + 48
    p.rect(mid - uw / 2, y, uw, 40, C["white"], rx=8, stroke=C["line"])
    p.text(mid, y + 11, "크리에이터 · Next.js 화면", 13, "Semi Bold", C["ink"], anchor_center=True)
    y += 40 + 4
    p.arrow_down(mid, y, 24)
    p.text(mid + 14, y + 5, "TeamTask  (intent · 플랫폼 · 게임/주제)", 11, "Regular", C["gray"])
    y += 24 + 4
    p.rect(inner_x, y, inner_w, 60, C["navy"], rx=8)
    p.text(mid, y + 10, "팀 총괄 슈퍼바이저", 15, "Bold", C["white"], anchor_center=True)
    p.text(mid, y + 34, "코드 라우터 + 보고서 병합 + 기획안 어댑터 (LLM 없음) · team_supervisor/", 11.5, "Regular",
           C["sub"], anchor_center=True)
    y += 60
    colw = (inner_w - 32) / 3
    centers = [inner_x + colw / 2 + k * (colw + 16) for k in range(3)]
    p.path("M%.1f %.1fV%.1fM%.1f %.1fH%.1f" % (mid, y, y + 12, centers[0], y + 12, centers[2]))
    for cx in centers:
        p.arrow_down(cx, y + 12, 20)
    y += 36
    plats = [
        (C["yt"], "YouTube", "장유림 · youtube/", ["Claude Code 스킬 + 서브에이전트 6개",
                                                 "수집 → 정규화 → 점수 → 분석 → 기획안 → 검증 → 영상 생성·검수 → 성과 기록",
                                                 "쇼츠 · 한국어 기획안 · FFmpeg 렌더"], None),
        (C["bili"], "빌리빌리", "곽우화 · bilibili/", ["Python + Claude API (Sonnet 5.5) · 워커 7개",
                                                   "수집 → 정규화 → 점수 → 분석 → 策划案 → 검증",
                                                   "이벤트·커뮤니티 반응 · 중국어 策划案"], None),
        (C["tt"], "TikTok", "조사 후 확정", ["같은 계약(XxxTask → XxxReport)으로 추가 예정",
                                         "실측 데이터 확보 후 설계"], "6 4"),
    ]
    def body_h(lines):
        return sum(len(wrap(l, colw - 28, 11.5)) for l in lines) * 11.5 * LH + 6 * (len(lines) - 1)
    ch = 14 + 4 + 8 + 15 * LH + 4 + 12 * LH + 8 + max(body_h(l) for _, _, _, l, _ in plats) + 14
    for (color, name, owner, lines, dash), cx in zip(plats, centers):
        x = cx - colw / 2
        p.rect(x, y, colw, ch, C["white"], rx=8, stroke=C["line"], dash=dash)
        p.rect(x + 14, y + 14, colw - 28, 4, color, rx=2)
        yy = y + 14 + 4 + 8
        yy += p.text(x + 14, yy, name, 15, "Bold", C["ink"]) + 4
        yy += p.text(x + 14, yy, owner, 12, "Semi Bold", C["navy"]) + 8
        for l in lines:
            yy += p.text(x + 14, yy, l, 11.5, "Regular", C["ink"], width=colw - 28) + 6
    y += ch + 10
    p.text(mid, y, "↑  YouTubeReport · BiliReport  →  총괄이 TeamReport 로 병합", 11, "Regular", C["gray"], anchor_center=True)
    y += 11 * LH + 10
    cross = "빌리빌리 → YouTube : 반응 상위 소재를 한국어 '해외 트렌드 소재 카드'로 전달 (참고용, 복제 금지)"
    cw = text_w(cross, 11.5, True) + 28
    p.rect(mid - cw / 2, y, cw, 32, C["white"], rx=6, stroke=C["bili"])
    p.text(mid, y + 8, cross, 11.5, "Semi Bold", C["ink"], anchor_center=True)
    y += 32 + 18
    p.els.insert(2, '<rect x="%d" y="%.1f" width="%d" height="%.1f" rx="8" fill="%s"/>' % (X0, top, CW, y - top, C["card"]))
    p.y = y + 22

    p.subtitle("인터페이스 계약")
    p.table([138, 196, 490], [
        ["방향", "형태", "주요 필드"],
        ["화면 → 총괄", "TeamTask", "intent (trend_scan · deep_dive · title_check · event_watch · make_video · "
                                   "performance_review), platforms, game/topic"],
        ["총괄 → 플랫폼", "BiliTask · YouTubeTask", "팀 intent 를 플랫폼 intent 로 변환 (deep_dive → game_deep_dive / topic_deep_dive)"],
        ["플랫폼 → 총괄", "BiliReport · YouTubeReport", "요약, 기회 목록, plan(plan-v1), 검증 결과, 데이터 출처, 실행 기록, 경고"],
        ["총괄 → 화면", "TeamReport", "플랫폼별 상태(ok · no_run · unsupported · error), 기획안 공통 보기(team-plan-view-v1), 해외 트렌드 소재"],
    ])
    p.subtitle("공통 원칙")
    p.cards([
        ("숫자는 코드가, 해석은 LLM 이", "점수·배수·중앙값은 결정적 코드로 계산하고, 에이전트는 계산값을 인용만 합니다."),
        ("점수는 정렬 참고용", "조회수 예측이 아니며, 예측·약속 표현은 정규식으로 찾아 제출을 막습니다."),
        ("2단 검증", "코드 규칙 검사 + LLM 의미 검토. 실패하면 기획 에이전트에게 되돌리고 수정 횟수에 상한을 둡니다."),
        ("장애 격리 · 출처 표시", "한 플랫폼이 실패해도 다른 결과는 보고합니다. 데이터는 live · snapshot · sample 로 표시합니다."),
    ])
    p.note("코드: github.com/Garyklay28/game-inspiration-platform (bilibili/ · youtube/ · team_supervisor/) — "
           "15장의 기능별 역할 분담 대신 플랫폼별로 서브 슈퍼바이저를 맡습니다.")
    p.save("page_12_team_architecture.svg")


# ════════════════ Page 13 · 17 빌리빌리 서브 슈퍼바이저 ════════════════
def page13():
    p = Page("13")
    p.section("17", "빌리빌리 서브 슈퍼바이저 (곽우화)")
    p.para("08장의 빌리빌리 모드 기능을 워커 7개로 나누고, 서브 슈퍼바이저(Claude)가 호출 순서를 정합니다. "
           "팀 流水线设计 A(수집 → 정규화 → 점수 → 분석 → 기획안 → 검증)를 따릅니다.")

    # 파이프라인
    steps = [("① 수집·정규화", "collector"), ("② 점수 (코드)", "Score_bili"),
             ("③ 분석", "trend_radar · engagement · title_doctor · localizer"),
             ("④ 策划案 생성", "plan_writer"), ("⑤ 검증", "validator")]
    gap = 22
    sw = (CW - gap * 4) / 5
    top = p.y
    sh = 14 + 13 * LH + 4 + max(len(wrap(b, sw - 20, 11)) for _, b in steps) * 11 * LH + 12
    for k, (t, b) in enumerate(steps):
        x = X0 + k * (sw + gap)
        dark = k == 1
        p.rect(x, top, sw, sh, C["navy"] if dark else C["card"], rx=8, stroke=None if dark else C["line"])
        if k in (0, 2, 3, 4):
            p.rect(x + 10, top + 8, sw - 20, 3, C["bili"], rx=1.5)
        p.text(x + 10, top + 16, t, 13, "Bold", C["white"] if dark else C["ink"])
        p.text(x + 10, top + 16 + 13 * LH + 2, b, 11, "Regular", C["sub"] if dark else C["navy"], width=sw - 20)
        if k < 4:
            ax = x + sw + 3
            p.path("M%.1f %.1fH%.1f" % (ax, top + sh / 2, ax + gap - 7))
            p.path("M%.1f %.1fL%.1f %.1fL%.1f %.1f" % (ax + gap - 12, top + sh / 2 - 5, ax + gap - 6, top + sh / 2,
                                                       ax + gap - 12, top + sh / 2 + 5))
    # 수정 루프 (⑤ → ④)
    x4 = X0 + 3 * (sw + gap) + sw / 2
    x5 = X0 + 4 * (sw + gap) + sw / 2
    ly = top + sh + 16
    p.path("M%.1f %.1fV%.1fH%.1fV%.1f" % (x5, top + sh, ly, x4, top + sh + 3))
    p.path("M%.1f %.1fL%.1f %.1fL%.1f %.1f" % (x4 - 5, top + sh + 9, x4, top + sh + 2, x4 + 5, top + sh + 9))
    p.text((x4 + x5) / 2, ly + 4, "실패 시 1회 수정", 11, "Semi Bold", C["navy"], anchor_center=True)
    y = ly + 4 + 11 * LH + 10
    out = "출력: 策划案 JSON (영상 파이프라인 B 입력) + Markdown 문서 + BiliReport → 팀 총괄"
    ow = text_w(out, 12, True) + 32
    p.rect(X0 + CW - ow, y, ow, 34, C["white"], rx=6, stroke=C["bili"])
    p.text(X0 + CW - ow / 2, y + 9, out, 12, "Semi Bold", C["ink"], anchor_center=True)
    p.y = y + 34 + 24

    p.subtitle("워커 7개")
    p.table([150, 300, 214, 160], [
        ["워커", "하는 일", "코드 도구", "08장 기능"],
        ["collector", "종합 인기·핫서치·랭킹 스냅샷 수집, 한·중·영 별칭 통일, 새 별칭 후보 제안",
         "collect_popular_games, collect_trending", "트렌드 수집"],
        ["trend_radar", "이벤트 레이더, 핫키워드 선행 신호, 공식 활동(mission_id)", "get_event_signals, get_hot_keyword_signals",
         "이벤트 레이더 · 핫키워드 · 공식 태그"],
        ["engagement_analyst", "반응률 배수, 길이·유형 분포, 소재 점수 해석", "get_engagement_ranking, score_games",
         "반응률 정렬 · 길이 제안"],
        ["title_doctor", "제목 진단(글자 수·【】·《》), 중국어 수정안", "diagnose_title, get_title_benchmark", "제목 진단"],
        ["localizer", "중국어 제목 → 한국어 해외 트렌드 소재 카드", "get_top_titles", "YouTube 모드 연결"],
        ["plan_writer", "策划案: 훅 3종 · 구간 스크립트 · 제목 3개 · 썸네일 · 저작권", "get_plan_context, lookup_evidence",
         "기획안 생성"],
        ["validator", "규칙 검사 + 의미 검토, 근거를 원본 데이터에서 직접 확인", "run_rule_checks, lookup_evidence", "검증"],
    ], size=11)

    p.subtitle("코드가 막는 것 · 데이터 · 실행 결과")
    p.cards([
        ("코드 가드레일", "수집 전 분석 · 기획안 없이 검증 · 검증 없이 최종 제출 · 조회수 예측 표현이 든 제출 · "
                     "기획안 수정 1회 초과 → 모두 코드가 거부합니다."),
        ("데이터 수집", "종합 인기(게임 카테고리)와 실시간 핫서치는 공개 API, 요청 간 1초. 랭킹 API(ranking/v2)는 "
                    "봇 차단(-352)이라 자동 수집하지 않고 사람이 저장한 스냅샷만 씁니다."),
        ("실제 실행 (2026-11-16)", "game_deep_dive 1회 약 $0.60–0.74, LLM 호출 26–30회. 4차 실행에서 검증 워커가 원본 데이터를 "
                                 "13회 조회했고, 1차 기획안의 문제 3건이 수정본에서 해결됐습니다."),
        ("모델 · 언어", "전 에이전트 claude-sonnet-5-5. 시스템 프롬프트 8개는 한국어, 策划案 본문은 간체 중국어. "
                     "오프라인 테스트 22개(가짜 LLM 포함)."),
    ])
    p.note("코드: github.com/Garyklay28/game-inspiration-platform/tree/main/bilibili")
    p.save("page_13_bilibili_supervisor.svg")


if __name__ == "__main__":
    page12()
    page13()
