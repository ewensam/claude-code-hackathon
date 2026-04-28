from .error_codes import make_error, ESTIMATOR_UNAVAILABLE, INVALID_FORMAT

_CATEGORY_BASE_RESERVES: dict[str, float] = {
    "escape_of_water": 800.0,
    "flood": 5000.0,
    "storm_damage": 1200.0,
    "theft": 1500.0,
    "attempted_theft": 200.0,
    "fire_damage": 15000.0,
    "accidental_damage": 500.0,
    "liability": 10000.0,
    "other": 1000.0,
}

_TOTAL_LOSS_KEYWORDS = [
    "total loss", "uninhabitable", "burned down", "demolished",
    "completely destroyed", "gutted", "structural collapse",
]
_SIGNIFICANT_KEYWORDS = [
    "significant", "extensive", "throughout", "multiple rooms",
    "ground floor", "entire", "spread to", "ceiling collapsed",
]


def reserve_estimator(damage_description: str, category: str) -> dict:
    """
    Provides an indicative reserve estimate for a UK home insurance claim based on
    the damage description and claim category.

    Returns: estimated_reserve_gbp (float), confidence (0.0–1.0),
    damage_category_confirmed (string matching Category enum),
    repair_scope ("minor" / "significant" / "total_loss").

    Does NOT provide a binding settlement figure. This estimate is indicative only
    and must not be communicated to the claimant as a quote or offer.

    Input:
    - damage_description: free text, 1–500 characters.
    - category: must match a valid Category enum value (e.g. "escape_of_water", "theft").

    Example: reserve_estimator(
        "Burst pipe under kitchen sink, water damage to cabinet and flooring, plumber estimate £320",
        "escape_of_water"
    )

    Edge cases:
    - Returns ESTIMATOR_UNAVAILABLE if the estimator service is unreachable. In this case,
      do NOT auto-approve the claim — route to adjuster queue for manual assessment.
    - If description contains total-loss language, repair_scope = "total_loss" which requires
      mandatory human escalation regardless of reserve amount.
    - If category is not recognised, defaults to "other" base reserve with reduced confidence.
    """
    if not damage_description or len(damage_description) > 500:
        return make_error(INVALID_FORMAT, "damage_description must be 1–500 characters.")

    base = _CATEGORY_BASE_RESERVES.get(category, 1000.0)
    confidence_penalty = 0.0 if category in _CATEGORY_BASE_RESERVES else 0.15

    desc_lower = damage_description.lower()

    if any(kw in desc_lower for kw in _TOTAL_LOSS_KEYWORDS):
        repair_scope = "total_loss"
        multiplier = 10.0
        confidence = round(0.85 - confidence_penalty, 2)
    elif any(kw in desc_lower for kw in _SIGNIFICANT_KEYWORDS):
        repair_scope = "significant"
        multiplier = 3.0
        confidence = round(0.80 - confidence_penalty, 2)
    else:
        repair_scope = "minor"
        multiplier = 1.0
        confidence = round(0.90 - confidence_penalty, 2)

    return {
        "estimated_reserve_gbp": round(base * multiplier, 2),
        "confidence": confidence,
        "damage_category_confirmed": category,
        "repair_scope": repair_scope,
    }
