"""The LangGraph workflow. Read this file first.

    START → supervisor_jev → route → close_spam                  → END
                                   | faq_agent                   → END
                                   | billing_agent → human_review → END
                                   | tech_agent    → human_review (urgent only) → END

Jev makes the cheap, fast decision; plain Python routes; an LLM writes the
reply only when needed; a human approves when it matters.
Docs: graph API https://docs.langchain.com/oss/python/langgraph/graph-api
      persistence https://docs.langchain.com/oss/python/langgraph/persistence
      interrupts https://docs.langchain.com/oss/python/langgraph/interrupts
"""
import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .jev import ask_jev
from .llm import ask_llm

# Jev gives numbers; these thresholds turn them into decisions.
# Change one and watch the routing change.
SPAM = 0.7
BILLING = 0.5
TECHNICAL = 0.5
URGENT = 1.5  # urgency is a Score on 0..2, so compare with >, never ==

HANDOFF_REPLY = "تم تحويل طلبك إلى أحد موظفينا وسيتواصل معك قريباً."


class State(TypedDict, total=False):
    text: str
    answers: dict
    route: str
    reply: str
    # Reducer: each node returns a one-item list and LangGraph APPENDS it,
    # instead of overwriting the list. https://docs.langchain.com/oss/python/langgraph/graph-api
    trace: Annotated[list[dict], operator.add]


def supervisor_jev(state: State) -> dict:
    result = ask_jev(state["text"])
    step = {"node": "supervisor_jev", "kind": "jev", "model": result["model"],
            "ms": result["ms"], "tokens": result["tokens"],
            "code": "client.system_one(state=text, questions=QUESTIONS)",
            "answers": result["answers"],
            "thresholds": {"is_spam": SPAM, "is_billing": BILLING,
                           "is_technical": TECHNICAL, "urgency": URGENT}}
    return {"answers": result["answers"], "trace": [step]}


def route(state: State) -> dict:
    # Plain Python: the first rule that fires wins. No model call here.
    a = state["answers"]
    if a["is_spam"] > SPAM:
        target, rule = "close_spam", f'is_spam {a["is_spam"]:.2f} > {SPAM}'
    elif a["is_billing"] > BILLING:
        target, rule = "billing_agent", f'is_billing {a["is_billing"]:.2f} > {BILLING}'
    elif a["is_technical"] > TECHNICAL:
        target, rule = "tech_agent", f'is_technical {a["is_technical"]:.2f} > {TECHNICAL}'
    else:
        target, rule = "faq_agent", "no rule matched"
    step = {"node": "route", "kind": "code", "model": "python", "ms": 0, "tokens": 0,
            "code": f'{rule}  →  return "{target}"', "target": target}
    return {"route": target, "trace": [step]}


def close_spam(state: State) -> dict:
    step = {"node": "close_spam", "kind": "code", "model": "python", "ms": 0, "tokens": 0,
            "code": 'return {"reply": ""}'}
    return {"reply": "", "trace": [step]}


def run_agent(name: str, state: State) -> dict:
    result = ask_llm(name, state["text"])
    step = {"node": name, "kind": "llm", "model": result["model"],
            "ms": result["ms"], "tokens": result["tokens"],
            "code": f'llm.invoke([AGENT_PROMPTS["{name}"], text])'}
    return {"reply": result["reply"], "trace": [step]}


def faq_agent(state: State) -> dict:
    return run_agent("faq_agent", state)


def billing_agent(state: State) -> dict:
    return run_agent("billing_agent", state)


def tech_agent(state: State) -> dict:
    return run_agent("tech_agent", state)


def human_review(state: State) -> dict:
    # interrupt() pauses the graph and saves its state in the checkpointer.
    # The value later passed to Command(resume=...) is returned here.
    # Note: on resume the node re-runs from its start, so keep code before
    # interrupt() free of side effects. https://docs.langchain.com/oss/python/langgraph/interrupts
    decision = interrupt({"reply": state["reply"]})
    reply = state["reply"] if decision == "approve" else HANDOFF_REPLY
    step = {"node": "human_review", "kind": "human", "model": "human", "ms": 0, "tokens": 0,
            "code": "decision = interrupt({\"reply\": reply})", "decision": decision}
    return {"reply": reply, "trace": [step]}


def after_tech(state: State) -> str:
    # Only urgent technical tickets need a human; the rest go straight out.
    return "human_review" if state["answers"]["urgency"] > URGENT else END


def build_graph():
    builder = StateGraph(State)

    # Nodes
    builder.add_node("supervisor_jev", supervisor_jev)
    builder.add_node("route", route)
    builder.add_node("close_spam", close_spam)
    builder.add_node("faq_agent", faq_agent)
    builder.add_node("billing_agent", billing_agent)
    builder.add_node("tech_agent", tech_agent)
    builder.add_node("human_review", human_review)

    # Edges
    builder.add_edge(START, "supervisor_jev")
    builder.add_edge("supervisor_jev", "route")
    # route wrote its choice into state["route"]; the edge just reads it.
    builder.add_conditional_edges("route", lambda s: s["route"],
                                  ["close_spam", "faq_agent", "billing_agent", "tech_agent"])
    builder.add_edge("close_spam", END)
    builder.add_edge("faq_agent", END)
    builder.add_edge("billing_agent", "human_review")
    builder.add_conditional_edges("tech_agent", after_tech, ["human_review", END])
    builder.add_edge("human_review", END)

    # interrupt() needs a checkpointer to save paused runs (in memory here).
    # https://docs.langchain.com/oss/python/langgraph/persistence
    return builder.compile(checkpointer=InMemorySaver())


graph = build_graph()
