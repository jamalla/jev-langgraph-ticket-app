"""End-to-end tests in mock mode (no API keys), using FastAPI's TestClient.

Run: cd backend && MOCK_DELAY=0 pytest -q
"""
import json
import os

os.environ["MOCK_DELAY"] = "0"
os.environ["TYPESAFE_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def events(response) -> list[dict]:
    return [json.loads(line[len("data: "):])
            for line in response.text.split("\n") if line.startswith("data: ")]


def run(text: str) -> list[dict]:
    return events(client.post("/api/run", json={"text": text}))


def nodes(evs: list[dict]) -> list[str]:
    return [e["node"] for e in evs if e["type"] == "step"]


def test_health_reports_mock():
    assert client.get("/api/health").json() == {"jev": "mock", "llm": "mock"}


def test_faq_question():
    evs = run("كيف أغيّر لغة الحساب؟")
    assert nodes(evs) == ["supervisor_jev", "route", "faq_agent"]
    assert evs[-1]["type"] == "done"


def test_spam_is_closed_without_llm():
    evs = run("اربح الآن! عرض خاص، اضغط هنا.")
    assert nodes(evs)[-1] == "close_spam"
    assert evs[-1]["type"] == "done"
    assert evs[-1]["summary"]["jev"]["llm_calls"] == 0
    assert evs[-1]["summary"]["llm"]["llm_calls"] == 1


def test_billing_pauses_then_approve():
    evs = run("تم خصم المبلغ مرتين، أرجو الاسترداد.")
    assert nodes(evs)[-1] == "billing_agent"
    assert evs[-1]["type"] == "paused"
    thread_id = evs[-1]["thread_id"]
    draft = evs[-1]["payload"]["reply"]

    evs = events(client.post("/api/resume", json={"thread_id": thread_id, "decision": "approve"}))
    assert nodes(evs) == ["human_review"]
    assert evs[-1]["type"] == "done"
    assert evs[-1]["reply"] == draft
    # The summary covers the whole run, not only the resumed part.
    assert evs[-1]["summary"]["jev"]["llm_calls"] == 1


def test_billing_reject_hands_off():
    thread_id = run("تم خصم المبلغ مرتين، أرجو الاسترداد.")[-1]["thread_id"]
    evs = events(client.post("/api/resume", json={"thread_id": thread_id, "decision": "reject"}))
    assert evs[-1]["type"] == "done"
    assert "موظفينا" in evs[-1]["reply"]


def test_urgent_tech_pauses():
    evs = run("عاجل: الدفع متوقف لجميع العملاء.")
    assert evs[-1]["type"] == "paused"


def test_urgent_tech_goes_through_review():
    # "الدفع" also matches billing, so this checks the tech_agent → human_review edge directly.
    evs = run("عاجل: التطبيق لا يعمل لجميع العملاء.")
    assert nodes(evs) == ["supervisor_jev", "route", "tech_agent"]
    assert evs[-1]["type"] == "paused"


def test_normal_tech_finishes_without_review():
    evs = run("التطبيق يتعطل عند رفع ملف.")
    assert nodes(evs) == ["supervisor_jev", "route", "tech_agent"]
    assert evs[-1]["type"] == "done"


def test_frontend_is_served_rtl():
    response = client.get("/")
    assert response.status_code == 200
    assert 'dir="rtl"' in response.text
