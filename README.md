# Claude Code Hackathon — UK Home Insurance Claims Triage Agent

## Solo vs. Team Note

This project is completed by a single participant. The hackathon brief assumes a team with PM, architect, dev, test, and platform roles. Here, one person plays every role, and Claude Code is the force multiplier that makes it viable. As a result:

- **`CLAUDE.md` is simpler.** No need for a shared conventions doc to coordinate multiple people. One project-level `CLAUDE.md` is sufficient; the three-level hierarchy (user / project / directory) is still used, but the user level lives in `~/.claude/CLAUDE.md` as personal preferences, and the directory level is only added where per-module context genuinely differs.
- **Depth over breadth is more important.** With one person, attempting all eight challenges is unrealistic. Challenges are picked for maximum cert-domain coverage and production-readiness signal.
- **No coordination overhead.** Decisions are made, documented in ADRs, and committed.

---

## Participants

- Sam Ewen (PM, Architect, Developer, QA — all roles)

---

## Scenario

Scenario 5: Agentic Solution — UK Home Insurance Claims Triage Agent

**Domain chosen:** UK Home Insurance. Inbound claims arrive from claimants via web form, email, and chat. The agent classifies the claim type (escape of water, storm damage, theft, fire), estimates the reserve, checks fraud/sanctions, and decides: auto-approve payment (≤£500), fast-track to adjuster, request more documentation, deny (below excess or excluded cause), or escalate to human. FCA Consumer Duty and UK regulatory context throughout.

---

## What We Built

An end-to-end claims triage agent built on the Claude Agent SDK. A coordinator agent ingests inbound claims, enriches them with policy details, fraud scores, and a reserve estimate via specialist subagents, then routes them to the appropriate outcome.

Two specialist subagents divide the read/write boundary: `TriageSpecialist` runs all read-only enrichment (policy lookup, fraud check, reserve estimation); `ActionSpecialist` executes writes (payment approval up to £500, adjuster queue assignment, denial recording, document requests). A `PreToolUse` hook hard-blocks write actions that hit mandatory stop conditions — payment above £500, sanctions matches, lapsed policies — before the LLM can reach them. A validation-retry loop wraps structured output: schema failures are fed back with the specific error and retried up to three times before escalating.

What runs: coordinator agent, two specialist subagents, five custom tools, PreToolUse hook, adversarial eval set.
What's scaffolded: the human-approval UI (stubbed as CLI prompt), CI eval harness (runs locally, not yet wired to CI).

---

## Challenges Attempted

| # | Challenge | Status | Notes |
|---|---|---|---|
| 1 | The Mandate | done | `docs/mandate.md` — scope, escalation policy, deliberate exclusions, FCA/FOS compliance notes |
| 2 | The Bones | done | `decisions/ADR-001` with coordinator/specialist diagram, stop_reason handling, context-passing template |
| 3 | The Tools | done | 5 tools across 2 specialists; structured errors with reason codes and retryable flag |
| 4 | The Triage | done | Coordinator with validation-retry loop, full reasoning log per claim |
| 5 | The Brake | done | `PreToolUse` hook + explicit escalation table (category + fraud score + reserve + regulatory triggers) |
| 6 | The Attack | partial | 10 labelled adversarial cases; harness runs locally |
| 7 | The Scorecard | skipped | |
| 8 | The Loop | skipped | |

---

## Key Decisions

- **UK Home Insurance domain** — domain expertise in this area makes the escalation thresholds and exclusion rules defensible rather than invented. FCA Consumer Duty and FOS escalation path add real regulatory grounding to the mandate.
- **Auto-payment up to £500** — the agent makes a real write decision, not just a classification. This made the `PreToolUse` hook essential rather than optional, and surfaces the hardest design question in the scenario: where does the LLM stop and the hard block begin.
- **Coordinator + two specialists split at the read/write boundary** — the `ActionSpecialist` is the only agent that needs the `PreToolUse` hook. See [decisions/ADR-001](decisions/ADR-001-agent-architecture.md).
- **Structured errors over string errors** — `retryable` flag drives recovery logic mechanically, not via prompt engineering. See [decisions/ADR-002](decisions/ADR-002-tool-error-format.md).
- **Escalation uses category + fraud score + reserve + regulatory triggers** — not a single confidence threshold. The compliance team can read and sign off on the table without reading code. See [decisions/ADR-003](decisions/ADR-003-escalation-rules.md).

---

## How to Run It

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=your_key_here

# Run the agent on a single claim
python src/main.py --policy HI-2024-000001 --claimant "Jane Smith" \
  --body "Burst pipe under the kitchen sink. Water damage to cabinet and flooring. Plumber quote is £320."

# Run a storm damage claim
python src/main.py --policy HI-2024-000002 --claimant "David Jones" \
  --body "Storm last night took out three roof tiles. Getting quotes — roofer estimated around £1,800."

# Run with human-approval mode enabled
python src/main.py --policy HI-2024-000001 --claimant "Jane Smith" \
  --body "Kitchen fire, significant smoke damage throughout ground floor." \
  --require-approval

# Run the adversarial eval set
python evals/run_evals.py
```

---

## If We Had More Time

1. **Scorecard CI harness** — wire `evals/run_evals.py` into GitHub Actions; accuracy and adversarial-pass rate move with every commit and are visible to the risk team.
2. **The Loop** — pipe human override signals back as labelled few-shot examples for the classifier, closing the feedback loop end-to-end.
3. **Trajectory logging and LLM review** — each agent run should emit a structured trajectory (input, tool calls in order, reasoning chain, final decision) to `logs/trajectories/` as newline-delimited JSON. Periodic LLM review of trajectories would surface systematic misclassification and reasoning drift without requiring human review of every case. Human review reserved for escalated and overridden cases. The infrastructure is straightforward — a `PostToolUse` hook writes each step, and a reviewer script runs the batch — but not implemented for the hackathon.
3. **Real channel connectors** — email IMAP poller and web form webhook instead of CLI input.
4. **Approval surface** — replace the CLI prompt with a minimal web UI showing the reasoning chain, fraud score, and reserve estimate alongside approve/override buttons.
5. **MCP server** — expose `policy_lookup`, `fraud_check`, and `reserve_estimator` as an MCP server so any fresh Claude session picks the right tool on the first try without re-implementing the tool layer.
6. **Claims history tool** — deliberately excluded from the initial build to keep specialist tool count at 3. Would be the natural next addition to `TriageSpecialist`.
7. **Flood Re scheme check** — flood claims on Flood Re properties need a separate routing path; currently escalated to adjuster with a manual flag.

---

## How We Used Claude Code

- Used Plan Mode before every architecture and domain-modelling decision — forced explicit reasoning about coordinator/specialist boundaries and escalation threshold design before writing any code.
- `CLAUDE.md` tool-design rules (structured errors, 4–5 tools per specialist, boundary descriptions) were written first and used as a constraint during implementation. Claude Code flagged two tool descriptions missing a "what it does NOT do" section before they were accepted.
- Subagent context passing was the hardest part to get right. The explicit context block template in `CLAUDE.md` was written after the first coordinator run showed the specialist had no knowledge of the claim body.
- The adversarial eval set was built collaboratively: asked Claude Code to generate prompt-injection and metadata-spoofing variants for each claim category, then reviewed and labelled them manually.
- The `PreToolUse` hook boundary — hard stop vs. soft escalation — was the design question that generated the most iteration. The ADR captures the reasoning; the `CLAUDE.md` captures the rule.
