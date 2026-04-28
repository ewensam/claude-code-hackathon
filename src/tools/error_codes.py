from dataclasses import dataclass


@dataclass
class ErrorCode:
    code: str
    guidance: str
    retryable: bool


INVALID_FORMAT = ErrorCode(
    code="INVALID_FORMAT",
    guidance="Check the input format against the tool description and resubmit. Policy numbers must match HI-YYYY-XXXXXX.",
    retryable=True,
)

PERMISSION_DENIED = ErrorCode(
    code="PERMISSION_DENIED",
    guidance="This action requires elevated permissions. Escalate to human approval.",
    retryable=False,
)

KB_UNAVAILABLE = ErrorCode(
    code="KB_UNAVAILABLE",
    guidance="External service is temporarily unavailable. Proceed with available context only; do not auto-approve.",
    retryable=True,
)

ROUTE_BLOCKED = ErrorCode(
    code="ROUTE_BLOCKED",
    guidance="This destination queue is not recognised. Escalate to human for manual routing.",
    retryable=False,
)

POLICY_NOT_FOUND = ErrorCode(
    code="POLICY_NOT_FOUND",
    guidance="Verify the policy number format (e.g. HI-2024-000001) and retry. If correct, escalate — the policy may not be in this system.",
    retryable=True,
)

POLICY_LAPSED = ErrorCode(
    code="POLICY_LAPSED",
    guidance="Policy is lapsed or cancelled. No automated action is permitted. Escalate to human — the claimant may need to be informed there is no active cover.",
    retryable=False,
)

FRAUD_FLAG_ACTIVE = ErrorCode(
    code="FRAUD_FLAG_ACTIVE",
    guidance="This claimant has an active fraud flag. Halt all processing and escalate to the fraud investigation queue immediately.",
    retryable=False,
)

SANCTIONS_HIT = ErrorCode(
    code="SANCTIONS_HIT",
    guidance="Claimant matched the sanctions list. Halt all processing immediately and escalate to the compliance team. Do not inform the claimant of the match.",
    retryable=False,
)

RESERVE_ABOVE_AUTO_THRESHOLD = ErrorCode(
    code="RESERVE_ABOVE_AUTO_THRESHOLD",
    guidance="Estimated reserve exceeds the £500 auto-payment threshold. Route to the adjuster queue — do not attempt auto-approval.",
    retryable=False,
)

EXCESS_EXCEEDS_RESERVE = ErrorCode(
    code="EXCESS_EXCEEDS_RESERVE",
    guidance="Policy excess is greater than or equal to the estimated reserve. The claimant's loss falls below their excess — recommend denial with this explanation.",
    retryable=False,
)

ESTIMATOR_UNAVAILABLE = ErrorCode(
    code="ESTIMATOR_UNAVAILABLE",
    guidance="Reserve estimator service is unavailable. Do not auto-approve without an estimate. Route to adjuster queue for manual assessment.",
    retryable=True,
)


def make_error(error_code: ErrorCode, detail: str = "") -> dict:
    return {
        "isError": True,
        "code": error_code.code,
        "guidance": error_code.guidance,
        "retryable": error_code.retryable,
        "detail": detail,
    }
