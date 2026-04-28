# Agent Conventions

All agents in this directory follow the coordinator/specialist pattern defined in the project CLAUDE.md.

- Never pass context implicitly between coordinator and specialist. Always include the full request body, enriched context, and account status in every Task prompt.
- Every agent module exports a single `run(input: AgentInput) -> AgentOutput` function. No side effects outside of tool calls.
- Log the full reasoning chain (not just the decision) to `logs/` on every run.
