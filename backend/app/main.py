"""FastAPI server: streams each graph step to the browser and serves ../frontend.

Steps are sent as Server-Sent Events (lines of `data: <json>`), one per node,
using LangGraph's "updates" stream mode.
Docs: streaming https://docs.langchain.com/oss/python/langgraph/streaming
      interrupts https://docs.langchain.com/oss/python/langgraph/interrupts
"""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel

from . import config
from .compare import ask_llm_router
from .graph import graph

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="jev-langgraph-ticket-app")

# The LLM-router measurement runs next to the graph, so it never slows the run.
# Results wait here by thread_id until the run finishes (in memory, like the checkpointer).
pool = ThreadPoolExecutor(max_workers=4)
comparisons = {}


class RunRequest(BaseModel):
    text: str


class ResumeRequest(BaseModel):
    thread_id: str
    decision: Literal["approve", "reject"]


def event(event_type: str, **data) -> str:
    # One SSE message. ensure_ascii=False keeps Arabic readable on the wire.
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


def totals(trace: list[dict]) -> dict:
    """What this run actually cost, summed from the measured steps."""
    return {"ms": sum(s["ms"] for s in trace), "tokens": sum(s["tokens"] for s in trace),
            "llm_calls": sum(1 for s in trace if s["kind"] == "llm")}


def router_comparison(trace: list[dict], future) -> dict:
    """Jev's routing step next to the LLM doing the same job on the same ticket."""
    jev_step = next(s for s in trace if s["node"] == "supervisor_jev")
    route_step = next(s for s in trace if s["node"] == "route")
    jev = {"ms": jev_step["ms"], "tokens": jev_step["tokens"], "model": jev_step["model"],
           "route": route_step["target"]}
    try:
        llm = future.result(timeout=120) if future else None
    except Exception as exc:  # show "no measurement" rather than a made-up one
        return {"jev": jev, "llm": None, "error": type(exc).__name__}
    return {"jev": jev, "llm": llm, "error": None}


def stream_run(graph_input, thread_id: str):
    # The thread_id tells the checkpointer which saved run this is.
    # https://docs.langchain.com/oss/python/langgraph/persistence
    run_config = {"configurable": {"thread_id": thread_id}}
    reply = ""
    # With version="v2" each chunk is {"type": "updates", "data": {node: update}}.
    # https://docs.langchain.com/oss/python/langgraph/streaming
    for chunk in graph.stream(graph_input, run_config, stream_mode="updates", version="v2"):
        for node, update in chunk["data"].items():
            if node == "__interrupt__":  # the graph paused at interrupt()
                yield event("paused", thread_id=thread_id, payload=update[0].value)
                return
            reply = update.get("reply", reply)
            for entry in update.get("trace", []):
                yield event("step", **entry)
    # A resumed run only streams the steps after the pause, so read the full
    # trace from the checkpoint for the totals.
    trace = graph.get_state(run_config).values["trace"]
    yield event("done", reply=reply, run=totals(trace))
    # Sent after "done" so the user never waits for the comparison.
    yield event("compare", router=router_comparison(trace, comparisons.pop(thread_id, None)))


def sse(generator) -> StreamingResponse:
    return StreamingResponse(generator, media_type="text/event-stream")


@app.get("/api/health")
def health():
    return {"jev": "real" if config.USE_REAL_JEV else "mock",
            "llm": "real" if config.USE_REAL_LLM else "mock"}


@app.post("/api/run")
def run(req: RunRequest):
    thread_id = str(uuid.uuid4())
    if config.USE_REAL_LLM:
        comparisons[thread_id] = pool.submit(ask_llm_router, req.text)
    return sse(stream_run({"text": req.text}, thread_id))


@app.post("/api/resume")
def resume(req: ResumeRequest):
    # Command(resume=...) becomes the return value of interrupt() in human_review.
    # https://docs.langchain.com/oss/python/langgraph/interrupts
    return sse(stream_run(Command(resume=req.decision), req.thread_id))


# Mounted last so the /api routes above take priority.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
