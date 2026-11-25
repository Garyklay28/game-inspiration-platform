"""전역 설정. 모든 값은 환경 변수(.env)로 덮어쓸 수 있다."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv 없이도 동작
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
ASIDE_DIR = DATA_DIR / "aside"            # Aside 브라우저가 내보낸 CSV (1순위 데이터)
PERFORMANCE_DIR = DATA_DIR / "performance"  # 업로드 등록·성과 기록
ASIDE_MAX_AGE_H = float(os.getenv("BILI_ASIDE_MAX_AGE_H", "48"))  # 이보다 오래된 Aside 파일은 공개 API 로 대체
# 게시된 지 이 일수보다 오래된 영상은 '지금의 트렌드'가 아니므로 풀에서 뺀다.
# (2026-11-25 Aside 수집에서 '游戏区排行榜' 45개가 모두 2025-04 영상 — 구 카테고리 랭킹이 그때 멈춰 있음)
MAX_VIDEO_AGE_DAYS = float(os.getenv("BILI_MAX_VIDEO_AGE_DAYS", "30"))
MIN_FRESH_VIDEOS = int(os.getenv("BILI_MIN_FRESH_VIDEOS", "30"))  # 신선한 영상이 이보다 적으면 공개 API 로 보충
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# ── Claude ──────────────────────────────────────────────
# 모든 에이전트가 같은 모델을 사용한다(팀 결정: Sonnet 5.5).
MODEL = os.getenv("BILI_AGENT_MODEL", "claude-sonnet-5-5")
MAX_TOKENS = int(os.getenv("BILI_AGENT_MAX_TOKENS", "8000"))
# 안전 분류기가 요청을 거절(refusal)하면 서버 측에서 대체 모델로 자동 재시도한다.
ENABLE_REFUSAL_FALLBACK = os.getenv("BILI_AGENT_FALLBACK", "1") == "1"
# 슈퍼바이저 루프 / 워커 루프의 최대 반복 횟수(무한 루프 방지)
SUPERVISOR_MAX_STEPS = int(os.getenv("BILI_SUPERVISOR_MAX_STEPS", "12"))  # 워커 7개 + 검증 루프 1회 + 여유
WORKER_MAX_STEPS = int(os.getenv("BILI_WORKER_MAX_STEPS", "6"))
# 비용 추정용 단가(USD / 100만 토큰, 입력·출력). 2026-11 Anthropic 공시 기준, 캐시 할인 미반영.
PRICE_PER_MTOK = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0), "claude-haiku-5-5": (0.10, 0.50)}

# ── 빌리빌리 수집 ────────────────────────────────────────
HTTP_TIMEOUT = float(os.getenv("BILI_HTTP_TIMEOUT", "10"))
# 공개 API 요청 사이 최소 간격(초). 기획안 리스크 매트릭스: "요청 빈도 제한"
REQUEST_INTERVAL = float(os.getenv("BILI_REQUEST_INTERVAL", "1.0"))
POPULAR_PAGES = int(os.getenv("BILI_POPULAR_PAGES", "5"))  # 종합 인기 몇 페이지까지 볼지
OFFLINE = os.getenv("BILI_OFFLINE", "0") == "1"  # 1이면 네트워크 없이 스냅샷만 사용

# ── Supabase (선택) ──────────────────────────────────────
# 두 값이 모두 있으면 별칭 사전을 Supabase에서 읽고, 없으면 data/alias_dictionary.json 사용
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
