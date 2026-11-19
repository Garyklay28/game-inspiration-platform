"""사용자(화면) ↔ 팀 총괄 슈퍼바이저 인터페이스."""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TEAM_INTENTS = ("trend_scan", "deep_dive", "title_check", "event_watch", "make_video", "performance_review")
PLATFORMS = ("bilibili", "youtube")

# 팀 intent → 각 파트 intent. None 이면 그 플랫폼은 해당 intent 를 지원하지 않음.
INTENT_MAP = {
    "trend_scan":         {"bilibili": "trend_scan",     "youtube": "trend_scan"},
    "deep_dive":          {"bilibili": "game_deep_dive", "youtube": "topic_deep_dive"},
    "title_check":        {"bilibili": "title_check",    "youtube": None},
    "event_watch":        {"bilibili": "event_watch",    "youtube": None},
    "make_video":         {"bilibili": None,             "youtube": "make_video"},
    "performance_review": {"bilibili": None,             "youtube": "performance_review"},
}


@dataclass
class TeamTask:
    intent: str
    platforms: Tuple[str, ...] = PLATFORMS
    game: Optional[str] = None            # 빌리빌리 게임(한·중·영)
    topic: Optional[str] = None           # YouTube 주제(한·영)
    title: Optional[str] = None           # title_check 용 (빌리빌리, 중국어)
    youtube_run_id: Optional[str] = None  # 비우면 가장 최근 실행
    task_id: str = "team-demo"

    def __post_init__(self):
        if self.intent not in TEAM_INTENTS:
            raise ValueError("intent must be one of %s" % (TEAM_INTENTS,))
        bad = [p for p in self.platforms if p not in PLATFORMS]
        if bad:
            raise ValueError("unknown platform(s): %s" % bad)


@dataclass
class TeamReport:
    task_id: str
    intent: str
    summary_ko: str
    platforms: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # 플랫폼별 상태·요약·원본 보고서
    plans: List[Dict[str, Any]] = field(default_factory=list)           # team-plan-view-v1 목록
    opportunities: List[Dict[str, Any]] = field(default_factory=list)   # 플랫폼 표시가 붙은 기회 목록
    cross_platform: Dict[str, Any] = field(default_factory=dict)        # 빌리빌리 → YouTube 해외 트렌드 소재 등
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
