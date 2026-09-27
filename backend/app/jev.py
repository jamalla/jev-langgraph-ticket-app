"""The decision model: ask Jev four questions about a ticket in one call.

Real Jev uses the official `typesafe-sdk`; without a key, a keyword mock
returns answers with exactly the same shape.
Docs: https://docs.typesafe.ai/sdk/python/usage.md
"""
import time

from . import config

# Two Jev primitives:
# - Noul: a yes/no question. The answer is a PROBABILITY of "yes" (0..1), not
#   true/false. Our code turns it into a decision with a threshold.
#   https://docs.typesafe.ai/primitives/noul.md
# - Score: a graded question. The answer is an EXPECTED VALUE over the levels
#   (e.g. 1.43 on a 0..2 scale), not an integer level. Compare it with
#   thresholds, never with ==.  https://docs.typesafe.ai/primitives/score.md
QUESTION_SPECS = {
    "is_spam": "Is this message spam, marketing, or unrelated to our product?",
    "is_billing": "Is this about payments, invoices, charges, refunds or subscriptions?",
    "is_technical": "Is the user reporting a bug, an error, or something not working?",
}
URGENCY_INSTRUCTIONS = "How urgent is this message?"
URGENCY_CRITERIA = [
    "Low: a question, no impact.",
    "Normal: broken but has a workaround.",
    "Urgent: blocked or production is down.",
]

client = None
QUESTIONS = None
if config.USE_REAL_JEV:
    # Create the client once, only when a key is set.
    # https://docs.typesafe.ai/sdk/python/usage.md
    from typesafe_sdk import Noul, Score, TypeSafeClient

    client = TypeSafeClient(api_key=config.TYPESAFE_API_KEY, model=config.JEV_MODEL,
                            base_url=config.TYPESAFE_BASE_URL or None)
    QUESTIONS = {key: Noul(instructions=text) for key, text in QUESTION_SPECS.items()}
    QUESTIONS["urgency"] = Score(instructions=URGENCY_INSTRUCTIONS, criteria=URGENCY_CRITERIA)


def ask_real(text: str) -> dict:
    start = time.perf_counter()
    # One call answers all four questions.
    # https://docs.typesafe.ai/sdk/python/api/types/responses.md
    response = client.system_one(state=text, questions=QUESTIONS)
    ms = round((time.perf_counter() - start) * 1000)
    answers = {key: response.nouls[key].noul for key in QUESTION_SPECS}
    answers["urgency"] = response.scores["urgency"].score
    # usage fields may be None, so treat missing values as 0.
    tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
    return {"answers": answers, "ms": ms, "tokens": tokens, "model": config.JEV_MODEL}


# Mock keywords, Arabic and English. This is keyword matching, not a model.
KEYWORDS = {
    "is_spam": ["اربح", "ربح", "عرض خاص", "اضغط هنا", "crypto", "seo"],
    "is_billing": ["استرداد", "استرجاع", "خصم", "فاتورة", "دفع", "مرتين", "اشتراك",
                   "refund", "invoice", "charged"],
    "is_technical": ["خطأ", "لا يعمل", "متوقف", "عطل", "يتعطل", "error", "crash", "down"],
}
URGENT_KEYWORDS = ["عاجل", "فوراً", "فورا", "جميع العملاء", "urgent"]


def has_any(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def ask_mock(text: str) -> dict:
    if config.MOCK_DELAY:
        time.sleep(config.MOCK_JEV_MS / 1000)
    answers = {key: 0.93 if has_any(text, words) else 0.04 for key, words in KEYWORDS.items()}
    answers["urgency"] = 1.85 if has_any(text, URGENT_KEYWORDS) else 0.4
    return {"answers": answers, "ms": config.MOCK_JEV_MS, "tokens": config.MOCK_JEV_TOKENS,
            "model": f"{config.JEV_MODEL} (mock)"}


def ask_jev(text: str) -> dict:
    """Return {"answers": {...4 floats...}, "ms", "tokens", "model"} as plain Python types."""
    return ask_real(text) if config.USE_REAL_JEV else ask_mock(text)
