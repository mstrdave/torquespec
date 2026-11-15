const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Tabs
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab, .panel").forEach((el) => el.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.tab).classList.add("active");
  });
});

// Minimal, safe markdown: escape first, then format.
function md(text) {
  const lines = esc(text).split("\n");
  let html = "", list = null;
  const inline = (s) => s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/_(.+?)_/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const line of lines) {
    const ul = line.match(/^\s*[-*] (.*)/), ol = line.match(/^\s*\d+[.)] (.*)/), h = line.match(/^#{1,4} (.*)/);
    if (ul || ol) {
      const tag = ul ? "ul" : "ol";
      if (list !== tag) { close(); html += `<${tag}>`; list = tag; }
      html += `<li>${inline((ul || ol)[1])}</li>`;
    } else {
      close();
      if (h) html += `<p><strong>${inline(h[1])}</strong></p>`;
      else if (line.trim()) html += `<p>${inline(line)}</p>`;
    }
  }
  close();
  return html;
}

// Diagnose chat
const history = [];
function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  if (role === "user") div.textContent = text; else div.innerHTML = md(text);
  $("#chat").appendChild(div);
  div.scrollIntoView({ block: "end", behavior: "smooth" });
  return div;
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#chat-input").value.trim();
  if (!text) return;
  $("#chat-input").value = "";
  $("#send").disabled = true;
  addMsg("user", text);
  history.push({ role: "user", content: text });
  const out = addMsg("assistant", "…");
  let answer = "";
  try {
    const res = await fetch("/api/diagnose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(typeof err.detail === "string" ? err.detail : `Request failed (${res.status})`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const events = buf.split("\n\n");
      buf = events.pop();
      for (const ev of events) {
        const data = ev.replace(/^data: /, "");
        if (data === "[DONE]") continue;
        const msg = JSON.parse(data);
        if (msg.error) throw new Error(msg.error);
        answer += msg.text;
        out.innerHTML = md(answer);
      }
    }
    history.push({ role: "assistant", content: answer || "(no answer)" });
  } catch (err) {
    history.pop(); // drop the unanswered user turn so roles keep alternating
    if (answer) history.push({ role: "user", content: text }, { role: "assistant", content: answer });
    out.classList.add("error");
    out.textContent = err.message;
  } finally {
    $("#send").disabled = false;
  }
});

$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chat-form").requestSubmit(); }
});

$("#reset").addEventListener("click", () => {
  history.length = 0;
  [...$("#chat").children].slice(1).forEach((el) => el.remove());
});

// Torque specs
async function loadTorque(q = "") {
  const rows = await (await fetch("/api/torque?q=" + encodeURIComponent(q))).json();
  $("#torque-body").innerHTML = rows.length ? rows.map((r) => `
    <tr>
      <td>${esc(r.component)}<span class="sys">${esc(r.system)}</span></td>
      <td class="num">${esc(r.range)} ${r.verify ? '<span class="verify">verify</span>' : ""}</td>
      <td class="num">${esc(r.nm)}</td>
      <td>${esc(r.notes)}</td>
    </tr>`).join("") : `<tr><td colspan="4">No match. Try a shorter search.</td></tr>`;
}
let t;
$("#torque-q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => loadTorque(e.target.value), 150); });

// Codes and issues
async function loadCodes() {
  const data = await (await fetch("/api/codes")).json();
  $("#code-steps").innerHTML = data.how_to_read.map((s) => `<li>${esc(s)}</li>`).join("");
  $("#code-list").innerHTML = data.codes.map((c) => `
    <div class="card"><h3><span class="code">${esc(c.code)}</span>${esc(c.circuit)}</h3><p>${esc(c.checks)}</p></div>`).join("");
}
async function loadIssues() {
  const data = await (await fetch("/api/issues")).json();
  $("#issue-list").innerHTML = data.map((i) => `
    <div class="card">
      <h3>${esc(i.title)}<span class="sev ${esc(i.severity)}">${esc(i.severity)}</span></h3>
      <p><strong>Symptoms:</strong> ${esc(i.symptoms.join(", "))}</p>
      <p><strong>Cause:</strong> ${esc(i.cause)}</p>
      <p><strong>Fix:</strong> ${esc(i.fix)}</p>
    </div>`).join("");
}

(async () => {
  const health = await (await fetch("/api/health")).json();
  if (!health.llm) { $("#llm-off").hidden = false; $("#send").disabled = true; }
  loadTorque(); loadCodes(); loadIssues();
})();
