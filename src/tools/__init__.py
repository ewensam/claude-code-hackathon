from .policy_lookup import policy_lookup
from .fraud_check import fraud_check
from .reserve_estimator import reserve_estimator
from .claim_writer import claim_writer
from .document_requester import document_requester

TRIAGE_TOOL_EXECUTOR = {
    "policy_lookup": lambda inp: policy_lookup(inp["policy_number"]),
    "fraud_check": lambda inp: fraud_check(inp["claimant_name"], inp["policy_number"]),
    "reserve_estimator": lambda inp: reserve_estimator(inp["damage_description"], inp["category"]),
}

ACTION_TOOL_EXECUTOR = {
    "claim_writer": lambda inp: claim_writer(inp["claim_id"], inp["action_type"], inp.get("payload", {})),
    "document_requester": lambda inp: document_requester(inp["policy_number"], inp["document_type"], inp["reason_code"]),
}
