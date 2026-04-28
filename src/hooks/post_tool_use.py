"""
PostToolUse hook — PII redaction before tool results enter the context window or logs.

Cert pattern — Context Management: PostToolUse hooks redact sensitive data from
tool results before they re-enter the LLM context or persist to storage.
This is deterministic (not prompt-level) because we don't trust the model to
consistently omit PII from its own context window.

Fields redacted: policy_holder_name, property_postcode from policy_lookup results.
The claim body itself is never stored verbatim in tool results (it lives in the
initial Task prompt only, which is not persisted to the log store).
"""

import logging
import re

logger = logging.getLogger(__name__)

_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.IGNORECASE)


def post_tool_use(tool_name: str, tool_input: dict, result: dict) -> dict:
    """
    Called after every tool execution. Returns the (possibly redacted) result.
    Must not raise — if redaction fails, log and return original result.
    """
    try:
        if tool_name == "policy_lookup" and not result.get("isError"):
            return _redact_policy_result(result)
    except Exception as exc:
        logger.error("PostToolUse redaction failed for %s: %s", tool_name, exc)
    return result


def _redact_policy_result(result: dict) -> dict:
    redacted = dict(result)
    # Replace real name with pseudonym for context window and logs
    if "policy_holder_name" in redacted:
        redacted["policy_holder_name"] = "[REDACTED]"
    # Replace postcode
    if "property_postcode" in redacted:
        redacted["property_postcode"] = "[REDACTED]"
    return redacted
