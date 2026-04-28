"""
CLI entry point.

Usage:
  # Single claim from flags
  python src/main.py --policy HI-2024-000001 --claimant "Jane Smith" \\
    --body "Burst pipe under kitchen sink, water damage to cabinet and flooring."

  # Single claim from the sample dataset by request_id
  python src/main.py --claim-id CLM-2024-000001

  # Run all sample claims
  python src/main.py --all

  # Run all sample claims and write results to JSON
  python src/main.py --all --output results.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Configure logging before importing local modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress noisy httpx logs from the Anthropic SDK
logging.getLogger("httpx").setLevel(logging.WARNING)

from src.agents.coordinator import CoordinatorResult, run
from src.models import AgentInput

SAMPLE_CLAIMS_PATH = Path(__file__).parent.parent / "data" / "sample_claims.json"


def load_sample_claims() -> list[dict]:
    with open(SAMPLE_CLAIMS_PATH) as f:
        return json.load(f)


def claim_from_dict(d: dict) -> AgentInput:
    return AgentInput(
        request_id=d["request_id"],
        body=d["body"],
        policy_number=d["policy_number"],
        claimant_name=d["claimant_name"],
        channel=d["channel"],
        timestamp=d["timestamp"],
    )


def print_result(result: CoordinatorResult) -> None:
    sep = "─" * 60
    print(f"\n{sep}")
    print(f"CLAIM: {result.request_id}")
    print(sep)

    if result.triage:
        t = result.triage
        print(f"  Category:   {t.category.value}")
        print(f"  Action:     {t.recommended_action.value}")
        print(f"  Confidence: {t.confidence:.0%}")
        if t.reserve_estimate_gbp is not None:
            print(f"  Reserve:    £{t.reserve_estimate_gbp:.0f}")
        if t.excess_gbp is not None:
            print(f"  Excess:     £{t.excess_gbp:.0f}")
        if t.fraud_score is not None:
            print(f"  Fraud score:{t.fraud_score:.2f}")
        print(f"  Retries:    {result.retry_count}")

    if result.escalated:
        print(f"\n  ⚑  ESCALATED: {result.escalation_reason}")
    elif result.action_result:
        print(f"\n  ✓  ACTION: {result.action_result.get('summary', result.action_result)}")

    if result.triage and result.triage.reasoning:
        print(f"\n  Reasoning:\n    {result.triage.reasoning[:300]}{'…' if len(result.triage.reasoning) > 300 else ''}")

    print(sep)


def result_to_dict(result: CoordinatorResult) -> dict:
    return {
        "request_id": result.request_id,
        "escalated": result.escalated,
        "escalation_reason": result.escalation_reason,
        "retry_count": result.retry_count,
        "triage": result.triage.model_dump() if result.triage else None,
        "action_result": result.action_result,
        "error": result.error,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="UK Home Insurance Claims Triage Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Run all sample claims")
    group.add_argument("--claim-id", metavar="ID", help="Run a specific claim from the sample dataset")
    group.add_argument("--body", help="Claim body text (use with --policy and --claimant)")

    parser.add_argument("--policy", help="Policy number (required with --body)")
    parser.add_argument("--claimant", help="Claimant name (required with --body)")
    parser.add_argument("--channel", default="cli", help="Channel (default: cli)")
    parser.add_argument("--output", metavar="FILE", help="Write results to JSON file")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    results: list[CoordinatorResult] = []

    if args.all:
        claims_data = load_sample_claims()
        logger.info("Processing %d sample claims…", len(claims_data))
        for d in claims_data:
            claim = claim_from_dict(d)
            try:
                result = run(claim, client)
            except Exception as exc:
                logger.error("Unhandled exception for %s: %s", d["request_id"], exc)
                result = CoordinatorResult(
                    request_id=d["request_id"],
                    triage=None,
                    action_result=None,
                    escalated=True,
                    escalation_reason=f"Unhandled exception: {exc}",
                    retry_count=0,
                    error=str(exc),
                )
            results.append(result)
            print_result(result)

    elif args.claim_id:
        claims_data = load_sample_claims()
        matching = [d for d in claims_data if d["request_id"] == args.claim_id]
        if not matching:
            logger.error("Claim ID '%s' not found in sample dataset.", args.claim_id)
            sys.exit(1)
        claim = claim_from_dict(matching[0])
        result = run(claim, client)
        results.append(result)
        print_result(result)

    else:  # --body mode
        if not args.policy or not args.claimant:
            parser.error("--body requires --policy and --claimant")
        claim = AgentInput(
            request_id=f"CLI-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            body=args.body,
            policy_number=args.policy,
            claimant_name=args.claimant,
            channel=args.channel,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        result = run(claim, client)
        results.append(result)
        print_result(result)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(
            json.dumps([result_to_dict(r) for r in results], indent=2, default=str)
        )
        logger.info("Results written to %s", out_path)


if __name__ == "__main__":
    main()
