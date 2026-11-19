"""Claude API 호출과 공용 tool-use 루프 (슈퍼바이저·워커가 같은 루프를 쓴다).

- Anthropic 공식 Python SDK(anthropic)의 messages API 를 직접 사용한다(프레임워크 없음).
- 종료 조건: 지정한 '종료 도구'(submit_findings / submit_report)가 호출되면 끝.
- 모델이 도구 없이 대화를 끝내면 한 번 더 제출을 요청한다(강제 tool_choice 는 이 모델에서 400).
"""
import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import anthropic

from .. import config
from ..workspace import Workspace

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLM:
    """얇은 래퍼: 모델·토큰·거절 시 대체 모델 설정을 한곳에 모은다."""

    def __init__(self, client: Optional[anthropic.Anthropic] = None):
        self.client = client or anthropic.Anthropic()

    def create(self, system: str, messages: List[Dict], tools: List[Dict]):
        kwargs: Dict[str, Any] = dict(model=config.MODEL, max_tokens=config.MAX_TOKENS,
                                      system=system, messages=messages, tools=tools)
        if config.ENABLE_REFUSAL_FALLBACK:
            # 안전 분류기가 거절하면 서버가 같은 요청을 대체 모델로 다시 실행한다.
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        return self.client.beta.messages.create(**kwargs)


def run_tool_loop(
    llm: LLM,
    ws: Workspace,
    agent_name: str,
    system: str,
    tools: List[Dict],
    handlers: Dict[str, Callable[..., Dict]],
    first_message: str,
    terminal_tool: str,
    max_steps: int,
    terminal_check: Optional[Callable[[Dict], Optional[str]]] = None,
) -> Tuple[Optional[Dict], List[str]]:
    """도구 호출 루프. (종료 도구의 입력, 경고 목록)을 돌려준다.

    terminal_check 가 오류 문자열을 돌려주면 제출을 거부하고(is_error) 모델에게 고치게 한다.
    """
    messages: List[Dict] = [{"role": "user", "content": first_message}]
    warnings: List[str] = []
    nudged = False
    for step in range(max_steps):
        t0 = time.time()
        try:
            resp = llm.create(system, messages, tools)
        except anthropic.RateLimitError as exc:
            warnings.append("%s: 요청 한도 초과(429) - %s" % (agent_name, exc))
            ws.log(agent_name, "api_error", "429", ok=False)
            return None, warnings
        except anthropic.APIStatusError as exc:
            warnings.append("%s: API 오류 %s - %s" % (agent_name, exc.status_code, exc.message))
            ws.log(agent_name, "api_error", str(exc.status_code), ok=False)
            return None, warnings
        except anthropic.APIConnectionError as exc:
            warnings.append("%s: 네트워크 오류 - %s" % (agent_name, exc))
            ws.log(agent_name, "api_error", "connection", ok=False)
            return None, warnings
        in_tok, out_tok = _record_usage(ws, resp)
        ws.log(agent_name, "llm_turn", "step=%d stop=%s %.1fs in=%d out=%d" % (
            step + 1, resp.stop_reason, time.time() - t0, in_tok, out_tok))

        if resp.stop_reason == "refusal":
            warnings.append("%s: 모델이 요청을 거절함(refusal)" % agent_name)
            return None, warnings

        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]

        if not tool_uses:
            if resp.stop_reason == "max_tokens" or nudged:
                warnings.append("%s: 결과를 제출하지 않고 종료(stop=%s)" % (agent_name, resp.stop_reason))
                return None, warnings
            nudged = True
            messages.append({"role": "user", "content":
                             "아직 `%s` 도구를 호출하지 않았습니다. 지금 `%s`로 결과를 제출하세요." % (terminal_tool, terminal_tool)})
            continue

        results, terminal_input = [], None
        for tu in tool_uses:
            if tu.name == terminal_tool:
                problem = terminal_check(dict(tu.input)) if terminal_check else None
                if problem:
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                    "content": "제출 거부: " + problem})
                    ws.log(agent_name, "submit_rejected", problem, ok=False)
                    continue
                terminal_input = dict(tu.input)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "제출 완료"})
                ws.log(agent_name, "submit", tu.name)
                continue
            results.append(_execute(ws, agent_name, handlers, tu))
        if terminal_input is not None:
            return terminal_input, warnings
        # 병렬 도구 호출 결과는 하나의 user 메시지로 함께 돌려준다.
        messages.append({"role": "user", "content": results})

    warnings.append("%s: 최대 단계(%d) 도달" % (agent_name, max_steps))
    return None, warnings


def _record_usage(ws: Workspace, resp) -> Tuple[int, int]:
    """토큰 사용량을 누적한다(비용 확인용)."""
    usage = getattr(resp, "usage", None)
    in_tok = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    out_tok = getattr(usage, "output_tokens", 0) or 0
    total = ws.cache.setdefault("usage", {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0})
    total["llm_calls"] += 1
    total["input_tokens"] += in_tok
    total["output_tokens"] += out_tok
    return in_tok, out_tok


def _execute(ws: Workspace, agent_name: str, handlers: Dict[str, Callable[..., Dict]], tu) -> Dict:
    handler = handlers.get(tu.name)
    args = dict(tu.input or {})
    if handler is None:
        content, is_error = "알 수 없는 도구: %s" % tu.name, True
    else:
        try:
            content, is_error = json.dumps(handler(ws, **args), ensure_ascii=False, default=str), False
        except Exception as exc:  # 도구 오류는 모델에게 돌려줘 스스로 복구하게 한다
            content, is_error = "도구 실행 오류: %s: %s" % (type(exc).__name__, exc), True
    ws.log(agent_name, "tool:" + tu.name, json.dumps(args, ensure_ascii=False), ok=not is_error)
    block = {"type": "tool_result", "tool_use_id": tu.id, "content": content}
    if is_error:
        block["is_error"] = True
    return block
