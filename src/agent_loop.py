"""
Generic agent loop engine.

Cert pattern — Agentic Architecture: the agent loop handles all stop_reason values
explicitly. stop_reason routing is deterministic code, not prompt engineering.

Key design choices:
- structured_output_tool: when the model calls this named tool, the loop stops and
  returns its input as structured data. This implements 'tool_use with JSON Schema
  for structured output' — we never ask the model to return JSON in text.
- tool_executor is a callable passed in, keeping the loop generic across specialists.
- pre_tool_use / post_tool_use hooks are injected per-specialist; the ActionSpecialist
  gets a hard-block PreToolUse, the TriageSpecialist gets None (read-only, no risk).
- System prompt uses cache_control: ephemeral so the prompt is cached across calls to
  the same specialist — saves tokens when processing multiple claims in a batch.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class AgentLoopResult:
    stop_reason: str  # "structured_output" | "end_turn" | "max_tokens" | "max_iterations"
    messages: list[dict] = field(default_factory=list)
    structured_output: Optional[dict] = None
    text_content: Optional[str] = None
    is_truncated: bool = False
    iterations: int = 0


def run_agent_loop(
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str,
    tools: list[dict],
    initial_messages: list[dict],
    tool_executor: Callable[[str, dict], dict],
    structured_output_tool: Optional[str] = None,
    pre_tool_use: Optional[Callable[[str, dict], dict]] = None,
    post_tool_use: Optional[Callable[[str, dict, dict], dict]] = None,
    max_iterations: int = 20,
) -> AgentLoopResult:
    """
    Run a single agent until it either calls structured_output_tool, reaches end_turn,
    hits max_tokens, or exhausts max_iterations.

    The caller (coordinator or specialist) owns the interpretation of the result.
    This function only drives the loop and dispatches tool calls.

    Cert note: the distinction between stop_reason handling here (deterministic,
    in code) vs escalation rules (probabilistic, in the LLM prompt) is tested on
    the architect exam. Never put stop_reason routing inside a prompt.
    """
    messages = list(initial_messages)
    iterations = 0

    while iterations < max_iterations:
        iterations += 1

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=tools,
            messages=messages,
        )

        logger.debug("stop_reason=%s iterations=%d", response.stop_reason, iterations)

        # --- Handle end_turn ---
        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            return AgentLoopResult(
                stop_reason="end_turn",
                messages=messages,
                text_content=text,
                iterations=iterations,
            )

        # --- Handle max_tokens ---
        # Cert note: max_tokens is a signal, not an error. We emit a partial result
        # with is_truncated=True so the coordinator can escalate rather than silently
        # returning incomplete output. Never ignore this stop_reason.
        elif response.stop_reason == "max_tokens":
            logger.warning("Agent loop hit max_tokens after %d iterations", iterations)
            return AgentLoopResult(
                stop_reason="max_tokens",
                messages=messages,
                is_truncated=True,
                iterations=iterations,
            )

        # --- Handle tool_use ---
        elif response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name: str = block.name
                tool_input: dict = block.input

                # Structured output tool — stop the loop, return captured input.
                # Cert note: this is 'tool_use for structured output'. The JSON Schema
                # on the tool definition enforces the output shape; we don't parse text.
                if structured_output_tool and tool_name == structured_output_tool:
                    return AgentLoopResult(
                        stop_reason="structured_output",
                        messages=messages,
                        structured_output=tool_input,
                        iterations=iterations,
                    )

                # PreToolUse hook — deterministic hard block.
                # Cert note: the hook runs before the LLM can act and cannot be
                # overridden by prompt. This is a hard stop, not a slow stop.
                # Escalation rules (probabilistic) live in the coordinator system prompt.
                if pre_tool_use:
                    hook_result = pre_tool_use(tool_name, tool_input)
                    if hook_result.get("block"):
                        logger.warning(
                            "PreToolUse blocked %s: %s", tool_name, hook_result["reason"]
                        )
                        tool_results.append(
                            _tool_result(
                                block.id,
                                {
                                    "isError": True,
                                    "code": "HOOK_BLOCKED",
                                    "guidance": hook_result["reason"],
                                    "retryable": False,
                                },
                            )
                        )
                        continue

                # Execute the tool
                try:
                    result = tool_executor(tool_name, tool_input)
                except Exception as exc:
                    logger.error("Tool %s raised exception: %s", tool_name, exc)
                    result = {
                        "isError": True,
                        "code": "TOOL_EXCEPTION",
                        "guidance": "An unexpected error occurred. Escalate to human.",
                        "retryable": False,
                        "detail": str(exc),
                    }

                # PostToolUse hook — redacts PII before it persists to logs/context.
                if post_tool_use:
                    result = post_tool_use(tool_name, tool_input, result)

                tool_results.append(_tool_result(block.id, result))

            messages.append({"role": "user", "content": tool_results})

        # --- Handle stop_sequence or unknown ---
        else:
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

    logger.warning("Agent loop reached max_iterations=%d", max_iterations)
    return AgentLoopResult(
        stop_reason="max_iterations",
        messages=messages,
        iterations=iterations,
    )


def _tool_result(tool_use_id: str, content: dict) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(content),
    }
