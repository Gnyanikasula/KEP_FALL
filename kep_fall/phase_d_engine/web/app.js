/*
 * KEP_FALL frontend — SSE streaming + tabbed verdict panel.
 *
 * Streaming: submitQuestion() opens POST /query/stream and renders live step
 *   events (routing → retrieving → synthesizing) before the verdict arrives.
 * Tabs: every verdict card has three tabs, all derived from existing fields:
 *   Verdict     — badge, confidence gauge, reasoning, conditions
 *   Citations   — rules[] parsed into regulation + article rows
 *   Regulations — bar chart counting how many rules cite each regulation
 */

const API_BASE = "";
document.getElementById("docs-link").href = "/docs";

const els = {
  sessionList: document.getElementById("session-list"),
  messages:    document.getElementById("messages"),
  question:    document.getElementById("question"),
  send:        document.getElementById("send"),
  newSession:  document.getElementById("new-session"),
  activeTitle: document.getElementById("active-title"),
};

let activeSessionId = localStorage.getItem("shield_session_id") || null;
let lastQuestion = "";

// ── API helpers ──────────────────────────────────────────────────────────────
async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" }, ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.status === 204 ? null : res.json();
}
const listSessions  = () => api("/sessions");
const getHistory    = (id) => api(`/sessions/${id}/history`);
const deleteSession = (id) => api(`/sessions/${id}`, { method: "DELETE" });

// ── Render routing ───────────────────────────────────────────────────────────
function shouldShowCard(v) {
  const decisions = ["Allowed", "Conditionally Allowed", "Prohibited", "Unclear"];
  if (decisions.includes(v.verdict)) return true;
  if (v.verdict === "Informational" && v.rules && v.rules.length > 0) return true;
  return false;
}
function renderAssistantResponse(v, evidence) {
  shouldShowCard(v) ? renderVerdict(v, evidence) : renderPlainMessage(v);
}

function renderPlainMessage(v) {
  const div = document.createElement("div");
  div.className = "msg-assistant msg-plain";
  div.innerHTML = escapeHtml(v.reasoning || "").replace(/\n/g, "<br>");
  els.messages.appendChild(div);
}

// ── Citation parsing ─────────────────────────────────────────────────────────
// "GDPR, Article 9" → { reg: "GDPR", art: "Article 9" }
// "EU AI Act, Article 6" → { reg: "EU AI Act", art: "Article 6" }
function parseRule(rule) {
  const idx = rule.indexOf(",");
  if (idx === -1) return { reg: rule.trim(), art: "" };
  return { reg: rule.slice(0, idx).trim(), art: rule.slice(idx + 1).trim() };
}

function regulationCounts(rules) {
  const counts = {};
  (rules || []).forEach((r) => {
    const { reg } = parseRule(r);
    counts[reg] = (counts[reg] || 0) + 1;
  });
  return counts;
}

// Article-level grounding key — mirrors engine._art_key so a citation row and
// a grounding item for the same article produce the same string and match.
const _REG_PREFIX = {
  "gdpr": "GDPR", "uk gdpr": "GDPR", "eu gdpr": "GDPR",
  "eu ai act": "EUAI", "ai act": "EUAI",
  "eu mdr 2017/745": "EUMDR", "eu mdr": "EUMDR", "mdr": "EUMDR",
  "uk mdr 2002": "UKMDR", "uk mdr": "UKMDR",
  "duaa 2025": "DUAA", "duaa": "DUAA",
};
function groundingKey(regulation, provision) {
  const reg = (regulation || "").trim().toLowerCase();
  const pre = _REG_PREFIX[reg] || (regulation || "").replace(/\s+/g, "");
  let rest = (provision || "").replace(/article/ig, "").trim();
  rest = rest.replace(/\(.*/, "");        // drop (2)(a)
  rest = rest.replace(/S80-/i, "");       // DUAA S80-22C -> 22C
  rest = rest.replace(/\s+/g, "");
  return `${pre}_Art${rest}`;
}

// Attach graph/corpus/ungrounded badges to the citation rows once the
// grounding frame arrives (after the verdict card is already in the DOM).
function applyGrounding(g) {
  const items = (g && g.items) || [];
  // Find the most recently rendered citation grid that hasn't been marked yet.
  const grids = document.querySelectorAll(".grounding-summary:not([data-done])");
  const summary = grids[grids.length - 1];
  if (!summary) return;
  summary.setAttribute("data-done", "1");
  const card = summary.closest(".verdict-card");
  if (!card) return;

  const byKey = {};
  items.forEach((it) => { byKey[groundingKey(it.regulation, it.provision)] = it.status; });

  const LABEL = { graph: "graph", corpus: "corpus", ungrounded: "ungrounded" };
  card.querySelectorAll(".citation-row").forEach((row) => {
    const status = byKey[row.dataset.gkey] || "ungrounded";
    const slot = row.querySelector(".citation-ground");
    if (slot) {
      slot.className = `citation-ground cg-${status}`;
      slot.textContent = LABEL[status];
      slot.title = {
        graph: "Backed by a knowledge-graph edge",
        corpus: "Backed by a retrieved passage",
        ungrounded: "Not found in retrieved evidence",
      }[status];
    }
  });

  const c = g.counts || {};
  const pct = Math.round((g.grounded_ratio != null ? g.grounded_ratio : 1) * 100);
  summary.innerHTML =
    `<span class="gs-pct">${pct}% grounded</span>` +
    `<span class="gs-detail">${c.graph || 0} graph · ${c.corpus || 0} corpus` +
    (c.ungrounded ? ` · <span class="gs-warn">${c.ungrounded} ungrounded</span>` : ``) +
    `</span>`;
}

// ── Verdict card with tabs ───────────────────────────────────────────────────
function verdictClass(v) {
  if (v === "Allowed")               return "v-Allowed";
  if (v === "Prohibited")            return "v-Prohibited";
  if (v === "Conditionally Allowed") return "v-Conditional";
  if (v === "Informational")         return "v-Informational";
  if (v === "Out of Scope")          return "v-OutOfScope";
  return "v-Unclear";
}

function gaugeColor(conf) {
  if (conf >= 80) return "var(--green)";
  if (conf >= 60) return "var(--gold)";
  return "var(--red)";
}

function renderVerdict(v, evidence) {
  const wrap = document.createElement("div");
  wrap.className = "msg-assistant";
  const cid = "vc-" + Math.random().toString(36).slice(2, 8);

  const conf = v.confidence ?? 0;
  const rules = v.rules || [];
  const conditions = v.conditions || [];

  // — Tab 1: Verdict —
  const parsed = v.parsed || {};
  const ctxChips = [
    parsed.intent             ? `<span class="ctx-chip ctx-intent">${escapeHtml(parsed.intent)}</span>` : "",
    parsed.purpose            ? `<span class="ctx-chip ctx-purpose">${escapeHtml(parsed.purpose)}</span>` : "",
    parsed.deployment_context ? `<span class="ctx-chip ctx-context">${escapeHtml(parsed.deployment_context)}</span>` : "",
    parsed.jurisdiction       ? `<span class="ctx-chip ctx-jur">${escapeHtml(parsed.jurisdiction)}</span>` : "",
  ].filter(Boolean).join("");
  const parsedRow = ctxChips ? `<div class="parsed-context">${ctxChips}</div>` : "";

  const conditionsHtml = conditions.length > 0
    ? `<div class="conditions-section">
         <div class="conditions-label">Required conditions</div>
         <ol class="conditions-list">
           ${conditions.map((c) => `<li><span class="cond-dot">▸</span>${escapeHtml(c)}</li>`).join("")}
         </ol>
       </div>`
    : "";

  const tab1 = `
    ${parsedRow}
    <div class="reasoning-label">Reasoning</div>
    <p class="reasoning-text">${escapeHtml(v.reasoning || "").replace(/\n/g, "<br>")}</p>
    ${conditionsHtml}`;

  // — Tab 2: Citations —
  const tab2 = rules.length > 0
    ? `<div class="grounding-summary" data-grounding="${cid}"></div>
       <div class="citation-grid">
         ${rules.map((r) => {
           const { reg, art } = parseRule(r);
           const gkey = groundingKey(reg, art);
           return `<div class="citation-row" data-gkey="${escapeHtml(gkey)}">
                     <span class="citation-reg">${escapeHtml(reg)}</span>
                     <span class="citation-art">${escapeHtml(art || reg)}</span>
                     <span class="citation-ground"></span>
                   </div>`;
         }).join("")}
       </div>`
    : `<div class="citation-empty">No specific provisions were cited for this response.</div>`;

  // — Tab 3: Evidence (graph edges actually traversed) —
  // This is the provenance view: the subject→predicate→object edges the
  // knowledge graph returned for this question, with the article each rests on
  // and its extraction confidence. Unlike Citations (what the LLM cited),
  // this is what the graph supplied — the two can be cross-checked (Phase 5).
  const edges = (evidence && evidence.edges) || [];
  const evCounts = (evidence && evidence.counts) || {};
  const passages = (evidence && evidence.passages) || [];
  const tab3 = (edges.length > 0 || passages.length > 0)
    ? `<div class="evidence-meta">
         ${evCounts.edges || edges.length} edges ·
         ${evCounts.passages || passages.length} passages ·
         ${evCounts.regulations || 0} regulations
       </div>
       ${edges.length > 0 ? `
       <div class="evidence-section-label">Graph edges traversed</div>
       <div class="evidence-grid">
         ${edges.map((e) => {
           const conf = e.confidence != null ? Math.round(e.confidence * 100) : null;
           const flags = [
             e.typed      ? `<span class="ev-flag ev-typed" title="Both nodes ontology-typed">typed</span>` : "",
             e.bridge     ? `<span class="ev-flag ev-bridge" title="Reached via cross-regulation bridge hop">bridge</span>` : "",
             e.deontic    ? `<span class="ev-flag ev-deontic">${escapeHtml(e.deontic)}</span>` : "",
           ].filter(Boolean).join("");
           return `<div class="evidence-row">
                     <div class="ev-triple">
                       <span class="ev-node">${escapeHtml(e.subject || "")}</span>
                       <span class="ev-pred">${escapeHtml(e.predicate || "")}</span>
                       <span class="ev-node">${escapeHtml(e.object || "")}</span>
                     </div>
                     <div class="ev-src">
                       <span class="ev-cite">${escapeHtml(e.citation || e.article_id || "")}</span>
                       ${conf != null ? `<span class="ev-conf">${conf}%</span>` : ""}
                       ${flags}
                     </div>
                   </div>`;
         }).join("")}
       </div>` : ""}
       ${passages.length > 0 ? `
       <div class="evidence-section-label">Retrieved passages${
         (evCounts.passages && evCounts.passages > passages.length)
           ? ` <span class="ev-shown">showing ${passages.length} of ${evCounts.passages}, closest first</span>`
           : ``
       }</div>
       <div class="evidence-grid">
         ${passages.map((p) => {
           const dist = p.distance != null ? p.distance.toFixed(2) : null;
           return `<div class="evidence-row ev-passage">
                     <span class="ev-cite">${escapeHtml(p.citation || p.chunk_id || "")}</span>
                     ${dist != null ? `<span class="ev-dist" title="vector distance (lower = closer)">dist ${dist}</span>` : ""}
                   </div>`;
         }).join("")}
       </div>` : ""}`
    : `<div class="citation-empty">No evidence was retrieved for this response.</div>`;

  wrap.innerHTML = `
    <div class="verdict-card">
      <div class="verdict-head">
        <span class="verdict-badge ${verdictClass(v.verdict)}">${escapeHtml(v.verdict)}</span>
        <div class="confidence-gauge">
          <div class="gauge-track">
            <div class="gauge-fill" style="width:${conf}%;background:${gaugeColor(conf)}"></div>
          </div>
          <span class="confidence-num">Confidence <b>${conf}%</b></span>
        </div>
      </div>
      <div class="tabs">
        <button class="tab active" data-tab="${cid}-1">Verdict</button>
        <button class="tab" data-tab="${cid}-2">Citations<span class="tab-count">${rules.length}</span></button>
        <button class="tab" data-tab="${cid}-3">Evidence<span class="tab-count">${edges.length}</span></button>
      </div>
      <div class="tab-panel active" id="${cid}-1">${tab1}</div>
      <div class="tab-panel" id="${cid}-2">${tab2}</div>
      <div class="tab-panel" id="${cid}-3">${tab3}</div>
    </div>`;

  // Tab switching
  wrap.querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => {
      wrap.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      wrap.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.tab).classList.add("active");
    };
  });

  // Feedback row
  const fb = document.createElement("div");
  fb.className = "feedback-row";
  fb.innerHTML = `
    <span class="feedback-label">Was this verdict correct?</span>
    <button class="fb-btn" data-r="1">👍</button>
    <button class="fb-btn" data-r="-1">👎</button>`;
  fb.querySelectorAll(".fb-btn").forEach((b) => {
    b.onclick = async () => {
      try {
        await api("/feedback", { method: "POST", body: JSON.stringify({
          session_id: activeSessionId, question: lastQuestion,
          verdict: v.verdict, rating: Number(b.dataset.r), notes: "",
        })});
      } catch (e) { console.warn("Feedback failed:", e.message); }
      fb.querySelector(".feedback-label").textContent = "Recorded. Thank you.";
      fb.querySelectorAll(".fb-btn").forEach((btn) => btn.disabled = true);
    };
  });
  wrap.querySelector(".verdict-card").appendChild(fb);

  els.messages.appendChild(wrap);
}

// ── Shared ───────────────────────────────────────────────────────────────────
function renderUserMessage(text) {
  const div = document.createElement("div");
  div.className = "msg-user";
  div.textContent = text;
  els.messages.appendChild(div);
}
function clearMessages()  { els.messages.innerHTML = ""; }
function scrollToBottom() { els.messages.scrollTop = els.messages.scrollHeight; }
function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

// ── Session list ─────────────────────────────────────────────────────────────
async function refreshSessions() {
  const sessions = await listSessions();
  els.sessionList.innerHTML = "";
  sessions.forEach((s) => {
    const li = document.createElement("li");
    li.className = "session-item" + (s.id === activeSessionId ? " active" : "");
    li.textContent = s.title;
    li.title = s.title;
    li.onclick = () => loadSession(s.id, s.title);
    els.sessionList.appendChild(li);
  });
}

async function loadSession(id, title) {
  activeSessionId = id;
  localStorage.setItem("shield_session_id", id);
  els.activeTitle.textContent = title || "Consultation";
  await refreshSessions();
  clearMessages();
  const history = await getHistory(id);
  history.messages.forEach((m) => {
    if (m.role === "user")  renderUserMessage(m.content);
    else if (m.verdict)     renderAssistantResponse(m.verdict);
  });
  scrollToBottom();
}

// ── Streaming send ───────────────────────────────────────────────────────────
const STEP_ORDER = ["routing", "routed", "retrieving", "synthesizing"];

async function submitQuestion() {
  const question = els.question.value.trim();
  if (!question) return;

  lastQuestion = question;
  els.send.disabled = true;
  els.question.value = "";
  els.question.style.height = "auto";

  if (els.messages.querySelector(".empty-state")) clearMessages();
  renderUserMessage(question);

  // Live step panel
  const stepPanel = document.createElement("div");
  stepPanel.className = "stream-steps";
  els.messages.appendChild(stepPanel);
  scrollToBottom();

  const stepEls = {};
  // Holds the `evidence` frame (arrives before the verdict) so renderVerdict
  // can attach it as the Evidence/Provenance tab when the verdict lands.
  let pendingEvidence = null;
  function setStep(stage, label, state) {
    if (!stepEls[stage]) {
      const el = document.createElement("div");
      el.className = "stream-step active";
      el.innerHTML = `<span class="dot"></span><span class="step-label">${escapeHtml(label)}</span>`;
      stepPanel.appendChild(el);
      stepEls[stage] = el;
      // mark previous steps done
      Object.keys(stepEls).forEach((k) => {
        if (k !== stage) { stepEls[k].classList.remove("active"); stepEls[k].classList.add("done"); }
      });
    } else if (label) {
      stepEls[stage].querySelector(".step-label").textContent = label;
    }
    if (state === "done") { stepEls[stage].classList.remove("active"); stepEls[stage].classList.add("done"); }
    scrollToBottom();
  }

  try {
    const res = await fetch(`${API_BASE}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: activeSessionId }),
    });
    if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse complete SSE frames (separated by blank line)
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        handleFrame(frame);
      }
    }

    function handleFrame(frame) {
      let event = "message", data = "";
      frame.split("\n").forEach((line) => {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      });
      if (!data) return;
      let payload;
      try { payload = JSON.parse(data); } catch { return; }

      if (event === "session") {
        if (payload.session_id !== activeSessionId) {
          activeSessionId = payload.session_id;
          localStorage.setItem("shield_session_id", payload.session_id);
        }
      } else if (event === "step") {
        setStep(payload.stage, payload.label);
      } else if (event === "evidence") {
        // Arrives before the verdict; stash it and show a lightweight live
        // count on the retrieving step so the user sees the graph did work.
        pendingEvidence = payload;
        const c = payload.counts || {};
        if (stepEls["retrieving"]) {
          stepEls["retrieving"].querySelector(".step-label").textContent =
            `Retrieved ${c.edges || 0} graph edges · ${c.passages || 0} passages`;
        }
      } else if (event === "grounding") {
        // Arrives after the verdict card is already rendered. Attach the
        // grounding badges to the citation rows that were just drawn.
        applyGrounding(payload);
      } else if (event === "verdict") {
        // mark all steps done, remove panel, render card
        Object.values(stepEls).forEach((el) => {
          el.classList.remove("active"); el.classList.add("done");
        });
        setTimeout(() => stepPanel.remove(), 150);
        renderAssistantResponse(payload, pendingEvidence);
        els.activeTitle.textContent = question.slice(0, 60);
        refreshSessions();
      } else if (event === "error") {
        stepPanel.remove();
        const err = document.createElement("div");
        err.className = "msg-assistant thinking";
        err.textContent = `Error: ${payload.detail}`;
        els.messages.appendChild(err);
      }
    }
  } catch (e) {
    stepPanel.remove();
    const err = document.createElement("div");
    err.className = "msg-assistant thinking";
    err.textContent = `Error: ${e.message}. Is the backend running?`;
    els.messages.appendChild(err);
  } finally {
    els.send.disabled = false;
    scrollToBottom();
  }
}

// ── Events ───────────────────────────────────────────────────────────────────
els.send.onclick = submitQuestion;
els.question.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitQuestion(); }
});
els.question.addEventListener("input", () => {
  els.question.style.height = "auto";
  els.question.style.height = Math.min(els.question.scrollHeight, 140) + "px";
});
els.newSession.onclick = () => {
  activeSessionId = null;
  localStorage.removeItem("shield_session_id");
  els.activeTitle.textContent = "New consultation";
  clearMessages();
  els.messages.innerHTML = `
    <div class="empty-state">
      <div class="empty-seal">§</div>
      <h1>Regulatory verdicts, with the articles to back them.</h1>
      <p>Describe an activity or ask about a rule. KEP_FALL returns a verdict,
         the exact provisions it relied on, and the conditions that apply.</p>
      <div class="examples">
        <button class="example">Can my elderly-care assistant store fall-risk predictions and share them with caregivers?</button>
        <button class="example">Can my diagnostic AI device store patient clinical data and share it with hospitals?</button>
        <button class="example">What criteria determine whether an AI system is high-risk?</button>
      </div>
    </div>`;
  bindExamples();
  refreshSessions();
};

function bindExamples() {
  document.querySelectorAll(".example").forEach((b) => {
    b.onclick = () => { els.question.value = b.textContent; submitQuestion(); };
  });
}

// ── Init ─────────────────────────────────────────────────────────────────────
(async function init() {
  bindExamples();
  try {
    await refreshSessions();
    if (activeSessionId) {
      const sessions = await listSessions();
      const s = sessions.find((x) => x.id === activeSessionId);
      if (s) await loadSession(s.id, s.title);
    }
  } catch (e) {
    console.warn("Backend not reachable yet:", e.message);
  }
})();