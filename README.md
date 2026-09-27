# jev-langgraph-ticket-app

> **بالعربية:** تطبيق تعليمي صغير يوضح كيف يتقاسم نموذج القرار **Jev** ونموذج اللغة **LLM** العمل داخل سير عمل **LangGraph**.
> يقرر Jev المسار بسرعة وبتكلفة قليلة، ثم يوجّه كود Python التذكرة، ويكتب الـ LLM الرد عند الحاجة فقط، ويوافق إنسان عندما يكون الأمر مهماً.
> يعمل التطبيق دون أي مفاتيح API (وضع المحاكاة)، وتعرض الواجهة كل خطوة مباشرةً.

A small **teaching project** for developers new to these tools. The scenario is support-ticket triage, but the lesson is the **pattern**:

> Jev makes the cheap, fast decision (which path?) → plain Python routes → an LLM does the open-ended writing (only when needed) → a human approves when it matters.

The UI streams every graph step live: which node ran, which kind of model did the work (Jev / LLM / code / human), how long it took, and how many tokens it used.

## 1. What you will learn

- **Decision model vs LLM.** Jev answers fixed questions with numbers, quickly and cheaply. The LLM writes free text, more slowly and at a higher cost. Each one does the job it is good at.
- **`Noul` vs `Score`.** A `Noul` is a yes/no question whose answer is a *probability* (0..1). A `Score` is a graded question whose answer is an *expected value* across levels (e.g. `1.43` on 0..2), not a whole number.
- **Thresholds in code.** Jev gives numbers; your code decides (`is_billing > 0.5`). Never compare a `Score` with `==`.
- **LangGraph basics.** Nodes, edges, conditional edges, typed state and a **reducer** that appends each node's trace entry.
- **Human in the loop and streaming.** `interrupt()` pauses the graph, a checkpointer saves it, and `Command(resume=...)` continues it. `stream_mode="updates"` sends each node's result as soon as it finishes.

## 2. The graph

```
                                      ┌─ close_spam ─────────────────────────────┐
                                      ├─ faq_agent ──────────────────────────────┤
START ─→ supervisor_jev ─→ route ─────┼─ billing_agent ─→ human_review ──────────┼─→ END
         (Jev: 4 questions) (Python)  └─ tech_agent ──┬─ urgency > 1.5 ─→ human_review
                                                      └─ otherwise ─────────────────→ END
```

| Node | Kind | What it does |
|---|---|---|
| `supervisor_jev` | Jev | Asks 4 questions in one call: `is_spam`, `is_billing`, `is_technical` (Noul) and `urgency` (Score) |
| `route` | code | First rule that fires: spam > 0.7 → billing > 0.5 → technical > 0.5 → otherwise FAQ |
| `*_agent` | LLM | A system prompt only, with no tools or memory; writes a 2-3 sentence Arabic reply |
| `close_spam` | code | Closes the ticket without calling an LLM |
| `human_review` | human | `interrupt()`; approve sends the draft, reject hands the ticket to a person |

## 3. Read the code in this order

1. [backend/app/graph.py](backend/app/graph.py): the whole workflow. Start here.
2. [backend/app/jev.py](backend/app/jev.py): the Jev questions, the real SDK call and the keyword mock.
3. [backend/app/llm.py](backend/app/llm.py): the agent prompts and `ChatAnthropic`.
4. [backend/app/main.py](backend/app/main.py): FastAPI, the SSE stream, pause and resume, and the Jev-vs-LLM summary.
5. [frontend/app.js](frontend/app.js): reads the stream and draws the timeline.

[backend/app/config.py](backend/app/config.py) holds the environment variables and benchmark constants.

## 4. Run it

Python 3.12 is recommended (3.11 also works).

```bash
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload
# open http://localhost:8000
```

Docker:

```bash
docker build -t jev-langgraph-ticket-app .
docker run -p 8000:8000 jev-langgraph-ticket-app
```

Tests (mock mode, no delays):

```bash
cd backend && MOCK_DELAY=0 pytest -q
```

Try the sample chips under the chat. `خصم مرتين` and `الدفع متوقف` pause at **human review**; click `موافقة` or `رفض`.

## 5. Use real models

With no keys, both models are mocks: Jev uses keyword matching and the LLM returns fixed replies. Each key switches its model on independently:

```bash
export TYPESAFE_API_KEY=...     # real Jev (typesafe-sdk)
export OPENAI_API_KEY=...       # real LLM via langchain-openai (default model gpt-5-nano)
# or: export ANTHROPIC_API_KEY=...  # real LLM via langchain-anthropic (default claude-haiku-4-5-20251001)
# optional: JEV_MODEL (default jev-latest), LLM_MODEL (overrides the default above)
```

The LLM provider follows whichever key is set; if both are set, OpenAI is used. Both are LangChain chat models, so `llm.invoke(...)` is the same call either way.

**Jev through OpenCode Zen.** Zen serves Jev with the same API, and `jev-1.13-free` is free for a limited time. Use your OpenCode Zen key as the TypeSafe key:

```bash
export TYPESAFE_API_KEY=<your OpenCode Zen key>
export TYPESAFE_BASE_URL=https://opencode.ai/zen   # the SDK adds /v1/systemone
export JEV_MODEL=jev-1.13-free
```

With Docker: `docker run -p 8000:8000 -e TYPESAFE_API_KEY=... -e OPENAI_API_KEY=... jev-langgraph-ticket-app`.
See [.env.example](.env.example) for the full list. Or copy it to `.env`, fill it in, and start with `uvicorn app.main:app --reload --env-file ../.env` (from `backend/`) or `docker run --env-file .env ...`.
The header badge shows `محاكاة` (mock) or `حقيقي` (real).

## 6. Deploy to Render

1. Push this repo to GitHub.
2. In Render, choose **New → Blueprint** and pick the repo. It reads [render.yaml](render.yaml).
3. Optionally, fill in `TYPESAFE_API_KEY` / `ANTHROPIC_API_KEY`. If you leave them empty, the app runs in mock mode.

State lives in memory (`InMemorySaver`), so a restart forgets any paused runs. That is fine for a proof of concept.

## 7. Exercises

1. **Add a question and an agent.** Add a `Noul` such as `is_account` ("Is this about login, password or account access?") in `jev.py`, add an `account_agent` prompt in `llm.py`, then add a node, a rule in `route` and an edge in `graph.py`. Add it to `KIND`, `TITLES` and `AGENTS` in `app.js`.
2. **Move a threshold.** Change `BILLING = 0.5` to `0.95` in `graph.py` and send `خصم مرتين` again. Watch the route change.
3. **Review FAQ answers too.** Change `add_edge("faq_agent", END)` to go to `human_review`.
4. **Add a `Choice` question for intent** instead of three separate Nouls. See the [Noul docs][J1] and the [intent routing pattern](https://docs.typesafe.ai/patterns/intent-routing.md).

## 8. References

**TypeSafe Jev**
- [J1] Noul (yes/no → probability, thresholds in code): https://docs.typesafe.ai/primitives/noul.md
- [J2] Python SDK usage: https://docs.typesafe.ai/sdk/python/usage.md
- [J3] SDK responses: https://docs.typesafe.ai/sdk/python/api/types/responses.md
- [J4] Score (probability-weighted mean): https://docs.typesafe.ai/primitives/score.md
- [J5] LangChain's reference implementation + benchmark: https://gist.github.com/sydney-runkle/a632ba4ea0b2b72501dfa4b6ab2a7d8a
- [J6] Background: https://www.langchain.com/blog/building-prod-with-jev-and-langgraph
- More: [building with System One](https://docs.typesafe.ai/concepts/how-to-build-with-system-one) · [confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing.md) · [intent routing](https://docs.typesafe.ai/patterns/intent-routing.md) · [docs index](https://docs.typesafe.ai/llms.txt)

**LangGraph / LangChain**
- [L1] Graph API: https://docs.langchain.com/oss/python/langgraph/graph-api
- [L2] Persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- [L3] Interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- [L4] Streaming: https://docs.langchain.com/oss/python/langgraph/streaming
- [L5] Overview: https://docs.langchain.com/oss/python/langgraph/overview
- [L6] ChatAnthropic: https://docs.langchain.com/oss/python/integrations/chat/anthropic
- [L7] ChatOpenAI: https://docs.langchain.com/oss/python/integrations/chat/openai

**Render**
- [R1] Blueprint spec: https://render.com/docs/blueprint-spec
- [R2] Web services (bind `0.0.0.0:$PORT`): https://render.com/docs/web-services
- [R3] Docker on Render: https://render.com/docs/docker

## 9. Notes

- **Benchmark numbers are LangChain's, not measured by this app.** The router comparison in the stats panel uses per-page averages from [J5]: Jev 0.34 s and ~661 tokens vs Claude Sonnet 5 3.80 s and ~1,466 tokens. The agent steps are the same in both columns; only the router differs.
- **Mock mode uses keywords, not a model.** For example, `عاجل: الدفع متوقف لجميع العملاء.` contains `دفع`, so the mock scores it as billing, and billing wins in `route`. A real Jev may judge it differently. That is the point of using a model.
- On resume, LangGraph re-runs `human_review` from its start, so code before `interrupt()` must be safe to run twice ([L3]).

[J1]: https://docs.typesafe.ai/primitives/noul.md
