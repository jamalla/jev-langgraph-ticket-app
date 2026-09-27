"""Measure an LLM doing Jev's job on the same ticket, for the stats panel.

This is not part of the graph. For each ticket we ask the real LLM the same
four questions Jev answers, route its answers with the same rules, and time
the call, so both sides of the comparison are measured on this ticket.
Without a real LLM there is nothing to measure, and we return None.
Docs: structured output https://docs.langchain.com/oss/python/langchain/models
"""
import time

from pydantic import BaseModel, Field

from . import config
from .graph import pick_route
from .jev import QUESTION_SPECS, URGENCY_CRITERIA, URGENCY_INSTRUCTIONS
from .llm import llm

YES_PROBABILITY = " Answer with the probability that the answer is yes, from 0 to 1."
LEVELS = " ".join(f"{i} = {text}" for i, text in enumerate(URGENCY_CRITERIA))


# The same questions Jev gets, as a typed schema: the LLM must return numbers too.
class RouterAnswers(BaseModel):
    is_spam: float = Field(description=QUESTION_SPECS["is_spam"] + YES_PROBABILITY)
    is_billing: float = Field(description=QUESTION_SPECS["is_billing"] + YES_PROBABILITY)
    is_technical: float = Field(description=QUESTION_SPECS["is_technical"] + YES_PROBABILITY)
    urgency: float = Field(description=f"{URGENCY_INSTRUCTIONS} Answer from 0 to 2 ({LEVELS}).")


SYSTEM = "You classify support tickets. Answer every question about the ticket with a number."


def ask_llm_router(text: str) -> dict | None:
    """Return {"answers", "route", "ms", "tokens", "model"}, or None without a real LLM."""
    if not config.USE_REAL_LLM:
        return None
    # include_raw=True keeps the AIMessage, which carries usage_metadata (token counts).
    # https://docs.langchain.com/oss/python/langchain/models
    router = llm.with_structured_output(RouterAnswers, include_raw=True)
    start = time.perf_counter()
    result = router.invoke([("system", SYSTEM), ("human", text)])
    ms = round((time.perf_counter() - start) * 1000)
    answers = result["parsed"].model_dump()
    return {"answers": answers, "route": pick_route(answers)[0], "ms": ms,
            "tokens": result["raw"].usage_metadata["total_tokens"], "model": config.LLM_MODEL}
