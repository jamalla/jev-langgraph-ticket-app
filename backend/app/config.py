"""Settings read from environment variables, plus the mock/real switches.

With no API keys the app runs fully in mock mode. Each key switches on its
real model independently. Env var names follow the TypeSafe SDK docs:
https://docs.typesafe.ai/sdk/python/usage.md
"""
import os

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

JEV_MODEL = os.getenv("JEV_MODEL", "jev-latest")
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

# The four numbers below are per-page averages from LangChain's Jev-vs-LLM
# benchmark (https://gist.github.com/sydney-runkle/a632ba4ea0b2b72501dfa4b6ab2a7d8a).
# Jev 1.13.0: 0.34 s/page, 3,648 in + 318 out tokens for 6 pages (~661/page).
# Claude Sonnet 5: 3.80 s/page, 7,930 in + 864 out tokens for 6 pages (~1,466/page).
# They are LangChain's numbers, not measured by this app.
MOCK_JEV_MS, MOCK_JEV_TOKENS = 340, 661
MOCK_LLM_MS, MOCK_LLM_TOKENS = 1400, 850
LLM_ROUTER_MS, LLM_ROUTER_TOKENS = 3800, 1466
