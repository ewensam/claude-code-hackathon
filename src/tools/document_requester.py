import re
from .error_codes import make_error, INVALID_FORMAT, PERMISSION_DENIED

POLICY_ID_PATTERN = re.compile(r"^HI-\d{4}-\d{6}$")

_APPROVED_TEMPLATES: dict[str, str] = {
    "police_report": (
        "To progress your theft claim, please provide the police crime reference number "
        "and a copy of the report submitted to your local force."
    ),
    "damage_photos": (
        "Please submit clear photographs of all damaged areas from multiple angles. "
        "Include any visible cause of damage where possible."
    ),
    "repair_quote": (
        "Please provide at least one written repair quote from a qualified and registered tradesperson. "
        "The quote should itemise labour and materials separately."
    ),
    "proof_of_ownership": (
        "To support your contents claim, please provide proof of ownership for the items claimed. "
        "Acceptable evidence includes original receipts, bank or credit card statements, valuations, "
        "or photographs showing the items in your home."
    ),
    "leak_report": (
        "Please provide a written report from a qualified plumber or drainage specialist confirming "
        "the cause and extent of the water damage. The report should confirm whether the leak was sudden "
        "or gradual in nature."
    ),
    "fire_brigade_report": (
        "Please provide the fire brigade incident report number and, if available, a copy of the report. "
        "This helps us confirm the cause and extent of the fire damage."
    ),
}


def document_requester(policy_number: str, document_type: str, reason_code: str) -> dict:
    """
    Sends a templated document request to the claimant, asking them to provide
    supporting documentation for their home insurance claim.

    Document types supported:
    - "police_report": required for theft and attempted theft claims
    - "damage_photos": applicable to any claim type
    - "repair_quote": required for escape of water, storm, and accidental damage claims
    - "proof_of_ownership": required for theft claims involving contents items
    - "leak_report": required for escape of water claims where cause is unclear
    - "fire_brigade_report": required for fire/smoke damage claims

    Does NOT send free-text messages to claimants. Only pre-approved templates
    from the approved library are permitted. This prevents the agent from making
    commitments, settlement representations, or policy interpretations in writing.

    Input:
    - policy_number: must match HI-YYYY-XXXXXX format
    - document_type: must be one of the approved template keys listed above
    - reason_code: short string logged for audit trail (e.g. "THEFT_CLAIM_INITIATED")

    Example: document_requester("HI-2024-000001", "police_report", "THEFT_CLAIM_INITIATED")

    Edge cases:
    - Returns PERMISSION_DENIED if document_type is not in the approved template list.
      Do not attempt to send custom messages — escalate if no template fits.
    - Returns INVALID_FORMAT if policy_number does not match expected format.
    """
    if not POLICY_ID_PATTERN.match(policy_number):
        return make_error(INVALID_FORMAT, f"'{policy_number}' does not match HI-YYYY-XXXXXX format.")

    if document_type not in _APPROVED_TEMPLATES:
        return make_error(
            PERMISSION_DENIED,
            f"'{document_type}' is not an approved template. "
            f"Supported types: {sorted(_APPROVED_TEMPLATES.keys())}. "
            "If none fit, escalate to human for manual communication.",
        )

    return {
        "success": True,
        "policy_number": policy_number,
        "document_type": document_type,
        "template_text": _APPROVED_TEMPLATES[document_type],
        "reason_code": reason_code,
    }
