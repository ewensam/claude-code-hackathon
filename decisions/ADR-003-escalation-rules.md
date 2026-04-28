# ADR-003: Escalation Rules — Category + Confidence + Impact

**Status:** Accepted
**Date:** 2026-04-28

## Context

The agent needs consistent escalation behaviour. Vague rules like "when the agent isn't sure" produce wildly inconsistent escalation rates because "sure" is evaluated differently across claims, categories, and phrasings. The claims and compliance teams need to be able to read and sign off on specific thresholds, not prompt text.

## Decision

Escalation is triggered when **any** of the following discrete conditions are met:

| Condition | Threshold | Rationale |
|---|---|---|
| Confidence score | < 0.75 | Below this, misclassification is as likely as correct classification |
| Fraud score | ≥ 0.30 | Internal fraud team threshold; above this, human review is required |
| Sanctions match | Any | Legal/regulatory hard requirement — no automated action on a sanctioned party |
| Category | `liability` | Third-party involvement always requires human judgment on legal exposure |
| Reserve estimate | > £25,000 | Specialist adjuster authority level |
| Repair scope | `total_loss` | Physical survey is always required; no automated action |
| Legal language in claim body | Any mention of "solicitor", "FOS", "ombudsman", "legal action" | FOS/litigation risk — routes to complaints team |
| Vulnerable customer indicators | Any detected | FCA Consumer Duty mandatory |
| Policy status | `lapsed` or `cancelled` | No valid cover — human must confirm situation with claimant |
| Validation retries | ≥ 2 | Repeated schema failure signals ambiguous or adversarial input |

Escalation = generate a human-approval request with full reasoning chain, route to the appropriate human queue (see `docs/mandate.md`), and halt further automated action on this claim.

**Hard blocks via `PreToolUse` hook (not escalation):**

These stop execution immediately, before the LLM can take the action. They do not produce an escalation request — they produce a hard stop logged to the audit trail.

| Trigger | What's blocked |
|---|---|
| Payment amount > £500 | `claim_writer` "approve_payment" action |
| `fraud_flag_active` or `sanctions_match` = True | Any `claim_writer` or `document_requester` call |
| Policy status = `lapsed` or `cancelled` | Any `claim_writer` call |
| `document_type` not in approved template list | `document_requester` call |

The distinction is important: **escalation is a slow stop** — the LLM routes to a human and the human decides. A **hook is a hard stop** — it runs before the LLM acts and cannot be overridden by prompt. An ADR is written for each because this distinction is tested on the cert exam and matters in production.

## Alternatives Considered

- **Single confidence threshold for everything:** Simple but doesn't account for category-level risk — a 0.80-confidence `liability` classification still needs human eyes regardless of confidence.
- **Free-text escalation criteria:** "Escalate when the situation seems serious." Produces inconsistent behaviour and is not auditable by the compliance team.

## Consequences

- Escalation behaviour is deterministic for any claim with a known category, confidence, and fraud score. It can be tested.
- The compliance team can read the table in `docs/mandate.md` and sign off on specific thresholds without reading code.
- Threshold changes require a new ADR entry and compliance sign-off.
- Cert alignment: "Escalation rules that are category plus confidence plus dollar-impact bucket, rather than vague rules."
