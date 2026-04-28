from .error_codes import (
    make_error,
    POLICY_LAPSED,
    RESERVE_ABOVE_AUTO_THRESHOLD,
    FRAUD_FLAG_ACTIVE,
    ROUTE_BLOCKED,
    PERMISSION_DENIED,
)

AUTO_PAYMENT_THRESHOLD_GBP = 500.0

_ADJUSTER_QUEUES = {
    "express": "EXPRESS_ADJUSTER_QUEUE",
    "standard": "STANDARD_ADJUSTER_QUEUE",
    "specialist": "SPECIALIST_ADJUSTER_QUEUE",
    "fraud": "FRAUD_INVESTIGATION_QUEUE",
    "complaints": "COMPLAINTS_TEAM_QUEUE",
}

_VALID_ACTIONS = {"approve_payment", "assign_to_adjuster_queue", "update_claim_status", "issue_denial"}


def claim_writer(claim_id: str, action_type: str, payload: dict) -> dict:
    """
    Performs write actions on a home insurance claim.

    Actions supported:
    - "approve_payment": issues payment up to £500 to the claimant.
      Payload: {"amount_gbp": float, "policy_number": str}
    - "assign_to_adjuster_queue": routes the claim to a named adjuster queue.
      Payload: {"queue": str ("express"/"standard"/"specialist"/"fraud"/"complaints"), "priority": str}
    - "update_claim_status": sets a new status on the claim record.
      Payload: {"new_status": str, "reason": str}
    - "issue_denial": records a formal denial with reason code for audit trail.
      Payload: {"reason_code": str, "reason_text": str}

    Does NOT: update policy terms, issue payments above £500, modify fraud flags,
    communicate directly with the claimant (use document_requester for outbound contact),
    or cancel policies.

    Example: claim_writer(
        "CLM-2024-00123",
        "approve_payment",
        {"amount_gbp": 320.0, "policy_number": "HI-2024-000001"}
    )

    Edge cases:
    - "approve_payment" with amount_gbp > £500 returns RESERVE_ABOVE_AUTO_THRESHOLD (non-retryable).
      Route to adjuster queue instead.
    - Any action on a lapsed policy returns POLICY_LAPSED (non-retryable).
    - Any action when fraud flag is active returns FRAUD_FLAG_ACTIVE (non-retryable).
    - "assign_to_adjuster_queue" with an unrecognised queue name returns ROUTE_BLOCKED.
    """
    if action_type not in _VALID_ACTIONS:
        return make_error(
            PERMISSION_DENIED,
            f"Unknown action_type '{action_type}'. Supported: {sorted(_VALID_ACTIONS)}.",
        )

    if action_type == "approve_payment":
        amount = float(payload.get("amount_gbp", 0))
        if amount > AUTO_PAYMENT_THRESHOLD_GBP:
            return make_error(
                RESERVE_ABOVE_AUTO_THRESHOLD,
                f"Requested £{amount:.2f} exceeds £{AUTO_PAYMENT_THRESHOLD_GBP:.2f} auto-payment limit.",
            )
        return {"success": True, "claim_id": claim_id, "action": "approve_payment", "amount_gbp": amount}

    if action_type == "assign_to_adjuster_queue":
        queue_key = payload.get("queue", "")
        if queue_key not in _ADJUSTER_QUEUES:
            return make_error(
                ROUTE_BLOCKED,
                f"Queue '{queue_key}' is not recognised. Valid queues: {list(_ADJUSTER_QUEUES.keys())}.",
            )
        return {
            "success": True,
            "claim_id": claim_id,
            "action": "assign_to_adjuster_queue",
            "queue": _ADJUSTER_QUEUES[queue_key],
            "priority": payload.get("priority", "normal"),
        }

    if action_type == "update_claim_status":
        return {
            "success": True,
            "claim_id": claim_id,
            "action": "update_claim_status",
            "new_status": payload.get("new_status"),
            "reason": payload.get("reason"),
        }

    if action_type == "issue_denial":
        return {
            "success": True,
            "claim_id": claim_id,
            "action": "issue_denial",
            "reason_code": payload.get("reason_code"),
            "reason_text": payload.get("reason_text"),
        }
