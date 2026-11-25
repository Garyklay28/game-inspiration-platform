"""에이전트(워커) 공통 정의.

WorkerSpec 하나 = 기획안 12장의 에이전트 하나.
- uses_llm=True  : 시스템 프롬프트 + 전용 도구 + 제출 도구로 Claude 가 판단 (tool-use 루프)
- uses_llm=False : 결정적 코드만 실행 (예: 3 점수화 — 기획안 12장 "계산 코드만 사용, LLM 없음")
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .. import config

Handler = Callable[..., Dict[str, Any]]
STR_LIST = {"type": "array", "items": {"type": "string"}}
GAME_ID_PROP = {"game_id": {"type": "string", "description": "표준 game_id(예: league_of_legends). 생략하면 전체 풀."}}


def tool(name: str, description: str, props: Optional[Dict] = None, required: Optional[List[str]] = None) -> Dict:
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props or {}, "required": required or []}}


def submit(props: Dict, required: List[str], description: str = "") -> Dict:
    return tool("submit_findings",
                description or "작업 결과를 슈퍼바이저에게 제출하고 종료한다. 반드시 마지막에 한 번 호출.",
                {"summary_ko": {"type": "string", "description": "한국어 요약"}, **props},
                ["summary_ko"] + required)


@dataclass
class WorkerSpec:
    name: str                      # 코드 이름 (collector, normalizer, ...)
    stage: str                     # 기획안 12장 단계 (1 수집 ...)
    db_tables: List[str]           # 기획안 13장에서 쓰는 테이블
    uses_llm: bool = True
    prompt_file: Optional[str] = None
    tools: List[Dict] = field(default_factory=list)
    handlers: Dict[str, Handler] = field(default_factory=dict)
    submit_tool: Optional[Dict] = None
    requires: Optional[str] = None  # 먼저 끝나 있어야 하는 에이전트 (수직 순서 가드레일)
    pre_run: Optional[Callable[..., Dict]] = None   # LLM 루프 전에 코드가 먼저 하는 결정적 작업 (결과를 첫 메시지에 넣음)
    run_code: Optional[Callable[..., Dict]] = None  # 단계 전체를 코드가 직접 진행할 때 (점수화, 기획안 단계 내부 루프)

    @property
    def system_prompt(self) -> str:
        return (config.PROMPT_DIR / self.prompt_file).read_text(encoding="utf-8")

    @property
    def all_tools(self) -> List[Dict]:
        return self.tools + ([self.submit_tool] if self.submit_tool else [])
