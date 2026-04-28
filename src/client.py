"""
Anthropic client factory.

Reads environment variables to decide whether to use the direct Anthropic API
or Amazon Bedrock. Set USE_BEDROCK=1 (or CLAUDE_CODE_USE_BEDROCK=1) to route
through Bedrock using your configured AWS credentials.

Model selection:
  CLAUDE_MODEL env var overrides the default for whichever backend is active.
  Bedrock model IDs use the cross-region inference profile format:
    us.anthropic.claude-haiku-4-5-20251001-v1:0
  Direct API model IDs use the short form:
    claude-haiku-4-5-20251001

Cert note: prompt caching (cache_control: ephemeral) is applied per-call in
agent_loop.py on the system prompt. Bedrock supports prompt caching for Claude
models in the same way as the direct API.
"""

import os
from typing import Union

import anthropic

# Default models — override with CLAUDE_MODEL env var
_DEFAULT_DIRECT_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Fallback if 4.5 isn't available in the region
_FALLBACK_BEDROCK_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

Client = Union[anthropic.Anthropic, anthropic.AnthropicBedrock]


def _use_bedrock() -> bool:
    return bool(
        os.getenv("USE_BEDROCK") or os.getenv("CLAUDE_CODE_USE_BEDROCK")
    )


def make_client() -> Client:
    """Return an Anthropic or AnthropicBedrock client based on environment."""
    if _use_bedrock():
        region = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1"))
        return anthropic.AnthropicBedrock(aws_region=region)
    return anthropic.Anthropic()


def default_model() -> str:
    """Return the model ID to use, respecting CLAUDE_MODEL env override."""
    env_model = os.getenv("CLAUDE_MODEL")
    if env_model:
        return env_model
    return _DEFAULT_BEDROCK_MODEL if _use_bedrock() else _DEFAULT_DIRECT_MODEL
