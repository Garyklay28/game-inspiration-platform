"""총괄 슈퍼바이저 ↔ 빌리빌리 서브 슈퍼바이저 사이의 인터페이스 계약.

총괄 슈퍼바이저(팀원 담당)는 BiliTask를 만들어 넘기고, BiliReport(JSON)를 돌려받는다.
YouTube / TikTok 서브 슈퍼바이저도 같은 형태(XxxTask → XxxReport)를 따르면
총괄 슈퍼바이저가 플랫폼을 바꿔 끼울 수 있다.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

INTENTS = ("trend_scan", "game_deep_dive", "title_check", "event_watch")


@dataclass
class BiliTask:
    """총괄 슈퍼바이저 → 빌리빌리 서브 슈퍼바이저 요청."""

    intent: str  # INTENTS 중 하나
    game: Optional[str] = None  # 한·중·영 아무 표기나 가능 (별칭 사전으로 통일)
    user_title: Optional[str] = None  # title_check 일 때 진단할 제목(중국어)
    period_days: int = 7
    note: str = ""  # 총괄 슈퍼바이저가 덧붙이는 자유 지시
    task_id: str = "local-demo"

    def __post_init__(self):
        if self.intent not in INTENTS:
            raise ValueError("intent must be one of %s, got %r" % (INTENTS, self.intent))
        if self.intent == "title_check" and not self.user_title:
            raise ValueError("title_check 에는 user_title 이 필요합니다")

    def to_prompt(self) -> str:
        lines = ["[BiliTask]", "task_id: %s" % self.task_id, "intent: %s" % self.intent,
                 "period_days: %d" % self.period_days]
        if self.game:
            lines.append("game: %s" % self.game)
        if self.user_title:
            lines.append("user_title: %s" % self.user_title)
        if self.note:
            lines.append("note: %s" % self.note)
        return "\n".join(lines)


@dataclass
class BiliReport:
    """빌리빌리 서브 슈퍼바이저 → 총괄 슈퍼바이저 응답."""

    task_id: str
    intent: str
    summary_ko: str
    opportunities: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    title_diagnosis: Optional[Dict[str, Any]] = None
    duration_advice: Optional[Dict[str, Any]] = None
    overseas_trend_cards: List[Dict[str, Any]] = field(default_factory=list)
    alias_candidates: List[Dict[str, Any]] = field(default_factory=list)  # 별칭 사전 추가 제안(사람 검토용)
    plan: Optional[Dict[str, Any]] = None  # 流水线设计 A 의 출력 = B 의 입력 (策划案 JSON)
    plan_validation: Optional[Dict[str, Any]] = None  # 규칙 검사 + 검증 워커 판정
    data_sources: List[Dict[str, Any]] = field(default_factory=list)
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, Any] = field(default_factory=dict)  # LLM 호출 수·토큰·추정 비용
    warnings: List[str] = field(default_factory=list)
    platform: str = "bilibili"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
