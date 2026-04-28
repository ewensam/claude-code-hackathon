# ADR-002: Structured Tool Error Responses

**Status:** Accepted
**Date:** 2026-04-28

## Context

When a tool fails, the agent needs to recover gracefully — retry with corrected input, fall back to an alternative, or escalate. If errors are returned as plain strings, the agent has to parse them, which is unreliable and varies by phrasing.

## Decision

All tools return structured errors:

```python
{"isError": True, "code": "POLICY_NOT_FOUND", "guidance": "Verify the policy number format (e.g. HI-2024-000001) and retry.", "retryable": True, "detail": "..."}
```

Canonical error codes are defined in `src/tools/error_codes.py`. Adding a new error code requires a new entry there — no one-off strings in tool implementations.

Every error code has:
- `code`: uppercase snake-case string, unique across all tools
- `guidance`: one sentence telling the agent what to do next
- `retryable`: bool — if `False`, the agent should escalate rather than retry
- `detail`: optional string with specifics (e.g. the offending input value)

## Alternatives Considered

- **Exception raising:** Exceptions work for Python-internal flows but don't cross the agent boundary cleanly. The SDK passes tool results as content, not exceptions.
- **Plain string errors:** Simpler to write but require the agent to parse, which is fragile and fails on phrasing variation.

## Consequences

- The agent can branch on `isError` without parsing free text.
- The `guidance` field gives the agent explicit next-step instructions, reducing hallucinated recovery strategies.
- The `retryable` field drives the retry vs. escalate decision mechanically — no prompt engineering needed for that branch.
- Error codes are logged in the reasoning chain and auditable.
- Cert alignment: "structured error responses (`isError: true` with a reason code and guidance) so the agent can recover gracefully."
