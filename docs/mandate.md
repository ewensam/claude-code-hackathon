# The Mandate — UK Home Insurance Claims Triage Agent

## What the Agent Decides Alone

| Action | Conditions |
|---|---|
| Auto-approve payment (≤£500) | Policy active, fraud_score < 0.3, no sanctions hit, reserve_estimate ≤ £500, excess_gbp < reserve, clear in-scope category (escape_of_water, storm_damage, theft, accidental_damage) |
| Fast-track to adjuster queue | Policy active, fraud_score < 0.3, reserve £500–£25,000, repair_scope not "total_loss", no liability involvement |
| Request more info | Any claim missing required documentation: police report (theft/attempted_theft), photos (any), leak report (escape_of_water with unclear cause), repair quote (storm/water/accidental) |
| Deny | Excess ≥ reserve estimate (loss falls below excess), or cause is explicitly named as an exclusion on the policy (e.g. gradual deterioration, subsidence on a policy without subsidence cover) |

## What the Agent Escalates

Escalation means: generate a human-approval request with full reasoning chain attached, halt further automated action, and route to the appropriate human queue. The human can approve, override, or reassign.

| Trigger | Human queue |
|---|---|
| fraud_score ≥ 0.3 | Fraud investigation queue |
| sanctions_match = True | Compliance team (immediate, silent) |
| Category = `liability` | Specialist liability team |
| reserve_estimate > £25,000 | Specialist adjuster team |
| repair_scope = `total_loss` | Specialist adjuster team |
| Legal language in claim body (e.g. "solicitor", "FOS", "ombudsman", "legal action") | Complaints team |
| Vulnerable customer indicators (e.g. language suggesting bereavement, disability, financial hardship) | Priority human handler |
| Confidence < 0.75 on category classification | Standard adjuster (with low-confidence flag) |
| Policy status = `lapsed` or `cancelled` | Standard adjuster (inform claimant there may be no active cover) |
| Validation retries ≥ 2 on the same claim | Standard adjuster (flag: ambiguous input) |

## What We Are Deliberately Not Automating

- **Liability claims** — any claim involving a third party (neighbour, visitor, public) requires human judgment on liability exposure and legal risk.
- **Total loss assessment** — properties assessed as total loss require a physical survey by a qualified surveyor. No automated decision on total loss.
- **Subsidence claims** — require specialist structural engineering survey. Out of scope for automated triage.
- **Flood Re scheme properties** — properties covered under the Flood Re reinsurance scheme have different pricing and coverage rules. Always escalate flood claims to adjuster to check scheme membership.
- **Vulnerable customer interactions** — FCA Consumer Duty requires that customers showing signs of vulnerability (bereavement, mental health, financial distress) receive human-handled contact. The agent may classify and escalate but must not be the primary point of communication for vulnerable customers.
- **Complaints** — any claim where the claimant uses language indicative of a formal complaint or FOS referral is routed to the complaints team, not the claims team. The two workflows are separate.
- **Claims involving legal representation** — if a claimant mentions a solicitor or legal representative, all communication must go through the legal team.

## Compliance Notes

- **FCA Consumer Duty**: vulnerable customer indicators must trigger a priority human escalation. The agent must not attempt to resolve or further classify a claim once a vulnerability signal is detected.
- **FOS pathway**: any claim referencing the Financial Ombudsman Service is removed from the automated triage flow and sent to the complaints team immediately.
- **ICO / UK GDPR**: claim body text is redacted from routing logs by the `PostToolUse` hook before it enters the context window or persists to storage. Policy numbers and names in logs are pseudonymised.
- **Fraud Re compliance**: reserve estimates are indicative only and must not be disclosed to the claimant as a quote or settlement offer.
- **Threshold sign-off**: any change to the £500 auto-payment threshold, the £25,000 adjuster threshold, or the fraud_score escalation cutoff requires written sign-off from the Head of Claims and the Compliance Officer before deployment.
