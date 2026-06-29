/*
 * SHIELD frontend — SSE streaming + tabbed verdict panel.
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
function renderAssistantResponse(v) {
  shouldShowCard(v) ? renderVerdict(v) : renderPlainMessage(v);
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

function renderVerdict(v) {
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
    ? `<div class="citation-grid">
         ${rules.map((r) => {
           const { reg, art } = parseRule(r);
           return `<div class="citation-row">
                     <span class="citation-reg">${escapeHtml(reg)}</span>
                     <span class="citation-art">${escapeHtml(art || reg)}</span>
                   </div>`;
         }).join("")}
       </div>`
    : `<div class="citation-empty">No specific provisions were cited for this response.</div>`;

  // — Tab 3: Regulations bar chart —
  const counts = regulationCounts(rules);
  const maxCount = Math.max(1, ...Object.values(counts));
  const tab3 = Object.keys(counts).length > 0
    ? `<div class="reg-chart">
         ${Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([reg, n]) => `
           <div class="reg-bar-row">
             <span class="reg-bar-label">${escapeHtml(reg)}</span>
             <div class="reg-bar-track">
               <div class="reg-bar-fill" style="width:${(n / maxCount) * 100}%"></div>
             </div>
             <span class="reg-bar-count">${n}</span>
           </div>`).join("")}
       </div>`
    : `<div class="citation-empty">No regulations engaged for this response.</div>`;

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
        <button class="tab" data-tab="${cid}-3">Regulations<span class="tab-count">${Object.keys(counts).length}</span></button>
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
      } else if (event === "verdict") {
        // mark all steps done, remove panel, render card
        Object.values(stepEls).forEach((el) => {
          el.classList.remove("active"); el.classList.add("done");
        });
        setTimeout(() => stepPanel.remove(), 150);
        renderAssistantResponse(payload);
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
      <p>Describe an activity or ask about a rule. SHIELD returns a verdict,
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