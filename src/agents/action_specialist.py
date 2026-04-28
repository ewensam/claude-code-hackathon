"""
ActionSpecialist — write-capable action agent.

Cert pattern — Agentic Architecture + Context Management:
- This specialist has WRITE-capable tools and is the ONLY agent scoped to
  the PreToolUse hard-block hook. Isolating writes to one specialist means
  the hook only needs to inspect this agent's tool calls.
- It receives the full TriageOutput from the coordinator as explicit context.
  Task subagents do not inherit coordinator state — everything needed is passed
  in the task prompt.
- Tool count: 2 operational tools + 1 structured output tool = 3 total.
  Well within the 4-5 reliability threshold.

The PreToolUse hook enforces hard blocks (payment > £500, etc.) before the
LLM can act. The coordinator's escalation rules handle soft stops (confidence,
fraud score, reserve threshold) before this specialist is ever dispatched.
So by the time ActionSpecialist runs, the "should we act at all?" question
is already answered — it just decides HOW to act.
"""

import logging

import anthropic

from src.agent_loop import AgentLoopResult, run_agent_loop
from src.client import default_model
from src.hooks.post_tool_use import post_tool_use
from src.hooks.pre_tool_use import pre_tool_use
from src.models import AgentInput, TriageOutput
from src.tools import ACTION_TOOL_EXECUTOR
from src.tools.tool_definitions import ACTION_TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the ActionSpecialist for a UK home insurance claims triage system.

The coordinator has already classified the claim and determined the appropriate action.
Your job is to execute that action using your tools.

## Your tools
1. claim_writer — approve payment (≤£500 only), assign to adjuster queue, update status, or issue denial.
2. document_requester — send a templated document request to the claimant.

## Important constraints
- You may only approve payments up to £500. The hook will block anything higher.
- Only use approved document templates. The hook blocks unapproved ones.
- Do not communicate with the claimant in free text — document_requester only.
- If a tool returns isError: True with retryable: False, do not retry. Submit your output
  noting the block and the reason — the coordinator will escalate.

## Submitting your output
Use submit_action_output once the action is complete (or once a non-retryable block occurs).
Include a clear summary of what was done (or what was blocked and why).
"""


def run_action_specialist(
    claim: AgentInput,
    triage: TriageOutput,
    client: anthropic.Anthropic,
) -> AgentLoopResult:
    """
    Dispatch ActionSpecialist with claim context AND the full TriageOutput injected.

    Cert note: the triage output is passed explicitly in the task prompt below —
    not inherited from coordinator session state. This is what makes each
    specialist's reasoning independently auditable from the log alone.
    """
    action_map = {
        "auto_approve_payment": (
            f"Auto-approve a payment of approximately £{triage.reserve_estimate_gbp:.0f} "
            f"(policy excess is £{triage.excess_gbp:.0f}). "
            "Use claim_writer with action_type='approve_payment'."
        ),
        "fast_track_adjuster": (
            f"Assign this claim to the '{triage.adjuster_queue or 'express'}' adjuster queue. "
            "Use claim_writer with action_type='assign_to_adjuster_queue'. "
            "Also consider whether a document request is appropriate (photos, repair quote, etc.)."
        ),
        "request_more_info": (
            "Send a document request to the claimant for the missing information. "
            "Use document_requester with the appropriate template."
        ),
        "deny": (
            f"Issue a formal denial. Reason: {triage.escalation_reason or 'see triage reasoning'}. "
            "Use claim_writer with action_type='issue_denial'."
        ),
    }

    action_instruction = action_map.get(
        triage.recommended_action.value,
        f"Recommended action: {triage.recommended_action.value}",
    )

    task_prompt = f"""Execute the triage decision for the following claim.

CLAIM ID: {claim.request_id}
POLICY NUMBER: {claim.policy_number}
CLAIMANT NAME: {claim.claimant_name}
CHANNEL: {claim.channel}

CLAIM BODY:
{claim.body}

TRIAGE RESULT (from TriageSpecialist):
- Category: {triage.category.value}
- Recommended action: {triage.recommended_action.value}
- Reserve estimate: £{triage.reserve_estimate_gbp}
- Excess: £{triage.excess_gbp}
- Fraud score: {triage.fraud_score}
- Cover type: {triage.cover_type}
- Repair scope: {triage.repair_scope.value if triage.repair_scope else "unknown"}
- Triage reasoning: {triage.reasoning}

YOUR INSTRUCTION: {action_instruction}

Execute the action, then call submit_action_output with a summary of what was done."""

    def tool_executor(name: str, inp: dict) -> dict:
        executor = ACTION_TOOL_EXECUTOR.get(name)
        if executor:
            return executor(inp)
        return {
            "isError": True,
            "code": "UNKNOWN_TOOL",
            "guidance": f"Tool '{name}' is not available to ActionSpecialist.",
            "retryable": False,
        }

    return run_agent_loop(
        client=client,
        model=default_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=ACTION_TOOLS,
        initial_messages=[{"role": "user", "content": task_prompt}],
        tool_executor=tool_executor,
        structured_output_tool="submit_action_output",
        pre_tool_use=pre_tool_use,   # Hard-block hook active on all write calls
        post_tool_use=post_tool_use,
    )
