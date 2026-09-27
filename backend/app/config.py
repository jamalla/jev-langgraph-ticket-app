"""Settings read from environment variables, plus the mock/real switches.

With no API keys the app runs fully in mock mode. Each key switches on its
real model independently. Env var names follow the TypeSafe SDK docs:
https://docs.typesafe.ai/sdk/python/usage.md
"""
import os

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# `or` also covers a variable that is set but empty (e.g. left blank on Render).
JEV_MODEL = os.getenv("JEV_MODEL") or "jev-latest"
# Empty means TypeSafe's own API. Set it to use another Jev provider with the
# same API, e.g. OpenCode Zen: https://opencode.ai/zen (model "jev-1.13-free").
# https://opencode.ai/docs/zen/
TYPESAFE_BASE_URL = os.getenv("TYPESAFE_BASE_URL", "")
# The LLM provider follows whichever key is set (OpenAI wins if both are).
LLM_PROVIDER = "openai" if OPENAI_API_KEY else "anthropic" if ANTHROPIC_API_KEY else "mock"
DEFAULT_LLM_MODEL = "gpt-5-nano" if LLM_PROVIDER == "openai" else "claude-haiku-4-5-20251001"
LLM_MODEL = os.getenv("LLM_MODEL") or DEFAULT_LLM_MODEL

USE_REAL_JEV = bool(TYPESAFE_API_KEY)
USE_REAL_LLM = LLM_PROVIDER != "mock"

# Mock models sleep to feel realistic. Tests set MOCK_DELAY=0 to run fast.
MOCK_DELAY = os.getenv("MOCK_DELAY", "1") != "0"

# Mock mode only: fixed, made-up step costs so the UI has something to show.
# They are not measurements; the UI marks every mock step with "(mock)".
MOCK_JEV_MS, MOCK_JEV_TOKENS = 340, 661
MOCK_LLM_MS, MOCK_LLM_TOKENS = 1400, 850
