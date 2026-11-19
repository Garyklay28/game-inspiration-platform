# AGENTS.md — YouTube 쇼츠 에이전트 파이프라인

이 저장소는 YouTube 게임 쇼츠(기본: 로블록스)를 **트렌드 수집 → 정규화 → 점수화 → 분석 → 기획안 → 영상 생성 → 성과 기록** 순서로 만든다.
작업 절차는 `.claude/skills/youtube-pipeline/SKILL.md`, 편집 절차는 `.claude/skills/video-edit/SKILL.md` 를 따른다.

## 프로젝트 구조

```
config/pipeline.json        모든 숫자 설정(지역·카테고리·가중치·영상 규격·검수 기준)
config/alias_dictionary.json 게임 별칭 사전 (한·영 표기 → topic_id)
yt_pipeline/                결정적 도구(코드). python -m yt_pipeline <명령>
runs/<run_id>/              실행 하나의 모든 산출물 (단계 번호 = 파일 번호)
  01_raw.json 02_normalized.json 03_scores.json 04_evidence.json   ← 코드가 쓴다
  04_analysis.json 05_plan.json                                     ← 에이전트가 쓴다
  06_validation.json 05_plan.md report.json trace.jsonl            ← 코드가 쓴다
  07_video/ script.json(에이전트) timing.json subs.* voice.wav edit.json output/
clips/                      원본 클립 — 읽기 전용
audio/                      BGM·효과음 (출처는 CREDITS.txt)
performance/                업로드 영상 ↔ 기획안 연결, 성과 기록
```

## 규격 (숫자로 고정)

- 최종: 1080×1920, 30fps, H.264(libx264, crf 20), AAC 192k / 프리뷰: 720×1280, crf 30
- 쇼츠 길이: 기획 15~60초, 업로드 상한 180초
- 자막: 한 줄 16자, 최대 2줄, 하단 중앙(MarginV 420px), Noto Sans CJK KR
- BGM 볼륨 0.25, 끝 1초 페이드아웃, 내레이션이 나올 때 자동 덕킹
- 검수 허용 오차: 길이 ±0.5초 / 무음 −40dB·1초 / 검은 화면 0.5초

## 규칙

1. 순서를 지킨다. 앞 단계 파일이 없으면 다음 단계를 하지 않는다. `python -m yt_pipeline status` 로 확인한다.
2. **숫자는 코드가, 해석은 에이전트가.** 점수·배수·중앙값은 `03_scores.json`·`04_evidence.json` 의 값을 그대로 옮긴다. 새 숫자를 만들지 않는다. 모든 주장에는 `evidence_refs`(예: `evidence.topics.doors.duration_buckets`, `video:<id>`)를 단다.
3. **점수는 정렬 참고용이다.** 조회수·구독·반응을 예측하는 표현("떡상할 것", "100만 나올 것")을 쓰지 않는다. 규칙 검사가 막는다.
4. 데이터는 공식 YouTube Data API v3 또는 사람이 저장한 파일만 쓴다. 스크래핑·로그인 우회를 하지 않는다. 샘플 데이터(`is_sample: true`)로 만든 기획은 연습용으로만 쓴다.
5. `edit.json` 한 파일이 편집 기준이다. 에이전트는 이 파일을 고치고, FFmpeg 은 이 파일대로만 실행한다. 수정은 값 하나 단위로 한다.
6. 계획 먼저, 렌더는 나중. 렌더 전에 `video render --plan-only` 로 명령을 보여 주고 승인을 받는다. 프리뷰(720p) → 검수 → 승인 → 최종 순서. 코드가 순서를 강제한다.
7. 한 번에 한 가지만 고친다(컷·자막·색·음악을 한 요청에 섞지 않는다).
8. 원본 `clips/` 는 수정하지 않는다. 결과물은 `_v1`, `_v2` 로 버전을 올리고 덮어쓰지 않는다.
9. 레퍼런스 영상에서는 형식만 가져온다. 다른 크리에이터의 화면·음성·음악을 가져오지 않는다. 게임 화면은 직접 녹화한 것만 쓴다.
10. 음악·음성·글꼴의 출처와 라이선스를 `CREDITS.txt` 에 적는다. 없으면 `video check` 가 렌더를 막는다.
11. API 키는 `.env` 에만 둔다. 채팅에 붙여 넣거나 출력하지 않는다. `.env` 를 읽지 않는다.

## 사람이 정할 것 (에이전트가 대신 정하지 않는다)

- 어떤 기획안으로 영상을 만들지, 컷 리듬·타이밍의 최종 판단
- 음악 선택과 색 느낌, 생성 크레딧·API 비용 승인
- 음원·폰트·소스의 저작권 확인
- 최종본 공개(업로드) 여부 — 에이전트는 업로드·게시·공유를 하지 않는다

## 완료 기준

- `06_validation.json` status 가 `validated`
- 최종 mp4 의 `.qa.json` verdict 가 `PASS` 이고 `visual_review.passed` 가 true
- 완료 보고에 세 가지를 나눠 적는다: **측정으로 확인한 것**, **확인하지 못한 것**(예: 직접 청취), **사람이 확인해야 할 것**(qa.json 의 human_checks)

## 금지

- 검증하지 않은 기획안·영상을 "완료"로 보고하지 않는다.
- `--force` 는 테스트 외에 쓰지 않는다.
- 요청받지 않은 게시·업로드·공유·메시지 전송을 하지 않는다.
