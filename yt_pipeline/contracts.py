"""팀 총괄 슈퍼바이저 ↔ YouTube 파트 인터페이스.

빌리빌리 파트(BiliTask → BiliReport)와 같은 모양(XxxTask → XxxReport)이라
총괄 슈퍼바이저는 플랫폼만 바꿔 끼우면 된다. plan 필드는 공통 plan-v1(텍스트는 한국어).
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

INTENTS = ("trend_scan", "topic_deep_dive", "make_video", "performance_review")


@dataclass
class YouTubeTask:
    intent: str
    topic: Optional[str] = None      # 한·영 아무 표기 (별칭 사전으로 통일)
    source: str = "api"              # api / file / sample
    note: str = ""
    task_id: str = "local-demo"

    def __post_init__(self):
        if self.intent not in INTENTS:
            raise ValueError("intent must be one of %s" % (INTENTS,))


@dataclass
class YouTubeReport:
    task_id: str
    intent: str
    run_id: str
    summary_ko: str
    opportunities: List[Dict[str, Any]] = field(default_factory=list)
    duration_advice: Optional[Dict[str, Any]] = None
    alias_candidates: List[Dict[str, Any]] = field(default_factory=list)
    plan: Optional[Dict[str, Any]] = None
    plan_validation: Optional[Dict[str, Any]] = None
    video: Optional[Dict[str, Any]] = None          # 렌더 결과 경로 + QA 판정
    performance: Optional[Dict[str, Any]] = None
    data_sources: List[Dict[str, Any]] = field(default_factory=list)
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    platform: str = "youtube"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
