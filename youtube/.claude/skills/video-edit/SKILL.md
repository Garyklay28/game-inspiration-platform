---
name: video-edit
description: clips/ 의 클립을 edit.json 대로 이어 붙이고 자막·내레이션·음악을 넣어 쇼츠 mp4 로 렌더하고 검수한다. 편집, 컷, 자막, BGM, 세로 버전, 다시 렌더 요청 시 사용.
allowed-tools: Read, Write, Edit, Bash(python -m yt_pipeline video *), Bash(python -m yt_pipeline qa *), Bash(python -m yt_pipeline status*), Bash(ffprobe *), Bash(ffmpeg *)
---

# 영상 편집

1. `ffprobe` 로 `clips/` 의 모든 클립 규격(해상도·fps·길이·코덱·오디오 유무)을 표로 보고한다.
2. `edit.json` 을 작성하고 승인을 받는다 (`runs/<id>/07_video/edit.draft.json` 에서 시작).
3. 720p 프리뷰를 먼저 렌더한다: `python -m yt_pipeline video render --run <id>`
4. 검수(qa-reviewer) PASS + 사용자 승인 후 최종 렌더: `--final` → `output/final_vN.mp4`
5. 원본 `clips/` 는 수정하지 않는다. 결과는 버전을 올려 저장한다(코드가 자동으로 _v2, _v3).

## edit.json (편집의 유일한 기준)

```json
{
  "plan_id": "yt-…",
  "output": {"size": "1080x1920", "fps": 30},
  "timeline": [
    {"clip": "clips/shot_01.mp4", "in": 0.0, "out": 3.5, "crop_x": 0.5, "transition": "cut"},
    {"clip": "clips/shot_02.mp4", "in": 0.8, "out": 5.0, "crop_x": 0.3, "transition": "fadein"}
  ],
  "captions": "runs/<id>/07_video/subs.ass",
  "voice": "runs/<id>/07_video/voice.wav",
  "clip_audio": 0.0,
  "bgm": {"file": "audio/bgm.mp3", "volume": 0.25, "fade_out": 1.0, "duck": true}
}
```
- `in`/`out`: 초 단위(타임코드). "중간쯤" 같은 말 대신 `shot_03 의 1.2~4.0초` 처럼 정한다.
- `crop_x`: 가로 클립을 세로로 자를 때 가로 위치(0=왼쪽, 0.5=가운데, 1=오른쪽). 인물·캐릭터가 중앙에 오게 샷마다 정한다.
- `transition`: `cut` 또는 `fadein`(0.25초).
- `clip_audio`: 게임 원래 소리 볼륨(0~1). 모든 클립에 오디오가 있어야 적용.
- 타임라인 합계(out−in)는 `timing.json` 의 total 과 ±0.5초 안이어야 한다(`video check` 가 확인).
- BGM 은 `CREDITS.txt` 에 파일명·곡명·작곡가·라이선스가 있어야 렌더된다.

## 수정은 값 하나씩

| 요청 예 | 바꿀 곳 |
|---|---|
| "shot_02 시작을 0.5초 늦춰줘" | timeline[1].in (+0.5) 과 out (+0.5, 길이 유지) |
| "자막 위치만 60px 위로" | config/pipeline.json `video.subtitle.margin_v` +60 → `video timing` 다시 |
| "이 문장 앞에 쉼 넣어줘" | script.json 해당 줄 `pause` → `video timing` → 타임라인 길이 재조정 |
| "내레이션 단어가 빠졌어" | 그 문장 voice wav 만 다시 만들기 → `video timing` |
| "BGM 줄여줘" | bgm.volume (0.25 → 0.18) |
| "세로로 다시, 인물 중앙" | 샷마다 crop_x 정하고 샷별 프레임을 한 장씩 보여 준 뒤 승인받고 렌더 |

`timing.json` 은 자동 생성 파일이라 직접 고치지 않는다.

## 검수 (렌더 결과를 Claude 가 직접 확인)

```
프리뷰 렌더 720p → ffprobe 규격 → 프레임 추출 → silencedetect·blackdetect → qa-reviewer PASS/FAIL
```
`python -m yt_pipeline qa --run <id> --file runs/<id>/07_video/output/preview_v1.mp4`
FAIL 이면 edit.json 을 고쳐 `_v2` 로 다시 렌더하고 재검수한다.

## 프롬프트 템플릿

- **컷 편집** (클립을 처음 모았을 때): "clips/ 의 모든 클립을 ffprobe 로 점검해 표로 보여줘. 정지 구간과 깨진 프레임을 찾아 잘라낼 구간을 edit.json 으로 제안해줘. 렌더는 하지 마."
- **자막** (내레이션이 있을 때): "script.json 의 대사를 timing 에 맞춰 자막으로 만들어줘. 한 줄 16자 이내, 최대 2줄. 하단 중앙에 넣고 3초와 10초 지점 프레임을 뽑아 가독성을 확인해줘."
- **세로 버전**: "output/final_v1.mp4 를 1080×1920 으로 다시 만들어줘. 인물이 중앙에 오도록 샷마다 crop_x 를 정하고, 샷별 프레임을 한 장씩 보여준 뒤 승인받고 렌더해줘."
