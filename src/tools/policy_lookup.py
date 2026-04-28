import re
from pydantic import BaseModel
from .error_codes import make_error, POLICY_NOT_FOUND, POLICY_LAPSED, INVALID_FORMAT

POLICY_ID_PATTERN = re.compile(r"^HI-\d{4}-\d{6}$")


class PolicyDetails(BaseModel):
    policy_number: str
    status: str
    cover_type: str
    excess_gbp: float
    exclusions: list[str]
    policy_holder_name: str
    property_postcode: str


_POLICY_DB: dict[str, PolicyDetails] = {
    "HI-2024-000001": PolicyDetails(
        policy_number="HI-2024-000001",
        status="active",
        cover_type="combined",
        excess_gbp=250.0,
        exclusions=["gradual_deterioration", "subsidence"],
        policy_holder_name="Jane Smith",
        property_postcode="SW1A 1AA",
    ),
    "HI-2024-000002": PolicyDetails(
        policy_number="HI-2024-000002",
        status="active",
        cover_type="buildings",
        excess_gbp=500.0,
        exclusions=["gradual_deterioration", "subsidence", "flood"],
        policy_holder_name="David Jones",
        property_postcode="M1 1AE",
    ),
    "HI-2023-009999": PolicyDetails(
        policy_number="HI-2023-009999",
        status="lapsed",
        cover_type="combined",
        excess_gbp=200.0,
        exclusions=[],
        policy_holder_name="Robert Brown",
        property_postcode="E1 6RF",
    ),
}


def policy_lookup(policy_number: str) -> dict:
    """
    Returns policy details for a UK home insurance policy by policy number.

    Returns: policy status (active/lapsed/cancelled), cover type (buildings/contents/combined),
    excess amount in GBP, named exclusions list, policy holder name, and property postcode.

    Does NOT return: claims history, payment details, premium amounts, or broker information.

    Input format: policy number string matching HI-YYYY-XXXXXX (e.g. HI-2024-000001).

    Example: policy_lookup("HI-2024-000001")

    Edge cases:
    - Returns POLICY_NOT_FOUND if no matching policy exists. Retryable — verify the number.
    - Returns POLICY_LAPSED (non-retryable) if policy status is lapsed or cancelled.
      Do not proceed with any write actions on a lapsed policy.
    - Returns INVALID_FORMAT if the policy number does not match HI-YYYY-XXXXXX.
    """
    if not POLICY_ID_PATTERN.match(policy_number):
        return make_error(INVALID_FORMAT, f"'{policy_number}' does not match HI-YYYY-XXXXXX format.")

    policy = _POLICY_DB.get(policy_number)
    if not policy:
        return make_error(POLICY_NOT_FOUND, f"No policy found for '{policy_number}'.")

    if policy.status in ("lapsed", "cancelled"):
        return make_error(POLICY_LAPSED, f"Policy {policy_number} has status '{policy.status}'.")

    return policy.model_dump()
