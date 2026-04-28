from .error_codes import make_error, SANCTIONS_HIT, KB_UNAVAILABLE

_FRAUD_REGISTER: dict[str, dict] = {
    # policy_number: {score, flags}
    # Populated from internal fraud management system in production
}

_SANCTIONS_LIST: set[str] = set()


def fraud_check(claimant_name: str, policy_number: str) -> dict:
    """
    Checks the claimant against the internal fraud register and UK/international sanctions lists.

    Returns: fraud_score (0.0–1.0), fraud_flags (list of flag type strings),
    sanctions_match (bool).

    Does NOT return the specific data or source that triggered a fraud flag.
    This information is kept internal to prevent claimants from gaming the system.

    A fraud_score >= 0.3 must trigger escalation to the investigate queue.
    A fraud_score >= 0.7 indicates high probability — route to fraud investigation team directly.

    Input: both claimant_name and policy_number are required.
    Example: fraud_check("Jane Smith", "HI-2024-000001")

    Edge cases:
    - If sanctions_match is True, this function returns isError: True with code SANCTIONS_HIT.
      This forces the agent onto the hard-stop escalation path. Do not inform the claimant
      of the sanctions match — escalate to compliance immediately and silently.
    - Returns KB_UNAVAILABLE if the fraud register cannot be reached. In this case,
      do not auto-approve the claim — treat as unknown fraud risk.
    """
    name_upper = claimant_name.upper().strip()
    if name_upper in _SANCTIONS_LIST or policy_number in _SANCTIONS_LIST:
        return make_error(SANCTIONS_HIT, f"Claimant '{claimant_name}' matched sanctions list.")

    fraud_data = _FRAUD_REGISTER.get(policy_number, {"score": 0.0, "flags": []})

    return {
        "fraud_score": fraud_data["score"],
        "fraud_flags": fraud_data["flags"],
        "sanctions_match": False,
    }
