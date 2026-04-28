from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Category(str, Enum):
    ESCAPE_OF_WATER = "escape_of_water"
    FLOOD = "flood"
    STORM_DAMAGE = "storm_damage"
    THEFT = "theft"
    ATTEMPTED_THEFT = "attempted_theft"
    FIRE_DAMAGE = "fire_damage"
    ACCIDENTAL_DAMAGE = "accidental_damage"
    LIABILITY = "liability"
    FRAUD_SUSPECTED = "fraud_suspected"
    POLICY_QUERY = "policy_query"
    OTHER = "other"


class Action(str, Enum):
    AUTO_APPROVE_PAYMENT = "auto_approve_payment"
    FAST_TRACK_ADJUSTER = "fast_track_adjuster"
    INVESTIGATE = "investigate"
    REQUEST_MORE_INFO = "request_more_info"
    DENY = "deny"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class RepairScope(str, Enum):
    MINOR = "minor"
    SIGNIFICANT = "significant"
    TOTAL_LOSS = "total_loss"


class TriageOutput(BaseModel):
    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: Action
    adjuster_queue: Optional[str] = None
    reserve_estimate_gbp: Optional[float] = None
    excess_gbp: Optional[float] = None
    fraud_score: Optional[float] = None
    cover_type: Optional[str] = None
    repair_scope: Optional[RepairScope] = None
    reasoning: str
    escalation_reason: Optional[str] = None
    retry_count: int = 0
    is_truncated: bool = False


class AgentInput(BaseModel):
    request_id: str
    body: str
    policy_number: str
    claimant_name: str
    channel: str
    timestamp: str


class EscalationRequest(BaseModel):
    request_id: str
    triage: TriageOutput
    reasoning_chain: str
    trigger: str
