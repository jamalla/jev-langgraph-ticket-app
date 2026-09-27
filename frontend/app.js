// Frontend logic: send a ticket, read the SSE stream of graph steps, draw them.
// The stream is a POST, so we read it with fetch() + getReader() instead of EventSource.

const KIND = {
  START: "start", supervisor_jev: "jev", route: "code", close_spam: "code",
  faq_agent: "llm", billing_agent: "llm", tech_agent: "llm", human_review: "human", END: "end",
};
const TITLES = {
  START: "استلام التذكرة", supervisor_jev: "Jev يصنّف التذكرة", route: "التوجيه",
  close_spam: "إغلاق كرسالة مزعجة", faq_agent: "وكيل الأسئلة الشائعة", billing_agent: "وكيل الفوترة",
  tech_agent: "وكيل الدعم الفني", human_review: "مراجعة بشرية", END: "إرسال الرد",
};
const AGENTS = ["close_spam", "faq_agent", "billing_agent", "tech_agent"];
const SAMPLES = [
  ["خصم مرتين", "تم خصم المبلغ مرتين، أرجو الاسترداد."],
  ["الدفع متوقف", "عاجل: الدفع متوقف لجميع العملاء."],
  ["تطبيق يتعطل", "التطبيق يتعطل عند رفع ملف."],
  ["تغيير اللغة", "كيف أغيّر لغة الحساب؟"],
  ["رسالة مزعجة", "اربح الآن! عرض خاص، اضغط هنا."],
];

const $ = (id) => document.getElementById(id);
let run = null; // the active run: { threadId, totalMs, visited, running, steps, lastNode, route }

function esc(text) {
  return String(text).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
const ltr = (text) => `<span dir="ltr">${esc(text)}</span>`;
const color = (node) => `var(--${KIND[node]})`;
const secs = (ms) => (ms / 1000).toFixed(2) + "s";

// ---------- running a ticket ----------

async function startRun(text) {
  run = { threadId: null, totalMs: 0, visited: new Set(), running: "supervisor_jev",
          steps: {}, lastNode: null, route: null };
  $("steps").innerHTML = "";
  setBusy(true);
  addMessage("user", text);
  renderStep({ node: "START", model: "—", ms: 0, tokens: null,
               code: 'graph.stream({"text": text}, config, stream_mode="updates")' });
  renderGraphStrip();
  const response = await fetch("/api/run", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
  });
  await readStream(response, run);
  unlockIfStreamBroke();
}

async function resumeRun(decision) {
  document.querySelectorAll(".actions button").forEach((b) => (b.disabled = true));
  run.waiting = false;
  $("messages").insertAdjacentHTML("beforeend", `<div class="typing"></div>`);
  const response = await fetch("/api/resume", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: run.threadId, decision }),
  });
  await readStream(response, run);
  unlockIfStreamBroke();
}

// If the server failed mid-run (no "done" or "paused"), let the user try again.
function unlockIfStreamBroke() {
  if (!run.finished && !run.waiting) { setBusy(false); setWaiting(false); }
}

// `owner` is the run that opened this stream; events from an older run are ignored.
async function readStream(response, owner) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const messages = buffer.split("\n\n");
    buffer = messages.pop(); // the last piece may be incomplete; keep it for the next read
    for (const message of messages) {
      for (const line of message.split("\n")) {
        if (line.startsWith("data: ") && owner === run) onEvent(JSON.parse(line.slice(6)));
      }
    }
  }
}

function onEvent(ev) {
  if (ev.type === "step") {
    if (ev.node === "route") run.route = ev.target;
    if (ev.node === "human_review") return finishReview(ev);
    renderStep(ev);
  } else if (ev.type === "paused") {
    run.threadId = ev.thread_id;
    run.waiting = true;
    run.running = "human_review";
    renderStep({ node: "human_review", model: "human", paused: true, draft: ev.payload.reply,
                 code: 'decision = interrupt({"reply": reply})' });
    addMessage("review", ev.payload.reply, run.lastNode);
    setWaiting(true);
  } else if (ev.type === "done") {
    run.running = null;
    run.finished = true;
    renderStep({ node: "END", model: "—", ms: 0, tokens: null, code: 'return state["reply"]' });
    if (run.route === "close_spam") addMessage("pill", "أُغلقت كرسالة مزعجة");
    else addMessage("bot", ev.reply, `${run.lastNode} · ${secs(run.totalMs)}`);
    run.totals = ev.run;
    renderStats();
    setBusy(false);
  } else if (ev.type === "compare") {
    run.router = ev.router;
    renderStats();
  }
  renderGraphStrip();
}

// Which node runs after this one? Mirrors the edges in graph.py, only to draw the gold outline.
function nextNode(ev) {
  if (ev.node === "supervisor_jev") return "route";
  if (ev.node === "route") return ev.target;
  if (ev.node === "billing_agent") return "human_review";
  return null; // tech_agent may or may not need review; "paused" will tell us
}

// ---------- drawing ----------

function renderStep(ev) {
  const isLive = ev.node !== "START" && ev.node !== "END" && !ev.paused;
  run.totalMs += ev.ms || 0;
  if (!ev.paused) run.visited.add(ev.node);
  if (isLive) { run.running = nextNode(ev); if (ev.node !== "route") run.lastNode = ev.node; }

  const chips = ev.node === "human_review" ? ["interrupt"]
    : ev.tokens === null ? []
    : [ev.ms ? `${ev.ms}ms` : "<1ms", `${ev.tokens.toLocaleString("en")} tok`];
  const li = document.createElement("li");
  li.className = ev.paused ? "step waiting" : "step";
  li.style.setProperty("--c", color(ev.node));
  li.innerHTML = `
    <div class="t" dir="ltr">+${secs(run.totalMs)}</div>
    <div class="dot">${$("steps").children.length + 1}</div>
    <div class="body">
      <div class="title-row"><h3>${esc(TITLES[ev.node])}</h3>
        ${chips.map((c) => `<span class="chip" dir="ltr">${esc(c)}</span>`).join("")}
        ${ev.paused ? `<span class="wait-badge"><i class="pulse"></i>بانتظار قرارك</span>` : ""}</div>
      <div class="tags">
        <span class="tag"><span class="k">العقدة</span><span class="v" dir="ltr">${esc(ev.node)}</span></span>
        <span class="tag model"><span class="k">النموذج</span><span class="v" dir="ltr">${esc(ev.model)}</span></span>
      </div>
      ${ev.answers ? renderBars(ev.answers, ev.thresholds) : ""}
      ${ev.paused ? `<div class="draft">${esc(ev.draft)}</div>${reviewButtons()}` : ""}
      <pre class="snippet" dir="ltr">${esc(ev.code)}</pre>
    </div>`;
  $("steps").appendChild(li);
  run.steps[ev.node] = li;
  li.scrollIntoView({ behavior: "smooth", block: "end" });
}

// The human_review step already exists (drawn on "paused"); update it in place.
function finishReview(ev) {
  const li = run.steps.human_review;
  li.classList.remove("waiting");
  li.querySelector(".wait-badge").remove();
  document.querySelectorAll(".actions").forEach((a) => a.remove());
  li.querySelector(".snippet").textContent = `${ev.code}\nCommand(resume="${ev.decision}")`;
  // Collapse the chat card to a one-line result; the reply itself follows as a bot bubble.
  const card = document.querySelector(".review:not(.resolved)");
  card.classList.add("resolved", ev.decision === "approve" ? "is-approved" : "is-rejected");
  card.querySelector(".review-head").textContent =
    ev.decision === "approve" ? "✓ تمت الموافقة على الرد" : "✕ رُفض الرد · حُوِّل إلى موظف";
  setWaiting(false);
  if (ev.decision === "reject") run.lastNode = "human_review"; // the handoff reply came from here
  run.visited.add("human_review");
}

function renderBars(answers, thresholds) {
  const rows = ["is_spam", "is_billing", "is_technical", "urgency"].map((key) => {
    const max = key === "urgency" ? 2 : 1;
    const value = answers[key];
    const label = key === "urgency" ? `${value.toFixed(1)} / 2` : value.toFixed(2);
    return `<div class="bar-row ${value > thresholds[key] ? "hit" : ""}" dir="ltr">
      <span>${key}</span><div class="track"><div class="fill" style="width:${(value / max) * 100}%"></div></div>
      <span class="num">${label}</span></div>`;
  });
  return `<div class="bars">${rows.join("")}</div>`;
}

function renderGraphStrip() {
  const node = (name) => {
    const state = run?.visited.has(name) ? "visited" : "";
    const running = run?.running === name ? (run.waiting ? "waiting" : "running") : "";
    return `<span class="gnode ${state} ${running}" style="--c:${color(name)}" dir="ltr">${name}</span>`;
  };
  const arrow = `<span class="arrow">←</span>`;
  $("graph").innerHTML = [node("START"), node("supervisor_jev"), node("route"),
    `<div class="agents">${AGENTS.map(node).join("")}</div>`, node("human_review"), node("END")]
    .join(arrow);
  $("clock").textContent = secs(run ? run.totalMs : 0);
}

// Every number here is measured: Jev's routing step, the real LLM doing the same job on the
// same ticket (the "compare" event), and this run's totals. Nothing measured → "—".
function renderStats() {
  const t = run?.totals, jev = run?.router?.jev, llm = run?.router?.llm;
  const pending = t && !run.router; // the LLM measurement is still running
  const n = (x) => (x == null ? "—" : x.toLocaleString("en"));
  let speed = "—", speedLabel = "أسرع", saved = "—", savedLabel = "توكنز أقل";
  if (jev && llm) {
    const ratio = llm.ms / jev.ms;
    const x = ratio >= 1 ? ratio : 1 / ratio;
    speed = `×${x >= 10 ? Math.round(x) : x.toFixed(1)}`;
    if (ratio < 1) speedLabel = "أبطأ";
    const pct = Math.round((1 - jev.tokens / llm.tokens) * 100);
    saved = `${Math.abs(pct)}%`;
    if (pct < 0) savedLabel = "توكنز أكثر";
  }
  const max = Math.max(jev?.ms || 0, llm?.ms || 0) || 1;
  const bar = (kind, label, side) => `<div class="rbar ${kind}">
      <div class="lbl"><span dir="ltr">${label}</span><span dir="ltr">${side ? `${secs(side.ms)} · ${n(side.tokens)} tok`
        : kind === "llm" && pending ? "…" : "—"}</span></div>
      <div class="track"><div class="fill" style="width:${side ? (side.ms / max) * 100 : 0}%"></div></div></div>`;
  const cell = (side, value, cls = "") => `<td class="num ${cls}" dir="ltr">${side ? value : "—"}</td>`;
  const differ = jev && llm && jev.route !== llm.route ? "differ" : "";
  const total = (label, value) => `<tr><td>${label}</td><td class="num" dir="ltr">${t ? value : "—"}</td></tr>`;
  const foot = jev?.model.includes("(mock)") ? "محاكاة: الأرقام ليست مقاسة"
    : llm ? `مقاس على هذه التذكرة · LLM: ${esc(llm.model)}`
    : run?.router?.error ? `تعذّر قياس LLM · ${esc(run.router.error)}`
    : run?.router ? "المقارنة تتطلب LLM حقيقي" : "";
  $("stats").innerHTML = `
    <div class="panel-label">التوجيه: Jev مقابل LLM</div>
    <div class="tiles">
      <div class="tile jev"><b dir="ltr">${speed}</b><span>${speedLabel}</span></div>
      <div class="tile"><b dir="ltr">${saved}</b><span>${savedLabel}</span></div>
    </div>
    ${bar("jev", "Jev", jev)}
    ${bar("llm", "LLM", llm)}
    <table class="table">
      <tr><th></th><th class="th-jev">Jev</th><th class="th-llm">LLM</th></tr>
      <tr><td>الزمن</td>${cell(jev, jev && secs(jev.ms))}${cell(llm, llm && secs(llm.ms))}</tr>
      <tr><td>التوكنز</td>${cell(jev, n(jev?.tokens))}${cell(llm, n(llm?.tokens))}</tr>
      <tr class="route-row"><td>المسار</td>${cell(jev, esc(jev?.route))}${cell(llm, esc(llm?.route), differ)}</tr>
    </table>
    <hr>
    <div class="panel-label">هذه التذكرة</div>
    <table class="table">
      ${total("الزمن", t && secs(t.ms))}${total("التوكنز", n(t?.tokens))}${total("استدعاءات LLM", n(t?.llm_calls))}
    </table>
    <div class="foot">${foot}</div>`;
}

function addMessage(kind, text, meta) {
  document.querySelector(".typing")?.remove();
  const box = $("messages");
  if (kind === "user") box.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(text)}</div>`);
  if (kind === "pill") box.insertAdjacentHTML("beforeend", `<div class="pill">${esc(text)}</div>`);
  if (kind === "bot") box.insertAdjacentHTML("beforeend",
    `<div class="bot-wrap"><div class="msg bot">${esc(text)}</div><div class="meta">${ltr(meta)}</div></div>`);
  if (kind === "review") box.insertAdjacentHTML("beforeend", `<div class="review">
      <div class="review-head"><i class="pulse"></i>بانتظار موافقتك</div>
      <div class="review-label">مسودة الرد · ${ltr(meta)}</div>
      <div class="review-draft">${esc(text)}</div>${reviewButtons()}</div>`);
  if ((run?.running && !run.waiting) || kind === "user") box.insertAdjacentHTML("beforeend", `<div class="typing"></div>`);
  box.scrollTop = box.scrollHeight;
}

// The same approve/reject pair appears in the chat card and in the timeline step.
function reviewButtons() {
  return `<div class="actions">
    <button class="approve" onclick="resumeRun('approve')">✓ موافقة وإرسال</button>
    <button class="reject" onclick="resumeRun('reject')">✕ رفض · تحويل لموظف</button></div>`;
}

function setBusy(busy) {
  document.querySelectorAll("#input, #send, .samples button").forEach((el) => (el.disabled = busy));
  if (!busy) { document.querySelector(".typing")?.remove(); $("input").focus(); }
}

// While the graph is paused at interrupt(), make it obvious everywhere that a human is needed.
function setWaiting(waiting) {
  document.body.classList.toggle("awaiting", waiting);
  $("input").placeholder = waiting ? "بانتظار قرارك على الرد أعلاه…" : "اكتب مشكلتك…";
  document.title = (waiting ? "⏸ بانتظار موافقتك · " : "") + "فرز التذاكر · Jev + LangGraph";
}

// ---------- start-up ----------

async function loadHealth() {
  const h = await (await fetch("/api/health")).json();
  const label = (mode) => (mode === "real" ? "حقيقي" : "محاكاة");
  $("mode-badge").textContent = h.jev === h.llm ? label(h.jev) : `Jev ${label(h.jev)} · LLM ${label(h.llm)}`;
}

$("samples").innerHTML = SAMPLES.map(([label]) => `<button type="button" class="chip-btn">${esc(label)}</button>`).join("");
$("samples").querySelectorAll("button").forEach((b, i) => (b.onclick = () => startRun(SAMPLES[i][1])));
$("form").onsubmit = (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text) return;
  $("input").value = "";
  startRun(text);
};
renderGraphStrip();
renderStats();
loadHealth();
