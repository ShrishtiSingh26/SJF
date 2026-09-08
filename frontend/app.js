const API = "/api";

function $(sel) { return document.querySelector(sel); }
function $all(sel) { return Array.from(document.querySelectorAll(sel)); }

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- Theme Switcher ----
const themeToggleBtn = $("#theme-toggle");
const themes = ["light", "dark", "high-contrast"];
let currentThemeIndex = 0;

if (themeToggleBtn) {
  themeToggleBtn.addEventListener("click", () => {
    currentThemeIndex = (currentThemeIndex + 1) % themes.length;
    const nextTheme = themes[currentThemeIndex];
    document.documentElement.setAttribute("data-theme", nextTheme);
  });
}

// ---- Nav ----
function activateTab(tabName) {
  const tab = $(`.nav-item[data-tab="${tabName}"]`);
  if (!tab) return;
  $all(".nav-item").forEach((t) => t.classList.remove("active"));
  $all(".panel").forEach((p) => p.classList.remove("active"));
  tab.classList.add("active");
  $(`#panel-${tabName}`).classList.add("active");
  if (tabName === "facts") loadFacts();
  if (tabName === "relationships") loadRelationships();
  if (tabName === "cases") loadCases();
  if (tabName === "issues") loadIssues();
}

$all(".nav-item").forEach((tab) => {
  tab.addEventListener("click", () => {
    activateTab(tab.dataset.tab);
    history.replaceState(null, "", `#${tab.dataset.tab}`);
  });
});

if (location.hash) {
  activateTab(location.hash.slice(1));
}

// ---- Sidebar Stats ----
async function loadStats() {
  try {
    const [docs, facts, rels] = await Promise.all([
      fetch(`${API}/documents`).then((r) => r.json()),
      fetch(`${API}/facts`).then((r) => r.json()),
      fetch(`${API}/relationships`).then((r) => r.json()),
    ]);
    $("#stat-docs").textContent = docs.length;
    $("#stat-facts").textContent = facts.length;
    $("#stat-rels").textContent = rels.length;
  } catch (err) {
    // Stats fail gracefully
  }
}

// ---- Upload ----
const dropZone = $("#drop-zone");
const fileInput = $("#file-input");

if (dropZone && fileInput) {
  ["dragover", "dragenter"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => { e.preventDefault(); dropZone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => { e.preventDefault(); dropZone.classList.remove("dragover"); })
  );
  dropZone.addEventListener("drop", (e) => {
    if (uploadInFlight) return;
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) uploadFile(fileInput.files[0]);
  });
}

let uploadInFlight = false;

async function uploadFile(file) {
  if (uploadInFlight) return;
  uploadInFlight = true;
  dropZone.classList.add("busy");
  fileInput.disabled = true;
  const statusEl = $("#upload-status");
  statusEl.className = "status";
  statusEl.textContent = `Processing ${file.name} — extracting facts and cross-checking against the knowledge store. This can take 30-90+ seconds depending on document size; please wait for the "Done" message before switching tabs.`;
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(`${API}/documents`, { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    statusEl.className = "status success";
    statusEl.textContent = `Done: extracted ${data.facts_extracted} facts and found ${data.relationships_found} relationships from ${data.filename} (${data.page_count} pages).`;
    loadDocuments();
    loadStats();
  } catch (err) {
    statusEl.className = "status error";
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    uploadInFlight = false;
    dropZone.classList.remove("busy");
    fileInput.disabled = false;
  }
}

async function loadDocuments() {
  const docs = await fetch(`${API}/documents`).then((r) => r.json());
  const tbody = $("#documents-table tbody");
  tbody.innerHTML = docs.map((d) => `<tr><td>${d.id}</td><td>${escapeHtml(d.filename)}</td><td>${d.page_count}</td><td>${d.uploaded_at}</td></tr>`).join("");
  const docFilter = $("#facts-document-filter");
  docFilter.innerHTML = `<option value="">All documents</option>` + docs.map((d) => `<option value="${d.id}">${escapeHtml(d.filename)}</option>`).join("");
}

// ---- Facts ----
async function loadFacts() {
  const documentId = $("#facts-document-filter").value;
  const category = $("#facts-category-filter").value;
  const q = $("#facts-search").value;
  const params = new URLSearchParams();
  if (documentId) params.set("document_id", documentId);
  if (category) params.set("category", category);
  if (q) params.set("q", q);
  const facts = await fetch(`${API}/facts?${params}`).then((r) => r.json());
  const tbody = $("#facts-table tbody");
  tbody.innerHTML = facts
    .map(
      (f) =>
        `<tr data-id="${f.id}"><td>${f.id}</td><td>${escapeHtml(f.document_filename)}</td><td>${f.page}</td><td>${escapeHtml(f.category)}</td><td>${escapeHtml(f.subject)}</td><td>${escapeHtml(f.statement)}</td><td>${escapeHtml(f.value)} ${escapeHtml(f.unit || "")}</td></tr>`
    )
    .join("");
  $all("#facts-table tbody tr").forEach((tr) => tr.addEventListener("click", () => showFactDetail(tr.dataset.id)));

  const categories = await fetch(`${API}/categories`).then((r) => r.json());
  const catFilter = $("#facts-category-filter");
  const current = catFilter.value;
  catFilter.innerHTML = `<option value="">All categories</option>` + categories.map((c) => `<option value="${c}">${escapeHtml(c)}</option>`).join("");
  catFilter.value = current;
}

async function showFactDetail(id) {
  const fact = await fetch(`${API}/facts/${id}`).then((r) => r.json());
  const el = $("#fact-detail");
  el.hidden = false;
  el.innerHTML = `
    <h2>Fact #${fact.id}</h2>
    <div class="fact-detail-grid">
      <div><b>Document:</b> ${escapeHtml(fact.document_filename)} (p.${fact.page})</div>
      <div><b>Category:</b> ${escapeHtml(fact.category)}</div>
      <div><b>Subject:</b> ${escapeHtml(fact.subject)}</div>
      <div><b>Value:</b> ${escapeHtml(fact.value)} ${escapeHtml(fact.unit || "")}</div>
      <div><b>Period:</b> ${escapeHtml(fact.period || "-")}</div>
      <div><b>Confidence:</b> ${fact.confidence}</div>
    </div>
    <p><b>Statement:</b> ${escapeHtml(fact.statement)}</p>
    <p class="fact-box quote">Evidence: "${escapeHtml(fact.quote)}"</p>
    <h3>Related facts (${fact.relationships.length})</h3>
    ${fact.relationships
      .map(
        (r) => `<div class="rel-card">
          <span class="rel-badge ${r.relation_type}">${r.relation_type}</span>
          <div class="fact-box"><div class="doc">${escapeHtml(r.other_fact.document_filename)} (p.${r.other_fact.page})</div>${escapeHtml(r.other_fact.statement)}<div class="quote">"${escapeHtml(r.other_fact.quote)}"</div></div>
          <div class="explanation">${escapeHtml(r.explanation)}</div>
        </div>`
      )
      .join("") || "<p class='muted'>No cross-document relationships found yet.</p>"}
  `;
}

$("#facts-refresh").addEventListener("click", loadFacts);
$("#facts-document-filter").addEventListener("change", loadFacts);
$("#facts-category-filter").addEventListener("change", loadFacts);
$("#facts-search").addEventListener("keydown", (e) => { if (e.key === "Enter") loadFacts(); });

// ---- Relationships ----
function relCardHtml(r) {
  return `<div class="rel-card">
    <span class="rel-badge ${r.relation_type}">${r.relation_type}</span>
    <div class="fact-pair">
      <div class="fact-box"><div class="doc">${escapeHtml(r.fact_a.document_filename)} (p.${r.fact_a.page})</div>${escapeHtml(r.fact_a.statement)}<div class="quote">"${escapeHtml(r.fact_a.quote)}"</div></div>
      <div class="fact-box"><div class="doc">${escapeHtml(r.fact_b.document_filename)} (p.${r.fact_b.page})</div>${escapeHtml(r.fact_b.statement)}<div class="quote">"${escapeHtml(r.fact_b.quote)}"</div></div>
    </div>
    <div class="explanation"><b>Reasoning:</b> ${escapeHtml(r.explanation)}</div>
  </div>`;
}

async function loadRelationships() {
  const type = $("#relationship-type-filter").value;
  const params = new URLSearchParams();
  if (type) params.set("relation_type", type);
  const relationships = await fetch(`${API}/relationships?${params}`).then((r) => r.json());
  $("#relationships-list").innerHTML = relationships.map(relCardHtml).join("") || "<p class='muted'>No relationships yet — upload documents to populate the knowledge store.</p>";
}
$("#relationships-refresh").addEventListener("click", loadRelationships);
$("#relationship-type-filter").addEventListener("change", loadRelationships);

// ---- Cases ----
async function loadCases() {
  const cases = await fetch(`${API}/cases`).then((r) => r.json());
  const el = $("#cases-content");
  const section = (num, title, desc, rel) => `
    <div class="card case-block">
      <div class="case-number">${num}</div>
      <h3>${title}</h3>
      <p class="muted">${desc}</p>
      ${rel ? relCardHtml(rel) : "<p class='muted'>None found yet.</p>"}
    </div>`;
  el.innerHTML =
    section(1, "Corroborated fact", "The same underlying fact stated differently across documents.", cases.corroborated) +
    section(2, "Genuine / likely contradiction", "Facts that cannot both be true as stated.", cases.contradiction) +
    section(3, "Reconciled via context", "An apparent contradiction explained by time, scope, or units.", cases.reconciled) +
    `<div class="card case-block">
      <div class="case-number">4</div>
      <h3>Extraction or reasoning failures</h3>
      <p class="muted">Issues the system found in itself, logged rather than hidden.</p>
      ${
        cases.extraction_or_reasoning_failures.length
          ? `<table class="table"><thead><tr><th>Doc</th><th>Page</th><th>Type</th><th>Description</th></tr></thead><tbody>${cases.extraction_or_reasoning_failures
              .map((i) => `<tr><td>${i.document_id ?? "-"}</td><td>${i.page ?? "-"}</td><td>${escapeHtml(i.issue_type)}</td><td>${escapeHtml(i.description)}</td></tr>`)
              .join("")}</tbody></table>`
          : "<p class='muted'>None logged yet.</p>"
      }
    </div>`;
}
$("#cases-refresh").addEventListener("click", loadCases);

// ---- Query ----
$("#query-submit").addEventListener("click", async () => {
  const q = $("#query-input").value.trim();
  if (!q) return;
  const el = $("#query-answer");
  el.textContent = "Thinking...";
  try {
    const res = await fetch(`${API}/query?${new URLSearchParams({ q })}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Query failed");
    el.textContent = data.answer;
  } catch (err) {
    el.textContent = `Error: ${err.message}`;
  }
});
$("#query-input").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#query-submit").click(); });

// ---- Issues ----
async function loadIssues() {
  const issues = await fetch(`${API}/issues`).then((r) => r.json());
  $("#issues-table tbody").innerHTML = issues
    .map((i) => `<tr><td>${i.id}</td><td>${i.document_id ?? "-"}</td><td>${i.page ?? "-"}</td><td>${escapeHtml(i.issue_type)}</td><td>${escapeHtml(i.description)}</td></tr>`)
    .join("");
}

loadDocuments();
loadStats();