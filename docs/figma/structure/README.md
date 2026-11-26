# 상세 구조도 — Figma 용 보드

[docs/structure.md](../../structure.md) 의 Mermaid 그림 25개를 장(章)별 보드 8장으로 묶은 파일입니다.

| 파일 | 내용 | 그림 수 |
|---|---|---|
| `board0_legend` | 그림 읽는 법 (범례 · 공통 원칙) | 1 |
| `board1_overview` | 전체 지도 | 1 |
| `board2_team_supervisor` | 팀 총괄 슈퍼바이저 (처리 흐름 ①② · intent 라우팅 · 데이터 계약 · 기획안 공통 보기) | 5 |
| `board3_bilibili` | 빌리빌리 분기 (전체 · 실행 순서 · intent별 경로 · 에이전트 1~6) | 9 |
| `board4_youtube` | YouTube 분기 (전체 · 기획안/검증 · 썸네일 · 영상 생성 · 성과 기록 · 점수) | 6 |
| `board5_tiktok` | TikTok 분기 (예정) | 1 |
| `board6_team_db` | 팀 공용 DB (ER 다이어그램) | 1 |
| `board7_cross_platform` | 빌리빌리 → YouTube 교차 소재 | 1 |

## Figma

**이미 들어가 있음:** 기획안 파일의 [「상세 구조도」 페이지](https://www.figma.com/design/QZJ3Ha10jKuiiH2awBCX0D/?node-id=113-2) — 장별 섹션 8개, 모두 편집 가능한 벡터·텍스트 레이어(글꼴은 기획안과 같은 Inter).

다시 넣을 때:

1. `board*.svg` 를 페이지에 넣는다 (Finder 에서 끌어다 놓거나 Figma MCP `upload_assets`).
2. [`tools/figma_post_import.js`](tools/figma_post_import.js) 의 `PAIRS` 에 보드·섹션 ID 를 적고 `use_figma` 로 실행한다.
   - ∗ → * 복원, `&lt;` 등 복원, 제목 백틱 제거
   - 글꼴이 Inter 로 바뀌며 넓어진 줄을 원래 폭(레이어 이름 `c<폭>_n`)으로 다시 가운데 정렬
   - 섹션 배치, 텍스트 레이어 이름을 내용으로

Figma 의 SVG 가져오기는 tspan 줄바꿈 위치·`dominant-baseline`·`text-anchor`·`<marker>`·CSS class 를 무시하므로, 생성 단계에서 모두 좌표·도형·속성으로 풀어 둔다.

`board*.png` 는 미리보기·대체용입니다 (긴 변 4096px 이하 — Figma 는 그보다 큰 이미지를 줄여서 넣음). 수정이 필요 없으면 PNG 를 넣어도 됩니다.

## 다시 만들기 (structure.md 를 고친 뒤)

```bash
python docs/figma/structure/tools/gen_boards.py docs/structure.md docs/figma/structure/tools/boards.html docs/figma/structure/tools/boards_template.html
python docs/figma/structure/tools/board_server.py 8766      # 다른 터미널에서 실행해 둔다
# 브라우저로 http://localhost:8766/boards.html 을 열면 이 폴더의 board*.svg / *.png 가 새로 저장된다
```

변환 내용: Mermaid 를 HTML 라벨 없이(순수 SVG 글자) 렌더한 뒤, CSS 스타일·화살표(marker)·글자 정렬을 요소 속성과 도형으로 풀어 Figma 가져오기에서 빠지는 것이 없게 했다.
