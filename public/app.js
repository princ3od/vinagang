const $ = (sel) => document.querySelector(sel);
const form = $("#ask-form");
const input = $("#query");
const askBtn = $("#ask-btn");
const results = $("#results");

const SRC_MAP = { Projects: "folders", Docs: "file", Code: "code", Jira: "ticket", HR: "people", Certs: "cert" };

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function initials(name) {
  return name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3200);
}

async function ask(query) {
  askBtn.disabled = true;
  askBtn.textContent = "Thinking…";
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    render(data);
  } catch (e) {
    toast("Something went wrong: " + e.message);
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = "Ask";
  }
}

function render(data) {
  results.hidden = false;

  const skills = (data.intent?.skills || []).map((s) => `<span class="tag">${esc(s)}</span>`).join("");
  const urgency = data.intent?.urgency && data.intent.urgency !== "normal" ? `<span class="tag urgent">urgency: ${esc(data.intent.urgency)}</span>` : "";
  $("#intent").innerHTML = skills + urgency;
  $("#source-badge").textContent = data.source === "fallback" ? "· offline ranker" : "· ranked by Gemini";

  const sources = data.sources || [];
  $("#sources").innerHTML = sources
    .map((s) => `<div class="src" data-src><span>${esc(s)}</span><span class="tick">✓</span></div>`)
    .join("");
  document.querySelectorAll("[data-src]").forEach((el, i) => setTimeout(() => el.classList.add("on"), 120 * i));

  $("#experts").innerHTML = (data.experts || []).map(expertCard).join("");

  const docs = data.docs || [];
  $("#docs-label").hidden = docs.length === 0;
  $("#docs").innerHTML = docs
    .map(
      (d) =>
        `<a class="doc" href="${esc(d.url)}" target="_blank" rel="noreferrer"><span class="doc-title">${esc(d.title)}</span><span class="doc-src">${esc(d.source)}</span></a>`
    )
    .join("");

  document.querySelectorAll("[data-slack]").forEach((btn) => {
    btn.addEventListener("click", () => sendSlack(btn.dataset.name, btn.dataset.email, btn.dataset.query || input.value));
  });
}

function expertCard(e) {
  const compact = e.rank === "related";
  const badge = { primary: "Primary contact", backup: "Backup contact", related: "Also relevant" }[e.rank];
  const signals = (e.rationale || [])
    .map((r) => `<div class="signal"><span class="tag">${esc(r.source)}</span><span>${esc(r.text)}</span></div>`)
    .join("");
  const avail = `<div class="avail tone-${esc(e.availability.tone)}"><span class="dot"></span>${esc(e.availability.label)}</div>`;

  if (compact) {
    return `<div class="card compact">
      <span class="rank-badge related">${badge}</span>
      <div class="person">
        <div class="avatar">${esc(initials(e.name))}</div>
        <div class="person-main">
          <div class="person-top"><p class="name">${esc(e.name)} <span style="font-weight:400;color:var(--muted);font-size:12px">· ${esc(e.role)}</span></p><span class="score">${e.composite}</span></div>
          ${avail}
        </div>
      </div>
    </div>`;
  }

  return `<div class="card ${e.rank === "primary" ? "primary" : ""}">
    <span class="rank-badge ${esc(e.rank)}">${badge}</span>
    <div class="person">
      <div class="avatar">${esc(initials(e.name))}</div>
      <div class="person-main">
        <div class="person-top">
          <p class="name">${esc(e.name)}</p>
          <span class="score">${e.composite}<span class="calc">${e.expertise} × ${e.factor}</span></span>
        </div>
        <p class="role">${esc(e.role)} · ${esc(e.dept)}</p>
        ${avail}
      </div>
    </div>
    <div class="signals">${signals}</div>
    <div class="actions">
      <button class="btn btn-primary" data-slack data-name="${esc(e.name)}" data-email="${esc(e.email)}">Message on Slack</button>
      <button class="btn" type="button">Book 30-min</button>
      <button class="btn" type="button">Profile</button>
    </div>
  </div>`;
}

async function sendSlack(name, email, query) {
  const message = `Hi ${name.split(" ")[0]} — someone needs help with: "${query}". XpertFinder flagged you as the best available expert. Do you have ~15 min?`;
  try {
    const res = await fetch("/api/slack", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, email, message }),
    });
    const data = await res.json();
    toast(data.simulated ? `Simulated intro to ${name} (set SLACK_WEBHOOK_URL to post for real)` : `Intro to ${name} posted to Slack ✓`);
  } catch (e) {
    toast("Slack failed: " + e.message);
  }
}

form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  if (input.value.trim()) ask(input.value.trim());
});
document.querySelectorAll("#suggestions .chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.textContent;
    ask(chip.textContent);
  });
});

ask(input.value);
