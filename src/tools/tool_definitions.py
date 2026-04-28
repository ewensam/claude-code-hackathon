"""
Anthropic API tool schemas for all agent tools.

Cert pattern — Tool Design: tool descriptions must teach the agent when to reach
for each one and, just as importantly, what it does NOT do. Input formats, edge
cases, and example queries are part of the description, not just the schema.

We use tool_use with JSON Schema for structured output rather than asking the
model to return JSON in its text. This is the 'don't prompt-for-JSON' principle.
"""

from src.models import Action, Category

_CATEGORY_VALUES = [c.value for c in Category]
_ACTION_VALUES = [a.value for a in Action]


POLICY_LOOKUP_DEF = {
    "name": "policy_lookup",
    "description": (
        "Returns policy details for a UK home insurance policy by policy number. "
        "Use this first on every claim to confirm the policy is active, retrieve the excess amount, "
        "check cover type (buildings / contents / combined), and identify any named exclusions. "
        "Does NOT return claims history, payment details, premium amounts, or broker information. "
        "Input must match HI-YYYY-XXXXXX format (e.g. HI-2024-000001). "
        "Returns POLICY_LAPSED (non-retryable) if the policy is not active — do not proceed with "
        "any further automated action on a lapsed policy. "
        "Returns POLICY_NOT_FOUND if no matching record exists — verify the number and retry once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "policy_number": {
                "type": "string",
                "description": "Policy number in HI-YYYY-XXXXXX format, e.g. HI-2024-000001",
            }
        },
        "required": ["policy_number"],
    },
}

FRAUD_CHECK_DEF = {
    "name": "fraud_check",
    "description": (
        "Checks the claimant against the internal fraud register and UK/international sanctions lists. "
        "Returns fraud_score (0.0–1.0), fraud_flags (list), and sanctions_match (bool). "
        "A fraud_score >= 0.3 requires escalation to the investigate queue. "
        "A fraud_score >= 0.7 indicates high probability — route to fraud investigation team directly. "
        "Does NOT return the specific data that triggered a flag (kept internal to prevent gaming). "
        "If sanctions_match is True, the function returns isError: True with SANCTIONS_HIT — "
        "escalate to compliance immediately and do not inform the claimant of the match. "
        "Both claimant_name and policy_number are required inputs. "
        "Example: fraud_check with claimant_name='Jane Smith', policy_number='HI-2024-000001'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "claimant_name": {
                "type": "string",
                "description": "Full name of the claimant as provided in the claim",
            },
            "policy_number": {
                "type": "string",
                "description": "Policy number in HI-YYYY-XXXXXX format",
            },
        },
        "required": ["claimant_name", "policy_number"],
    },
}

RESERVE_ESTIMATOR_DEF = {
    "name": "reserve_estimator",
    "description": (
        "Provides an indicative reserve estimate for a home insurance claim based on the damage "
        "description and category. Returns estimated_reserve_gbp, confidence, damage_category_confirmed, "
        "and repair_scope ('minor' / 'significant' / 'total_loss'). "
        "Does NOT produce a binding settlement figure — this is indicative only and must not be "
        "communicated to the claimant as a quote or offer. "
        "If repair_scope is 'total_loss', mandatory human escalation is required regardless of amount. "
        "Returns ESTIMATOR_UNAVAILABLE if the service is down — do not auto-approve without an estimate. "
        "Input: damage_description (max 500 chars) + category matching a valid Category value. "
        "Example: reserve_estimator with damage_description='Burst pipe under kitchen sink, "
        "water damage to cabinet and flooring', category='escape_of_water'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "damage_description": {
                "type": "string",
                "description": "Free-text description of the damage, max 500 characters",
                "maxLength": 500,
            },
            "category": {
                "type": "string",
                "enum": _CATEGORY_VALUES,
                "description": "Claim category — must be one of the defined Category values",
            },
        },
        "required": ["damage_description", "category"],
    },
}

CLAIM_WRITER_DEF = {
    "name": "claim_writer",
    "description": (
        "Performs write actions on a home insurance claim. "
        "Supported action_type values: "
        "'approve_payment' — issues payment up to £500 (payload: {amount_gbp, policy_number}); "
        "'assign_to_adjuster_queue' — routes to a named queue (payload: {queue, priority}), "
        "valid queues: express, standard, specialist, fraud, complaints; "
        "'update_claim_status' — sets a new status (payload: {new_status, reason}); "
        "'issue_denial' — records a formal denial (payload: {reason_code, reason_text}). "
        "Does NOT update policy terms, issue payments above £500, modify fraud flags, "
        "or communicate directly with the claimant (use document_requester for that). "
        "Returns RESERVE_ABOVE_AUTO_THRESHOLD (non-retryable) if payment > £500. "
        "Returns POLICY_LAPSED or FRAUD_FLAG_ACTIVE (non-retryable) for blocked writes. "
        "Example: claim_writer with claim_id='CLM-2024-000001', action_type='approve_payment', "
        "payload={amount_gbp: 320.0, policy_number: 'HI-2024-000001'}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "claim_id": {
                "type": "string",
                "description": "Claim identifier, e.g. CLM-2024-000001",
            },
            "action_type": {
                "type": "string",
                "enum": ["approve_payment", "assign_to_adjuster_queue", "update_claim_status", "issue_denial"],
            },
            "payload": {
                "type": "object",
                "description": "Action-specific parameters — see tool description for each action_type",
            },
        },
        "required": ["claim_id", "action_type", "payload"],
    },
}

DOCUMENT_REQUESTER_DEF = {
    "name": "document_requester",
    "description": (
        "Sends a templated document request to the claimant asking for supporting evidence. "
        "Supported document_type values: "
        "'police_report' (theft / attempted_theft claims); "
        "'damage_photos' (any claim type); "
        "'repair_quote' (escape_of_water, storm_damage, accidental_damage); "
        "'proof_of_ownership' (theft claims with contents items); "
        "'leak_report' (escape_of_water where cause is unclear); "
        "'fire_brigade_report' (fire_damage claims). "
        "Does NOT send free-text messages — only pre-approved templates. "
        "If no template fits the situation, escalate to human for manual communication. "
        "Returns PERMISSION_DENIED if document_type is not in the approved list. "
        "Example: document_requester with policy_number='HI-2024-000001', "
        "document_type='police_report', reason_code='THEFT_CLAIM_INITIATED'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "policy_number": {
                "type": "string",
                "description": "Policy number in HI-YYYY-XXXXXX format",
            },
            "document_type": {
                "type": "string",
                "enum": ["police_report", "damage_photos", "repair_quote", "proof_of_ownership", "leak_report", "fire_brigade_report"],
            },
            "reason_code": {
                "type": "string",
                "description": "Short audit-trail code, e.g. THEFT_CLAIM_INITIATED",
            },
        },
        "required": ["policy_number", "document_type", "reason_code"],
    },
}

# --- Structured output tools ---
# Cert pattern: use tool_use with JSON Schema for structured output.
# Never ask the model to return JSON in its text — force it through a tool call.
# When the agent calls submit_triage_output, the agent loop captures the input
# and stops, returning it as the validated TriageOutput. No text parsing needed.

SUBMIT_TRIAGE_OUTPUT_DEF = {
    "name": "submit_triage_output",
    "description": (
        "Submit your final triage classification for this claim. Call this once you have "
        "run policy_lookup, fraud_check, and reserve_estimator and are confident in your assessment. "
        "All fields are required except adjuster_queue (only needed if recommending fast_track_adjuster), "
        "escalation_reason (only needed if recommending escalate_to_human), "
        "and repair_scope (populate from reserve_estimator output)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": _CATEGORY_VALUES},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "recommended_action": {"type": "string", "enum": _ACTION_VALUES},
            "reserve_estimate_gbp": {"type": "number", "description": "From reserve_estimator output"},
            "excess_gbp": {"type": "number", "description": "From policy_lookup output"},
            "fraud_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "cover_type": {"type": "string", "description": "From policy_lookup: buildings/contents/combined"},
            "repair_scope": {"type": "string", "enum": ["minor", "significant", "total_loss"]},
            "adjuster_queue": {"type": "string", "description": "Required if recommended_action is fast_track_adjuster"},
            "reasoning": {"type": "string", "description": "Full reasoning chain — explain why each tool result led to this decision"},
            "escalation_reason": {"type": "string", "description": "Required if recommended_action is escalate_to_human"},
        },
        "required": ["category", "confidence", "recommended_action", "reasoning"],
    },
}

SUBMIT_ACTION_OUTPUT_DEF = {
    "name": "submit_action_output",
    "description": "Submit confirmation of the action taken on this claim. Call this once the write action is complete.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action_taken": {"type": "string", "enum": _ACTION_VALUES},
            "claim_id": {"type": "string"},
            "summary": {"type": "string", "description": "One-sentence summary of what was done"},
            "payment_amount_gbp": {"type": "number", "description": "If action was approve_payment"},
            "adjuster_queue": {"type": "string", "description": "If action was assign_to_adjuster_queue"},
            "documents_requested": {
                "type": "array",
                "items": {"type": "string"},
                "description": "document_type values requested, if any",
            },
        },
        "required": ["action_taken", "claim_id", "summary"],
    },
}

# Tool lists by specialist
TRIAGE_TOOLS = [POLICY_LOOKUP_DEF, FRAUD_CHECK_DEF, RESERVE_ESTIMATOR_DEF, SUBMIT_TRIAGE_OUTPUT_DEF]
ACTION_TOOLS = [CLAIM_WRITER_DEF, DOCUMENT_REQUESTER_DEF, SUBMIT_ACTION_OUTPUT_DEF]
