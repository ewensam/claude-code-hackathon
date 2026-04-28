"""
PreToolUse hook — deterministic hard blocks on write actions.

Cert pattern — Context Management: hooks enforce deterministic guardrails;
prompts enforce probabilistic preferences. This distinction is key:
- This hook runs BEFORE the LLM acts and cannot be overridden by any prompt.
- Escalation rules in the coordinator system prompt are probabilistic guidance.
- An ADR explains why each guardrail lives here vs in the prompt (ADR-003).

The hook returns {"block": True, "reason": str} to stop execution,
or {"block": False} to allow it through.

No LLM calls inside a hook — hooks must be fast and deterministic.
"""

import logging

logger = logging.getLogger(__name__)

AUTO_PAYMENT_CEILING_GBP = 500.0


def pre_tool_use(tool_name: str, tool_input: dict) -> dict:
    """
    Called before every tool execution in the ActionSpecialist.
    Returns {"block": True, "reason": str} to hard-stop, {"block": False} to allow.
    """
    if tool_name == "claim_writer":
        return _check_claim_writer(tool_input)

    if tool_name == "document_requester":
        return _check_document_requester(tool_input)

    return {"block": False}


def _check_claim_writer(tool_input: dict) -> dict:
    action_type = tool_input.get("action_type", "")
    payload = tool_input.get("payload", {})

    # Block payment above ceiling
    if action_type == "approve_payment":
        amount = float(payload.get("amount_gbp", 0))
        if amount > AUTO_PAYMENT_CEILING_GBP:
            reason = (
                f"HARD BLOCK: approve_payment of £{amount:.2f} exceeds the "
                f"£{AUTO_PAYMENT_CEILING_GBP:.2f} auto-payment ceiling. "
                "Route to adjuster queue instead."
            )
            logger.warning("PreToolUse blocked approve_payment £%.2f", amount)
            return {"block": True, "reason": reason}

    return {"block": False}


def _check_document_requester(tool_input: dict) -> dict:
    # The document_requester tool itself validates template names, but we add
    # a hook-level check as a defence-in-depth measure.
    approved_templates = {
        "police_report", "damage_photos", "repair_quote",
        "proof_of_ownership", "leak_report", "fire_brigade_report",
    }
    doc_type = tool_input.get("document_type", "")
    if doc_type and doc_type not in approved_templates:
        reason = (
            f"HARD BLOCK: document_type '{doc_type}' is not in the approved template list. "
            "Escalate to human for manual communication."
        )
        logger.warning("PreToolUse blocked document_requester with type=%s", doc_type)
        return {"block": True, "reason": reason}

    return {"block": False}
