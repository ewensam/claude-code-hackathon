"""
TriageSpecialist — read-only classification agent.

Cert pattern — Agentic Architecture:
- This is a Task subagent. It receives all required context explicitly in the
  task prompt; it has NO access to the coordinator's session or history.
- It has exactly 3 operational tools + 1 structured output tool. Keeping tool
  count low (4-5 max per specialist) maintains reliable tool selection.
- It is read-only. All write capability sits in ActionSpecialist, which is the
  only agent scoped to the PreToolUse hook.

The structured output tool (submit_triage_output) is how we get the TriageOutput
back to the coordinator without parsing text. The agent loop stops when this tool
is called and returns its input as the result.
"""

import logging
from typing import Optional

import anthropic

from src.agent_loop import AgentLoopResult, run_agent_loop
from src.client import default_model
from src.models import AgentInput
from src.tools import TRIAGE_TOOL_EXECUTOR
from src.tools.tool_definitions import TRIAGE_TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the TriageSpecialist for a UK home insurance claims triage system.

Your job is to classify an inbound claim and recommend an action. You do not take any write actions.

## Your tools (use all three before submitting)
1. policy_lookup — verify policy status, excess, cover type, and exclusions. Always run this first.
2. fraud_check — check the claimant against the fraud register and sanctions list.
3. reserve_estimator — get an indicative reserve estimate from the damage description.

## Escalation rules — recommend escalate_to_human if ANY of these apply
- Confidence in your classification is below 0.75
- fraud_score >= 0.30 (route to investigate queue)
- sanctions_match = True (immediate compliance escalation)
- Category is 'liability'
- Estimated reserve > £25,000
- repair_scope is 'total_loss'
- Claim body contains legal language: "solicitor", "FOS", "ombudsman", "legal action"
- Claim body contains vulnerable customer indicators: bereavement, disability, mental health, financial hardship
- Policy status is lapsed or cancelled

## When to deny
- Policy excess >= estimated reserve (the claimant's loss falls below their excess)
- Cause is a named exclusion on the policy (e.g. flood on a policy excluding flood, gradual deterioration)

## When to request more info
- Theft or attempted theft without a police report
- Escape of water where the cause is unclear
- Cover type is ambiguous (e.g. possible tenant claiming on a buildings-only policy)

## When to auto_approve_payment
- Policy active, fraud_score < 0.30, no sanctions
- Reserve estimate <= £500, and above the policy excess
- Clear in-scope cause, confidence >= 0.85

## When to fast_track_adjuster
- Policy active, fraud_score < 0.30
- Reserve £500–£25,000, repair_scope is not 'total_loss'
- No escalation triggers

## Submitting your output
Use the submit_triage_output tool once you have run all three tools and reached a conclusion.
Include your full reasoning in the 'reasoning' field — explain what each tool returned and
how it led to your recommendation. The reasoning chain is logged for audit and human review.
"""


def run_triage_specialist(
    claim: AgentInput,
    client: anthropic.Anthropic,
    previous_error: Optional[str] = None,
) -> AgentLoopResult:
    """
    Dispatch the TriageSpecialist as a fresh Task with explicit context.

    Cert note: the task_prompt below passes everything the specialist needs.
    It cannot rely on coordinator session state — Task subagents start fresh.
    This explicit passing is what makes the reasoning chain auditable.

    previous_error: if this is a retry attempt, the specific validation error from
    the previous attempt is appended to the prompt. Feeding the specific error back
    (not a vague "try again") is the validation-retry pattern — the model can correct
    the exact field that failed rather than re-guessing the whole output.
    """
    task_prompt = f"""Classify the following home insurance claim.

CLAIM ID: {claim.request_id}
POLICY NUMBER: {claim.policy_number}
CLAIMANT NAME: {claim.claimant_name}
CHANNEL: {claim.channel}
TIMESTAMP: {claim.timestamp}

CLAIM BODY:
{claim.body}

Run policy_lookup, fraud_check, and reserve_estimator, then submit your triage output."""

    if previous_error:
        task_prompt += (
            f"\n\n[VALIDATION RETRY] Your previous submit_triage_output call failed schema "
            f"validation with this error:\n{previous_error}\n"
            "Please re-run your tools if needed and resubmit with a corrected output."
        )

    def tool_executor(name: str, inp: dict) -> dict:
        executor = TRIAGE_TOOL_EXECUTOR.get(name)
        if executor:
            return executor(inp)
        return {
            "isError": True,
            "code": "UNKNOWN_TOOL",
            "guidance": f"Tool '{name}' is not available to TriageSpecialist.",
            "retryable": False,
        }

    return run_agent_loop(
        client=client,
        model=default_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=TRIAGE_TOOLS,
        initial_messages=[{"role": "user", "content": task_prompt}],
        tool_executor=tool_executor,
        structured_output_tool="submit_triage_output",

        pre_tool_use=None,  # Read-only — no PreToolUse hook needed
        post_tool_use=None,  # Policy lookup PII redaction happens in ActionSpecialist context
    )
