# bilibili-supervisor-agent

게임 영상 크리에이터 원스톱 인스피레이션 플랫폼 — **빌리빌리 서브 슈퍼바이저 에이전트** (Proof of Concept)

- 기획안(Figma): 「게임 영상 인스피레이션 플랫폼 - 화면 설계」 08 빌리빌리 모드 *"이벤트 중심 + 커뮤니티 반응"*
- 담당: 빌리빌리 파트 전체 (역할 분담이 기획안의 기능별 → 플랫폼별로 변경됨)
- 언어: Python 3.9+ / Claude API (Anthropic 공식 Python SDK, 프레임워크 없이 tool use 루프 직접 구현)

## 한눈에 보기

```
총괄 슈퍼바이저 (팀) ──BiliTask──▶ 빌리빌리 서브 슈퍼바이저 ──delegate──▶ collector
                    ◀─BiliReport──        (Claude)                 ├────▶ trend_radar
                                                                    ├────▶ engagement_analyst
                                                                    ├────▶ title_doctor
                                                                    ├────▶ localizer
                                                                    ├────▶ plan_writer ─┐ 실패 시
                                                                    └────▶ validator ◀──┘ 1회 수정
```

팀 **流水线设计 A**(采集 → 规范化 → 评分 → 分析 → 策划案生成 → 校验)를 빌리빌리용으로 구현했고, 최종 산출물은 **策划案 JSON**(영상 파이프라인 B의 입력) + 팀 공유용 Markdown 문서입니다.

| 워커 | 기획안 기능 |
|---|---|
| `collector` | 트렌드 수집·정규화 (종합 인기/핫서치/랭킹 스냅샷, 한·중·영 별칭 통일, 새 별칭 후보 제안) |
| `trend_radar` | 이벤트 레이더 · 핫키워드 선행 신호 · 공식 이벤트 태그 |
| `engagement_analyst` | 반응률 정렬(Top 풀 중앙값 대비 배수) · 영상 길이 제안 · 유형 분포 · 소재 점수 |
| `title_doctor` | 제목 진단(글자 수·【】·《》) · 중국어 수정안 |
| `localizer` | 중국어 제목 → 한국어 '해외 트렌드 소재' 카드 (YouTube·TikTok 모드 연결) |
| `plan_writer` | 策划案 생성(간체 중국어): 훅 3종 · 구간별 스크립트 · 제목 3개 · 썸네일 brief · 저작권 체크리스트 |
| `validator` | 策划案 검증: 코드 규칙 검사(구조·시간·저작권·'仅供排序参考'·예측 표현) + LLM 의미 검토 |

자세한 구조, 설계 원칙, 기획안 매핑은 **[docs/architecture.md](docs/architecture.md)**.
시스템 프롬프트는 **[bili_agent/prompts/](bili_agent/prompts/)** (한국어).

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # ANTHROPIC_API_KEY 입력
```

```bash
# 1) API 키 없이: 데이터 수집·지표 계산 파이프라인만 (LLM 호출 0회)
python main.py --intent trend_scan --dry-run

# 2) 슈퍼바이저 에이전트 실행 (Claude API 호출)
python main.py --intent trend_scan
python main.py --intent game_deep_dive --game 英雄联盟
python main.py --intent title_check --title "BLG夺冠了！S16决赛全程回顾"
python main.py --intent event_watch

# 3) 테스트 (네트워크·API 키 불필요, 가짜 LLM 사용)
python -m pytest -q
```

결과는 터미널에 에이전트 실행 기록·요약·사용량·경고가 출력되고, 전체 `BiliReport`는 `outputs/report_*.json`에 저장됩니다.
`trend_scan` / `game_deep_dive` 는 策划案도 만들어 `outputs/report_*_plan.json`(B 파이프라인 입력)과 `*_plan.md`(팀 공유 문서)를 함께 저장합니다.

## 데이터 수집 원칙

빌리빌리 API는 공식 개방 API가 아니므로 **공개적으로 열려 있는 엔드포인트만**, 로그인·쿠키 위조·서명 우회 없이, 요청 간 1초 간격으로 호출합니다.

| 데이터 | 방식 |
|---|---|
| 종합 인기(게임 카테고리) | 실시간 공개 API → 실패 시 `data/snapshots/popular_game_*.json` |
| 실시간 핫서치 | 실시간 공개 API → 실패 시 `data/snapshots/trending_*.json` |
| 게임 카테고리 랭킹 | 봇 차단(-352)이라 **자동 호출하지 않음** → 사람이 저장한 스냅샷만 사용 |

### 랭킹 스냅샷 저장 (사람이 직접)
1. 브라우저로 `https://www.bilibili.com` 을 연다.
2. `https://api.bilibili.com/x/web-interface/ranking/v2?rid=4&type=all` 을 열고 `⌘+S` / `Ctrl+S`.
3. `data/snapshots/ranking_game_YYYYMMDD.json` 으로 저장. 가장 최신 파일을 자동으로 읽습니다.

오프라인 대체 스냅샷 갱신: `python -m scripts.save_snapshots`

## 파일 구조

```
bili_agent/
  contracts.py          총괄 ↔ 빌리빌리 인터페이스 (BiliTask / BiliReport)
  config.py             모델·수집 설정 (.env)
  workspace.py          공유 작업 공간(블랙보드)
  agents/
    supervisor.py       빌리빌리 서브 슈퍼바이저 (LLM 모드 / dry-run 모드), 검증 루프, 보고서 조립
    workers.py          7개 워커: 도구 스키마 + 핸들러 + 제출 스키마, 策划案 조립
    loop.py             Claude API 호출, 공용 tool-use 루프, 오류·거절·제출 거부 처리
  prompts/              시스템 프롬프트 8개 (supervisor + 워커 7)
  tools/
    bilibili_api.py     공개 API 수집 + 스냅샷 대체
    metrics.py          반응률·배수·길이/유형 분포·제목 진단·Score_bili (결정적 계산)
    plan_rules.py       策划案 규격·규칙 검사·예측 표현 차단·Markdown 변환
    alias_store.py      별칭 사전 (로컬 JSON / Supabase)
data/                   별칭 사전, 스냅샷
supabase/schema.sql     game_alias, bili_video_snapshot, bili_agent_report 등
docs/architecture.md    아키텍처 문서
tests/                  오프라인 테스트 (가짜 LLM 포함)
```

## Supabase

`supabase/schema.sql`로 테이블을 만들고 `.env`에 `SUPABASE_URL`, `SUPABASE_KEY`를 넣으면 별칭 사전을 Supabase에서 읽습니다. 값이 없으면 `data/alias_dictionary.json`을 씁니다(같은 인터페이스).

## 한계

- 영상 유형은 키워드 규칙 분류라 '기타' 비중이 큼. 별칭 사전(15개 게임) 밖의 게임은 집계에서 빠짐 → collector의 `alias_candidates` 제안을 사람이 검토해 사전에 반영.
- 이벤트 날짜(캘린더)는 수집하지 않음. 공식 활동(`mission_id`)과 핫서치로만 감지.
- 점수 가중치는 초기 동일 가중치. 성과 데이터 누적 후 보정 예정.
