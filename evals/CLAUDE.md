# Eval Conventions

- Eval cases are JSON arrays. Each case has: `id`, `input`, `expected_priority`, `expected_category`, `expected_action`, `is_adversarial` (bool), `notes`.
- When adding adversarial cases, include the injection technique in `notes` (e.g., "role override", "instruction append", "context flooding").
- `run_evals.py` prints a summary table and exits non-zero if accuracy < 0.85 or adversarial-pass-rate < 0.90.
- Never add cases with real ticket data or real user names.
