// ============================================================================
// admin.js — frontend van de adminpagina (admin.html)
//
// Vanilla JavaScript. Twee taken:
// 1. LLM-instellingen: het formulier vullen vanuit GET /admin/settings en
//    wijzigingen opslaan via POST /admin/settings (de backend valideert en
//    begrenst de waarden, en geeft de genormaliseerde versie terug).
// 2. Testset-runner: de testvragen ophalen (GET /admin/testset) en stuk voor
//    stuk draaien (POST /admin/test-een), met een live samenvatting en per vraag
//    een oordeel (goed/deels/mis) + ontbrekende sleutelwoorden.
// ============================================================================

// Velden die als getal/tekst direct uit de inputs worden gelezen
const NUMERIEKE_VELDEN = [
  "temperature", "top_p", "top_k", "repeat_penalty",
  "num_predict", "num_ctx", "seed",
  "top_n", "bronnen_tonen", "drempel_globaal", "drempel_filter",
];
const SLIDERS = ["temperature", "top_p", "top_k", "repeat_penalty"];

const $ = (id) => document.getElementById(id);

// Onthoudt of er een Gemini-API-key in de omgeving (.env) gevonden is.
let geminiBeschikbaar = false;

// ── Laden ──────────────────────────────────────────────────────────────────
async function init() {
  await Promise.all([laadModellen(), laadInstellingen()]);
  SLIDERS.forEach((id) => {
    $(id).addEventListener("input", () => updateSliderUit(id));
  });
  $("provider").addEventListener("change", updateProviderUI);
}

// Toon de relevante velden (Ollama-model of Gemini-model) bij de gekozen provider
// en waarschuw als Gemini is gekozen zonder dat er een API-key gevonden is.
function updateProviderUI() {
  const provider = $("provider").value;
  $("model_veld").style.display = provider === "ollama" ? "" : "none";
  $("gemini_model_veld").style.display = provider === "gemini" ? "" : "none";

  const hint = $("provider_hint");
  if (provider === "gemini" && !geminiBeschikbaar) {
    hint.textContent = "⚠️ Geen GEMINI_API_KEY gevonden in .env — Gemini geeft een foutmelding tot de key is ingesteld.";
    hint.className = "veld-hint waarschuwing";
  } else if (provider === "gemini") {
    hint.textContent = "✓ Gemini-API-key gevonden in .env.";
    hint.className = "veld-hint ok";
  } else {
    hint.textContent = "Lokaal model via Ollama. Geen API-key nodig.";
    hint.className = "veld-hint";
  }
}

function updateSliderUit(id) {
  $(id + "_uit").textContent = parseFloat($(id).value).toFixed(
    id === "top_k" ? 0 : 2
  );
}

async function laadModellen() {
  const sel = $("model");
  try {
    const res = await fetch("/admin/models");
    const data = await res.json();
    sel.innerHTML = "";
    (data.models || []).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      sel.appendChild(opt);
    });
    if (!(data.models || []).length) {
      sel.innerHTML = '<option value="">(geen modellen gevonden)</option>';
    }

    // Gemini: beschikbaarheid onthouden + de modelsuggesties vullen
    geminiBeschikbaar = !!data.gemini_beschikbaar;
    const lijst = $("gemini_modellen");
    lijst.innerHTML = "";
    (data.gemini_modellen || []).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      lijst.appendChild(opt);
    });
  } catch {
    sel.innerHTML = '<option value="">(kon modellen niet laden)</option>';
  }
}

async function laadInstellingen() {
  const res = await fetch("/admin/settings");
  const inst = await res.json();
  vulFormulier(inst);
}

function vulFormulier(inst) {
  // model: voeg toe als het (nog) niet in de lijst staat
  const sel = $("model");
  if (inst.model && ![...sel.options].some((o) => o.value === inst.model)) {
    const opt = document.createElement("option");
    opt.value = inst.model;
    opt.textContent = inst.model + " (huidig)";
    sel.appendChild(opt);
  }
  sel.value = inst.model;

  if (inst.provider) $("provider").value = inst.provider;
  $("gemini_model").value = inst.gemini_model || "";

  NUMERIEKE_VELDEN.forEach((k) => { if (k in inst) $(k).value = inst[k]; });
  $("system_prompt").value = inst.system_prompt || "";
  SLIDERS.forEach(updateSliderUit);
  updateProviderUI();
}

// ── Opslaan ────────────────────────────────────────────────────────────────
function leesFormulier() {
  const payload = {
    provider: $("provider").value,
    model: $("model").value,
    gemini_model: $("gemini_model").value,
    system_prompt: $("system_prompt").value,
  };
  NUMERIEKE_VELDEN.forEach((k) => { payload[k] = $(k).value; });
  return payload;
}

async function bewaarInstellingen() {
  const status = $("bewaarStatus");
  status.textContent = "Opslaan…";
  status.className = "status";
  try {
    const res = await fetch("/admin/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(leesFormulier()),
    });
    const inst = await res.json();
    vulFormulier(inst);
    status.textContent = "✓ Opgeslagen (genormaliseerd indien nodig)";
    status.className = "status ok";
  } catch (e) {
    status.textContent = "Fout bij opslaan: " + e;
    status.className = "status fout";
  }
}

async function resetInstellingen() {
  if (!confirm("Alle instellingen terugzetten naar de standaardwaarden?")) return;
  const res = await fetch("/admin/settings/reset", { method: "POST" });
  vulFormulier(await res.json());
  const status = $("bewaarStatus");
  status.textContent = "✓ Teruggezet naar standaard";
  status.className = "status ok";
}

// ── Test runner ──────────────────────────────────────────────────────────────
async function draaiTests() {
  const knop = $("testKnop");
  const status = $("testStatus");
  const container = $("testResultaten");
  knop.disabled = true;
  container.innerHTML = "";

  let vragen = [];
  try {
    const res = await fetch("/admin/testset");
    vragen = (await res.json()).vragen || [];
  } catch (e) {
    status.textContent = "Kon testset niet laden: " + e;
    status.className = "status fout";
    knop.disabled = false;
    return;
  }

  // Samenvatting bovenaan
  const samenvatting = document.createElement("div");
  samenvatting.className = "test-samenvatting";
  container.appendChild(samenvatting);

  const telling = { goed: 0, deels: 0, mis: 0 };
  let scoreSom = 0, scoreAantal = 0;
  const updateSamenvatting = () => {
    const gem = scoreAantal ? Math.round((scoreSom / scoreAantal) * 100) : 0;
    samenvatting.innerHTML = `
      <span class="totaal">Gem. dekking: <strong>${gem}%</strong></span>
      <span class="badge goed">✓ ${telling.goed} goed</span>
      <span class="badge deels">~ ${telling.deels} deels</span>
      <span class="badge mis">✗ ${telling.mis} mis</span>`;
  };
  updateSamenvatting();

  for (let i = 0; i < vragen.length; i++) {
    status.innerHTML = `<span class="spinner"></span> Vraag ${i + 1} van ${vragen.length}…`;
    status.className = "status";

    const item = vragen[i];
    const div = document.createElement("div");
    div.className = "test-item bezig";
    div.innerHTML = `<div class="test-vraag">${escapeHtml(item.vraag)}</div>
      <div class="test-kolom"><span class="spinner"></span> antwoord genereren…</div>`;
    container.appendChild(div);

    try {
      const res = await fetch("/admin/test-een", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vraag: item.vraag, verwacht: item.verwacht || "" }),
      });
      const data = await res.json();
      const oordeel = data.scoring && data.scoring.oordeel;
      if (oordeel in telling) telling[oordeel]++;
      if (data.scoring && data.scoring.score !== null) {
        scoreSom += data.scoring.score; scoreAantal++;
      }
      updateSamenvatting();
      div.className = "test-item " + (oordeel || "");
      div.innerHTML = renderResultaat(data);
    } catch (e) {
      div.className = "test-item";
      div.innerHTML = `<div class="test-vraag">${escapeHtml(item.vraag)}</div>
        <div class="status fout">Fout: ${escapeHtml(String(e))}</div>`;
    }
  }

  status.textContent = `✓ Klaar — ${vragen.length} vragen getest`;
  status.className = "status ok";
  knop.disabled = false;
}

function renderResultaat(data) {
  const bron = (data.secties || [])
    .map((s) => s.bron + (s.pagina ? `, p.${s.pagina}` : ""))
    .join(" · ");

  const sc = data.scoring || {};
  let badge = "";
  if (sc.score !== null && sc.score !== undefined) {
    const labels = { goed: "✓ goed", deels: "~ deels", mis: "✗ mis" };
    badge = `<span class="badge ${sc.oordeel}">${labels[sc.oordeel] || sc.oordeel} · ${Math.round(sc.score * 100)}%</span>`;
  } else {
    badge = `<span class="badge neutraal">geen referentie</span>`;
  }

  const gemist = (sc.gemist && sc.gemist.length)
    ? `<div class="test-gemist">Ontbrekende sleutelwoorden: ${sc.gemist.map((w) => `<code>${escapeHtml(w)}</code>`).join(" ")}</div>`
    : "";

  return `
    <div class="test-vraag">${escapeHtml(data.vraag)} ${badge}</div>
    <div class="test-kolommen">
      <div class="test-kolom verwacht">
        <div class="kop">Verwacht</div>
        <div class="inhoud">${escapeHtml(data.verwacht || "—")}</div>
      </div>
      <div class="test-kolom">
        <div class="kop">Antwoord chatbot</div>
        <div class="inhoud">${DOMPurify.sanitize(marked.parse(data.antwoord || ""))}</div>
      </div>
    </div>
    ${gemist}
    ${bron ? `<div class="test-bron">Bron: ${escapeHtml(bron)}</div>` : ""}
  `;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

init();
