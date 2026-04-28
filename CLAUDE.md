# CLAUDE.md — UK Home Insurance Claims Triage Agent

## Solo-Worker Note on CLAUDE.md Structure

The hackathon brief recommends a three-level `CLAUDE.md` hierarchy: user-level (personal preferences in `~/.claude/CLAUDE.md`), project-level (this file, shared in VCS), and directory-level (per-module context in subdirectory `CLAUDE.md` files). For a solo participant, this simplifies as follows:

- **User level** (`~/.claude/CLAUDE.md`): personal coding style preferences that apply everywhere — not in this repo.
- **Project level** (this file): conventions, architecture rules, and domain context that Claude Code needs to work correctly in this project. Everything here.
- **Directory level**: only added where a subdirectory genuinely needs different conventions. Currently: `src/agents/CLAUDE.md` and `evals/CLAUDE.md`.

For teams, the project-level file would also carry "how we coordinate" notes. Solo, that section is omitted.

---

## Project Overview

**Scenario:** Agentic Solution (Scenario 5)
**Domain:** UK Home Insurance — inbound claims triage
**Goal:** Coordinator agent that ingests home insurance claims, classifies category and severity, routes to the correct adjuster queue or auto-approves payment (≤£500), and escalates to humans for anything above confidence or impact thresholds.

**Must-not-touch rules (enforced by hook, not prompt):**
- Never issue an auto-payment above £500.
- Never take any write action on a lapsed or cancelled policy.
- Never proceed after a sanctions match — escalate silently to compliance.
- Never communicate to the claimant using free text — only approved templates via `document_requester`.

---

## Architecture Conventions

### Coordinator / Specialist Split

- The **coordinator** (`src/agents/coordinator.py`) ingests, enriches, and routes. It does NOT execute write actions.
- **TriageSpecialist** (`src/agents/triage_specialist.py`) handles classification, reserve estimation, policy lookup, and fraud check. Read-only tools only.
- **ActionSpecialist** (`src/agents/action_specialist.py`) handles writes: payment approval, queue assignment, denial recording, document requests. This is the only agent with write-capable tools and the only one the `PreToolUse` hook scopes to.

### Context Passing to Subagents

Task subagents do NOT inherit coordinator context. Every Task call must include:

```python
task_prompt = f"""
You are the TriageSpecialist for a UK home insurance claims triage system.

CLAIM BODY:
{claim.body}

CLAIMANT: {claim.claimant_name} | POLICY: {claim.policy_number}
CHANNEL: {claim.channel} | TIMESTAMP: {claim.timestamp}

POLICY DETAILS (from policy_lookup):
- Status: {policy.status}
- Cover type: {policy.cover_type}
- Excess: £{policy.excess_gbp}
- Exclusions: {policy.exclusions}

Classify the claim category, estimate the reserve using reserve_estimator,
run fraud_check, and return a TriageOutput JSON matching the schema.
"""
```

Never rely on the specialist "knowing" anything from earlier in the coordinator's session.

### Stop Reason Handling

Always handle all stop reasons explicitly:
- `end_turn`: normal completion, validate output against `TriageOutput` schema
- `tool_use`: process tool calls, continue loop
- `max_tokens`: log truncation, emit partial result with `is_truncated: true`, escalate to human
- `stop_sequence`: treat as `end_turn` unless sequence indicates error

---

## Tool Design Rules

1. **4–5 tools per specialist maximum.** Reliability drops past this range. `TriageSpecialist` has 3; `ActionSpecialist` has 2.

2. **Every tool description must include:**
   - What the tool DOES (one sentence)
   - What the tool does NOT do (explicit exclusions)
   - Input format and constraints
   - At least one example call
   - Edge cases that return errors

3. **Structured error responses only.** No string error messages. All errors return:
   ```python
   {"isError": True, "code": "POLICY_LAPSED", "guidance": "...", "retryable": False, "detail": "..."}
   ```
   Reason codes are defined in `src/tools/error_codes.py`. Never define one-off error strings in tool implementations.

4. **`retryable` drives recovery logic, not prompt.** If `retryable: False`, the agent escalates. If `retryable: True`, it corrects input and retries. This branch is mechanical, not probabilistic.

---

## Validation-Retry Loop

Wrap all structured output from agents in a validator:

```python
for attempt in range(MAX_RETRIES):  # MAX_RETRIES = 3
    result = agent.run(prompt)
    validation_error = validate_triage_output(result)
    if not validation_error:
        break
    log_retry(attempt, validation_error)
    prompt = build_retry_prompt(prompt, validation_error)
else:
    escalate_to_human(claim, reason="validation_exhausted")
```

Log `retry_count` and `error_type` per claim. Never silently swallow a validation failure.

---

## Escalation Rules

Escalation is triggered when **any** of the following conditions are met:

| Condition | Threshold |
|---|---|
| Confidence score | < 0.75 |
| Fraud score | ≥ 0.30 |
| Sanctions match | Any |
| Category | `liability` |
| Reserve estimate | > £25,000 |
| Repair scope | `total_loss` |
| Legal language in body | Any |
| Vulnerable customer indicators | Any |
| Policy status | `lapsed` or `cancelled` |
| Validation retries | ≥ 2 |

Escalation produces a human-approval request with the full reasoning chain attached. It is NOT a hard block — the human can approve, override, or reassign.

---

## Hooks

- **`PreToolUse`**: Runs before every tool call on the `ActionSpecialist`. Blocks writes that hit the hard-stop list (payment > £500, fraud/sanctions active, lapsed policy, unapproved template). Returns `{block: true, reason: "..."}`. Never relies on the LLM to enforce these — that's the point.
- **`PostToolUse`**: Redacts claim body text and PII (claimant name, postcode, policy number) from tool results before they persist to logs or re-enter the context window.

Hook implementations are in `src/hooks/`. They must be deterministic — no LLM calls inside a hook.

---

## File Structure

```
src/
  agents/
    coordinator.py          # Coordinator agent + main loop
    triage_specialist.py    # Read-only classification specialist
    action_specialist.py    # Write-capable action specialist
    CLAUDE.md               # Agent-specific conventions
  tools/
    policy_lookup.py        # Policy admin system read
    fraud_check.py          # Fraud register + sanctions check
    reserve_estimator.py    # Indicative reserve estimate
    claim_writer.py         # Payment, queue, denial writes
    document_requester.py   # Templated document requests
    error_codes.py          # Canonical error code registry
  hooks/
    pre_tool_use.py         # Hard-block hook
    post_tool_use.py        # PII redaction hook
  models.py                 # Pydantic schemas (TriageOutput, AgentInput, etc.)
  main.py                   # CLI entry point

decisions/
  ADR-001-agent-architecture.md
  ADR-002-tool-error-format.md
  ADR-003-escalation-rules.md

docs/
  mandate.md                # The Mandate: what the agent decides alone vs escalates

evals/
  adversarial_cases.json    # Labelled adversarial eval set
  normal_cases.json         # Labelled normal traffic eval set
  run_evals.py              # Eval harness
  CLAUDE.md                 # Eval-specific conventions

presentation.html           # HTML deck for judging
```

---

## Plan Mode Usage

Use Plan Mode (`/plan`) before:
- Any change to the coordinator/specialist split or context-passing strategy
- Adding or removing a tool from a specialist
- Modifying escalation thresholds or hook logic
- Any change to the auto-payment threshold or fraud score cutoff

Do NOT use Plan Mode for:
- Adding new eval cases
- Updating tool descriptions or docstrings
- Fixing a bug in an existing tool implementation
- Adding new error codes

---

## Cert Domain Coverage

| Challenge | Cert Domain |
|---|---|
| Bones (ADR) | Agentic Architecture |
| Tools | Tool Design & MCP |
| Triage (coordinator) | Agentic Architecture + Prompt Engineering |
| Brake (hooks) | Context Management |
| Attack (evals) | Context Management + Prompt Engineering |
| CLAUDE.md structure | Claude Code Config |
