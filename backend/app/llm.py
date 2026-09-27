"""The LLM agents: each agent is just a system prompt (no tools, no memory).

The LLM does the open-ended writing, and only runs after Jev has picked
the path. Real calls use ChatOpenAI or ChatAnthropic (both LangChain chat
models, so the calling code is the same); without a key, a mock returns a
fixed Arabic reply per agent.
Docs: https://docs.langchain.com/oss/python/integrations/chat/openai
      https://docs.langchain.com/oss/python/integrations/chat/anthropic
"""
import time

from . import config

AGENT_PROMPTS = {
    "billing_agent": "You are the billing support agent. Reply in Arabic in 2-3 short sentences.",
    "tech_agent": "You are the technical support agent. Reply in Arabic in 2-3 short sentences.",
    "faq_agent": "You are the help-center agent. Reply in Arabic in 2-3 short sentences.",
}

MOCK_REPLIES = {
    "billing_agent": "نعتذر عن ذلك. وجدنا الخصم المكرر وأنشأنا طلب استرداد للمبلغ.",
    "tech_agent": "شكراً لإبلاغنا. فريقنا الفني يراجع المشكلة الآن، وجرّب تحديث التطبيق إلى آخر إصدار.",
    "faq_agent": "يمكنك تغيير لغة الحساب من الإعدادات ثم اختيار اللغة المفضلة.",
}

# Create the chat model once, only when a key is set.
llm = None
if config.LLM_PROVIDER == "openai":
    # https://docs.langchain.com/oss/python/integrations/chat/openai
    from langchain_openai import ChatOpenAI

    # No token cap: reasoning models (e.g. gpt-5-nano) spend hidden tokens
    # first, and a small cap can leave the visible reply empty.
    llm = ChatOpenAI(model=config.LLM_MODEL)
elif config.LLM_PROVIDER == "anthropic":
    # https://docs.langchain.com/oss/python/integrations/chat/anthropic
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(model=config.LLM_MODEL, max_tokens=300)


def ask_real(agent: str, text: str) -> dict:
    start = time.perf_counter()
    # Same call for both providers: (role, content) tuples in, an AIMessage out.
    # msg.text is the reply as plain text; usage_metadata holds token counts.
    # https://docs.langchain.com/oss/python/integrations/chat/openai
    msg = llm.invoke([("system", AGENT_PROMPTS[agent]), ("human", text)])
    ms = round((time.perf_counter() - start) * 1000)
    return {"reply": str(msg.text), "ms": ms, "tokens": msg.usage_metadata["total_tokens"],
            "model": config.LLM_MODEL}


def ask_mock(agent: str, text: str) -> dict:
    if config.MOCK_DELAY:
        time.sleep(config.MOCK_LLM_MS / 1000)
    return {"reply": MOCK_REPLIES[agent], "ms": config.MOCK_LLM_MS,
            "tokens": config.MOCK_LLM_TOKENS, "model": f"{config.LLM_MODEL} (mock)"}


def ask_llm(agent: str, text: str) -> dict:
    """Return {"reply", "ms", "tokens", "model"} for one agent."""
    return ask_real(agent, text) if config.USE_REAL_LLM else ask_mock(agent, text)
