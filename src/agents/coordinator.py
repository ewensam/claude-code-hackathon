"""
Coordinator — main orchestration loop.

Cert patterns demonstrated here:

1. AGENTIC ARCHITECTURE — coordinator + specialist split with explicit context passing.
   The coordinator never executes tools directly; it dispatches Tasks and interprets results.

2. VALIDATION-RETRY LOOP — structured output from TriageSpecialist is validated against
   the Pydantic schema. On failure, the specific error is fed back and retried (up to
   MAX_RETRIES). Retry count and error type are logged per claim.

3. STOP_REASON HANDLING — max_tokens and max_iterations from the agent loop both
   result in escalation, not silent failure.

4. ESCALATION RULES — category + fraud_score + reserve + regulatory triggers.
   Deterministic checks in code, not probabilistic prompt guidance.
   See ADR-003 for the full table and rationale.

5. PROMPT ENGINEERING — the retry prompt feeds the specific validation error back
   to the model, not a vague "try again". This is the validation-retry pattern:
   structured validator checks output → error fed back → retry up to N times.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import anthropic
from pydantic import ValidationError

from src.agent_loop import AgentLoopResult
from src.agents.action_specialist import run_action_specialist
from src.agents.triage_specialist import run_triage_specialist
from src.models import Action, AgentInput, EscalationRequest, TriageOutput

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

# Escalation thresholds — these live in code, not in the prompt.
# Cert note: explicit thresholds produce consistent, auditable escalation behaviour.
# "When the agent isn't sure" is not a threshold — it produces inconsistent rates.
FRAUD_SCORE_ESCALATION = 0.30
RESERVE_ESCALATION_GBP = 25_000.0
CONFIDENCE_ESCALATION = 0.75

ESCALATE_CATEGORIES = {"liability", "fraud_suspected"}
LEGAL_KEYWORDS = {"solicitor", "fos", "ombudsman", "legal action", "legal proceedings", "my lawyer"}
VULNERABILITY_KEYWORDS = {
    "passed away", "bereavement", "bereaved", "died", "death",
    "disability", "disabled", "mental health", "depression", "anxiety",
    "financial hardship", "struggling to cope", "can't manage",
}

# Actions that require ActionSpecialist dispatch
ACTIONABLE_ACTIONS = {
    Action.AUTO_APPROVE_PAYMENT,
    Action.FAST_TRACK_ADJUSTER,
    Action.REQUEST_MORE_INFO,
    Action.DENY,
}


@dataclass
class CoordinatorResult:
    request_id: str
    triage: Optional[TriageOutput]
    action_result: Optional[dict]
    escalated: bool
    escalation_reason: Optional[str]
    retry_count: int
    error: Optional[str] = None


def run(claim: AgentInput, client: Optional[anthropic.Anthropic] = None) -> CoordinatorResult:
    """
    Main coordinator entry point. Processes a single claim end-to-end.

    Flow:
    1. Dispatch TriageSpecialist → get TriageOutput
    2. Validate TriageOutput (retry loop ≤ MAX_RETRIES)
    3. Apply escalation rules
    4. If escalate: return EscalationResult
    5. If action: dispatch ActionSpecialist
    6. Return CoordinatorResult
    """
    if client is None:
        client = anthropic.Anthropic()

    logger.info("Coordinator processing claim %s", claim.request_id)

    # --- Step 1 & 2: Triage with validation-retry loop ---
    triage, retry_count = _run_triage_with_retry(claim, client)

    if triage is None:
        reason = f"Triage validation exhausted after {MAX_RETRIES} retries"
        logger.warning("%s — escalating claim %s", reason, claim.request_id)
        return CoordinatorResult(
            request_id=claim.request_id,
            triage=None,
            action_result=None,
            escalated=True,
            escalation_reason=reason,
            retry_count=retry_count,
        )

    # --- Step 3: Apply escalation rules ---
    escalation_reason = _check_escalation_rules(claim, triage)
    if escalation_reason:
        logger.info(
            "Escalating claim %s — reason: %s", claim.request_id, escalation_reason
        )
        triage.recommended_action = Action.ESCALATE_TO_HUMAN
        triage.escalation_reason = escalation_reason
        return CoordinatorResult(
            request_id=claim.request_id,
            triage=triage,
            action_result=None,
            escalated=True,
            escalation_reason=escalation_reason,
            retry_count=retry_count,
        )

    # --- Step 4: Dispatch ActionSpecialist if action is needed ---
    if triage.recommended_action not in ACTIONABLE_ACTIONS:
        logger.info(
            "Claim %s: action '%s' requires no write — returning triage only",
            claim.request_id,
            triage.recommended_action.value,
        )
        return CoordinatorResult(
            request_id=claim.request_id,
            triage=triage,
            action_result=None,
            escalated=False,
            escalation_reason=None,
            retry_count=retry_count,
        )

    logger.info(
        "Dispatching ActionSpecialist for claim %s — action: %s",
        claim.request_id,
        triage.recommended_action.value,
    )
    action_loop_result = run_action_specialist(claim, triage, client)
    action_result = _extract_action_result(action_loop_result)

    return CoordinatorResult(
        request_id=claim.request_id,
        triage=triage,
        action_result=action_result,
        escalated=False,
        escalation_reason=None,
        retry_count=retry_count,
    )


# --- Private helpers ---

def _run_triage_with_retry(
    claim: AgentInput, client: anthropic.Anthropic
) -> tuple[Optional[TriageOutput], int]:
    """
    Cert pattern — Validation-retry loop:
    1. Run TriageSpecialist
    2. Validate output against Pydantic schema
    3. On ValidationError: feed the specific error back, retry
    4. After MAX_RETRIES: return None (coordinator will escalate)

    Retry count and error type are logged per claim for the eval harness.
    """
    attempt = 0
    last_error: Optional[str] = None

    while attempt < MAX_RETRIES:
        if attempt > 0:
            logger.info(
                "Retry %d/%d for claim %s — previous error: %s",
                attempt, MAX_RETRIES, claim.request_id, last_error,
            )

        # Cert note: feeding the specific validation error back (not a vague "try again")
        # is what makes the retry productive. The specialist can correct the exact field
        # that failed rather than re-guessing the whole output.
        loop_result: AgentLoopResult = run_triage_specialist(
            claim, client, previous_error=last_error if attempt > 0 else None
        )

        # Handle non-structured-output stop reasons
        if loop_result.stop_reason in ("max_tokens", "max_iterations"):
            last_error = f"agent_loop stopped with stop_reason={loop_result.stop_reason}"
            logger.warning(
                "Triage loop stop_reason=%s for claim %s (attempt %d)",
                loop_result.stop_reason, claim.request_id, attempt,
            )
            attempt += 1
            continue

        if loop_result.stop_reason != "structured_output":
            last_error = f"unexpected stop_reason={loop_result.stop_reason}"
            attempt += 1
            continue

        # Validate against Pydantic schema
        try:
            triage = TriageOutput(**loop_result.structured_output)
            logger.info(
                "Claim %s triage validated on attempt %d — category=%s action=%s confidence=%.2f",
                claim.request_id, attempt, triage.category.value,
                triage.recommended_action.value, triage.confidence,
            )
            triage.retry_count = attempt
            return triage, attempt
        except (ValidationError, TypeError) as exc:
            last_error = str(exc)
            logger.warning(
                "Validation failed attempt %d for claim %s: %s",
                attempt, claim.request_id, last_error,
            )
            attempt += 1

    return None, attempt


def _check_escalation_rules(claim: AgentInput, triage: TriageOutput) -> Optional[str]:
    """
    Apply the escalation rules from ADR-003. Returns a reason string if escalation
    is triggered, None otherwise.

    Cert note: these are discrete, auditable conditions — category + score + impact —
    not "when the agent isn't sure". Each check maps to a row in ADR-003's table.
    """
    body_lower = claim.body.lower()

    if triage.confidence < CONFIDENCE_ESCALATION:
        return f"Low confidence ({triage.confidence:.2f} < {CONFIDENCE_ESCALATION})"

    if triage.fraud_score is not None and triage.fraud_score >= FRAUD_SCORE_ESCALATION:
        return f"Fraud score {triage.fraud_score:.2f} >= threshold {FRAUD_SCORE_ESCALATION}"

    if triage.category.value in ESCALATE_CATEGORIES:
        return f"Category '{triage.category.value}' always requires human review"

    if triage.reserve_estimate_gbp is not None and triage.reserve_estimate_gbp > RESERVE_ESCALATION_GBP:
        return f"Reserve estimate £{triage.reserve_estimate_gbp:.0f} exceeds £{RESERVE_ESCALATION_GBP:.0f} threshold"

    if triage.repair_scope and triage.repair_scope.value == "total_loss":
        return "Repair scope is total_loss — physical survey required"

    if any(kw in body_lower for kw in LEGAL_KEYWORDS):
        matched = [kw for kw in LEGAL_KEYWORDS if kw in body_lower]
        return f"Legal language detected in claim body: {matched}"

    if any(kw in body_lower for kw in VULNERABILITY_KEYWORDS):
        matched = [kw for kw in VULNERABILITY_KEYWORDS if kw in body_lower]
        return f"Vulnerable customer indicator detected: {matched} — FCA Consumer Duty"

    if triage.retry_count >= 2:
        return f"Validation retries ({triage.retry_count}) >= 2 — ambiguous input"

    return None


def _extract_action_result(loop_result: AgentLoopResult) -> dict:
    if loop_result.stop_reason == "structured_output" and loop_result.structured_output:
        return loop_result.structured_output
    return {
        "error": f"ActionSpecialist stopped with stop_reason={loop_result.stop_reason}",
        "is_truncated": loop_result.is_truncated,
    }
