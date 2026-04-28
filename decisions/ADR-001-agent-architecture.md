# ADR-001: Coordinator + Specialist Agent Architecture

**Status:** Accepted
**Date:** 2026-04-28

## Context

The UK home insurance claims triage agent needs to: ingest inbound claims, enrich with policy and fraud context, classify the claim, and either auto-approve a small payment, route to the appropriate adjuster queue, request further documentation, or deny. Some of these operations are read-only (policy lookup, fraud check, reserve estimation), while others are writes (payment approval, queue assignment, denial recording). Mixing read and write tools in a single agent increases blast radius if the agent misbehaves, and makes scoping the `PreToolUse` hard-block hook harder.

## Decision

Use a **coordinator + two specialist** structure:

```
                    ┌──────────────────────────────┐
  Inbound Claim  →  │         Coordinator          │
                    │  - Ingests claim              │
                    │  - Checks escalation rules    │
                    │  - Runs validation-retry loop │
                    │  - Dispatches via Task tool   │
                    └────────────┬─────────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
   ┌───────────────────────┐           ┌───────────────────────┐
   │    TriageSpecialist   │           │    ActionSpecialist   │
   │  - policy_lookup      │           │  - claim_writer       │
   │  - fraud_check        │           │  - document_requester │
   │  - reserve_estimator  │           │                       │
   │  READ-ONLY tools      │           │  WRITE-capable tools  │
   └───────────────────────┘           └───────────────────────┘
```

**Context passing:** Task subagents do NOT inherit coordinator context. Every dispatch includes the full claim body, policy details, fraud score, and reserve estimate explicitly in the Task prompt. See `CLAUDE.md` for the required prompt template.

**Stop reason handling:** The coordinator handles all four stop reasons explicitly:
- `end_turn`: validate output against `TriageOutput` schema
- `tool_use`: process tool calls, continue loop
- `max_tokens`: emit partial result with `is_truncated: true`, escalate to human
- `stop_sequence`: treat as `end_turn` unless sequence signals error

## Alternatives Considered

- **Single monolithic agent:** Simpler, but a single tool set covering both reads and writes exceeds the 4–5 tool reliability threshold, and the `PreToolUse` hook would need to inspect every tool call rather than only the ActionSpecialist's write calls.
- **Three specialists (classify, enrich, act):** More granular isolation but adds a third context-passing boundary and a third prompt to maintain. The read/write split is the meaningful safety boundary here; classify vs. enrich is not.

## Consequences

- Write operations are isolated to `ActionSpecialist`. It is the only agent that triggers the `PreToolUse` hard-block hook — which checks for payment above £500, fraud flags, sanctions hits, and lapsed policies.
- Context passing is explicit and logged — every Task prompt is captured in the reasoning log.
- Adding a new read capability (e.g. a claims history lookup in future) goes to `TriageSpecialist`; new write capabilities go to `ActionSpecialist`.
- Cert alignment: "coordinator plus specialist subagents via the Task tool, with context passed explicitly in each call."
