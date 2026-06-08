const chatVenster  = document.getElementById("chatVenster");
const invoerVeld   = document.getElementById("invoerVeld");
const verstuurKnop = document.getElementById("verstuurKnop");
const sessieLijst  = document.getElementById("sessieLijst");
const zijbalk      = document.getElementById("zijbalk");

// Actieve handleiding-filter (null = geen filter)
let huidigFilter = null;

// Bekende handleiding-namen voor autocomplete
let alleHandleidingNamen = [];
let autocompleteIndex = -1;

// ── Zijbalk ───────────────────────────────────────────────────────────────────
const menuKnop = document.getElementById("menuKnop");

function toggleZijbalk() {
  zijbalk.classList.toggle("dicht");
  menuKnop.classList.toggle("dicht");
}

// ── Sessie-opslag ─────────────────────────────────────────────────────────────
const OPSLAG_SLEUTEL   = "hlc_sessies";
const MAX_SESSIES      = 20;
const NIEUWE_SESSIE_MS = 2 * 60 * 60 * 1000;

function getSessies() {
  try { return JSON.parse(localStorage.getItem(OPSLAG_SLEUTEL) || "[]"); }
  catch { return []; }
}

function saveSessies(sessies) {
  localStorage.setItem(OPSLAG_SLEUTEL, JSON.stringify(sessies));
}

function initialiseerSessie() {
  const sessies = getSessies();
  const nu = Date.now();
  if (sessies.length > 0) {
    const laatste = sessies[sessies.length - 1];
    if ((nu - (laatste.laatste_activiteit || laatste.gestart)) < NIEUWE_SESSIE_MS && laatste.berichten.length > 0) {
      return;
    }
  }
  const nieuw = { id: nu.toString(), gestart: nu, laatste_activiteit: nu, berichten: [] };
  sessies.push(nieuw);
  if (sessies.length > MAX_SESSIES) sessies.splice(0, sessies.length - MAX_SESSIES);
  saveSessies(sessies);
}

function slaBerichtOp(tekst, rol, secties = []) {
  const sessies = getSessies();
  if (!sessies.length) return;
  const idx = sessies.length - 1;
  if (rol === "gebruiker" && !sessies[idx].titel) {
    sessies[idx].titel = tekst;
  }
  sessies[idx].berichten.push({ tekst, rol, secties });
  sessies[idx].laatste_activiteit = Date.now();
  sessies[idx].filter = huidigFilter;
  saveSessies(sessies);
  renderSessieLijst();
}

function laadHuidigeSessie() {
  const sessies = getSessies();
  if (!sessies.length) return;
  const sessie = sessies[sessies.length - 1];
  if (!sessie.berichten.length) return;

  huidigFilter = sessie.filter || null;

  const welkom = chatVenster.querySelector(".welkom-bericht");
  if (welkom) welkom.remove();

  sessie.berichten.forEach(({ tekst, rol, secties }) => {
    const inhoud = _renderBericht(tekst, rol);
    _renderBronnen(inhoud, secties);
  });
}

// ── Sessielijst ───────────────────────────────────────────────────────────────
function renderSessieLijst() {
  const alleSessies = getSessies();
  const huidigId = alleSessies[alleSessies.length - 1]?.id;
  const sessies = alleSessies
    .filter(s => s.berichten.length > 0)
    .sort((a, b) => b.gestart - a.gestart);

  sessieLijst.innerHTML = "";

  if (!sessies.length) {
    sessieLijst.innerHTML = '<div class="sessie-leeg">Nog geen eerdere gesprekken.</div>';
    return;
  }

  sessies.forEach((sessie) => {
    const isHuidig = sessie.id === huidigId;

    const item = document.createElement("div");
    item.className = "sessie-item" + (isHuidig ? " actief" : "");

    const datum = new Date(sessie.gestart);
    const datumTekst = datum.toLocaleDateString("nl-NL", {
      day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });

    item.innerHTML = `
      <div class="sessie-tekst">
        <div class="sessie-preview">
          <span class="sessie-naam">${sessie.titel || "Gesprek"}</span>
        </div>
        <div class="sessie-datum">${datumTekst}</div>
      </div>
      <div class="sessie-menu-wrap">
        <button class="sessie-dots" title="Opties" onclick="toggleSessieMenu(event, '${sessie.id}')">
          <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14">
            <circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/>
          </svg>
        </button>
        <div class="sessie-dropdown" id="menu-${sessie.id}">
          <button onclick="hernoemSessie(event, '${sessie.id}')">Naam wijzigen</button>
          <button class="verwijder" onclick="verwijderSessie(event, '${sessie.id}')">Verwijderen</button>
        </div>
      </div>
    `;

    item.querySelector(".sessie-tekst").onclick = () => laadSessie(sessie.id);
    sessieLijst.appendChild(item);
  });
}

function toggleSessieMenu(e, id) {
  e.stopPropagation();
  // sluit alle andere menus
  document.querySelectorAll(".sessie-dropdown.open").forEach(d => {
    if (d.id !== `menu-${id}`) d.classList.remove("open");
  });
  document.getElementById(`menu-${id}`)?.classList.toggle("open");
}

function hernoemSessie(e, id) {
  e.stopPropagation();
  document.getElementById(`menu-${id}`)?.classList.remove("open");

  const item = e.target.closest(".sessie-item");
  const naamEl = item?.querySelector(".sessie-naam");
  if (!naamEl) return;

  const huidig = naamEl.textContent.trim();
  const input = document.createElement("input");
  input.className = "sessie-naam-input";
  input.value = huidig;
  naamEl.replaceWith(input);
  input.focus();
  input.select();

  function opslaan() {
    const nieuw = input.value.trim() || huidig;
    const sessies = getSessies();
    const sessie = sessies.find(s => s.id === id);
    if (sessie) { sessie.titel = nieuw; saveSessies(sessies); }
    renderSessieLijst();
  }

  input.onblur = opslaan;
  input.onkeydown = (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); input.blur(); }
    if (ev.key === "Escape") { input.value = huidig; input.blur(); }
  };
}

function verwijderSessie(e, id) {
  e.stopPropagation();
  document.getElementById(`menu-${id}`)?.classList.remove("open");

  const sessies = getSessies().filter(s => s.id !== id);
  saveSessies(sessies);

  // als de verwijderde sessie de actieve was, start nieuw gesprek
  const actief = getSessies();
  if (!actief.length || actief[actief.length - 1]?.id === id) {
    nieuwGesprek();
  } else {
    renderSessieLijst();
  }
}

// sluit menu bij klik buiten
document.addEventListener("click", () => {
  document.querySelectorAll(".sessie-dropdown.open").forEach(d => d.classList.remove("open"));
});

function laadSessie(id) {
  const sessies = getSessies();
  const idx = sessies.findIndex(s => s.id === id);
  if (idx === -1) return;

  const sessie = sessies.splice(idx, 1)[0];
  sessies.push(sessie);
  saveSessies(sessies);

  huidigFilter = sessie.filter || null;

  chatVenster.innerHTML = "";
  sessie.berichten.forEach(({ tekst, rol, secties }) => {
    const inhoud = _renderBericht(tekst, rol);
    _renderBronnen(inhoud, secties);
  });

  renderSessieLijst();
  scrollNaarOnderen();
  invoerVeld.focus();
}

function nieuwGesprek() {
  const sessies = getSessies();
  const nu = Date.now();
  sessies.push({ id: nu.toString(), gestart: nu, laatste_activiteit: nu, berichten: [] });
  if (sessies.length > MAX_SESSIES) sessies.splice(0, sessies.length - MAX_SESSIES);
  saveSessies(sessies);

  huidigFilter = null;

  chatVenster.innerHTML = `
    <div class="welkom-bericht">
      <div class="welkom-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
        </svg>
      </div>
      <h2>Welkom bij HandleidingChat</h2>
      <p>Kies een apparaat of stel direct uw vraag.</p>
      <div class="chip-rij" id="startChips"></div>
    </div>
  `;

  stuurWelkomBericht();
  renderSessieLijst();
  invoerVeld.focus();
}

// ── Chat renderen ─────────────────────────────────────────────────────────────
function scrollNaarOnderen() {
  chatVenster.scrollTop = chatVenster.scrollHeight;
}

function _renderBericht(tekst, rol) {
  const rij = document.createElement("div");
  rij.className = `bericht-rij ${rol}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = rol === "gebruiker" ? "U" : "B";

  const inhoud = document.createElement("div");
  inhoud.className = "bericht-inhoud";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = marked.parse(tekst);

  inhoud.appendChild(bubble);

  if (rol === "bot") {
    const aiLabel = document.createElement("span");
    aiLabel.className = "ai-label";
    aiLabel.title = "AI-gegenereerd";
    aiLabel.setAttribute("aria-label", "AI-gegenereerd");
    aiLabel.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M12 2l1.9 5.3a5 5 0 0 0 2.8 2.8L22 12l-5.3 1.9a5 5 0 0 0-2.8 2.8L12 22l-1.9-5.3a5 5 0 0 0-2.8-2.8L2 12l5.3-1.9a5 5 0 0 0 2.8-2.8L12 2z"/><path d="M19 3l.6 1.6A2 2 0 0 0 20.4 5.4L22 6l-1.6.6a2 2 0 0 0-1.4 1.4L19 9l-.6-1.6a2 2 0 0 0-1.4-1.4L15 6l1.6-.6a2 2 0 0 0 1.4-1.4L19 3z"/></svg>`;
    bubble.insertBefore(aiLabel, bubble.firstChild);
  }

  rij.appendChild(avatar);
  rij.appendChild(inhoud);
  chatVenster.appendChild(rij);
  scrollNaarOnderen();
  return inhoud;
}

function _renderOpties(inhoud, opties) {
  if (!opties || !opties.length) return;
  const rij = document.createElement("div");
  rij.className = "chip-rij opties-rij";
  opties.forEach(opt => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = opt.replace(/\s*users\s*manual\s*$/i, "").trim() || opt;
    chip.onclick = () => stuurVoorbeeldVraag(opt);
    rij.appendChild(chip);
  });
  inhoud.appendChild(rij);
  scrollNaarOnderen();
}

const _docIcoon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>';

function _renderBronnen(inhoud, secties) {
  if (!secties || !secties.length) return;

  // dedupliceer op bestand + pagina zodat dezelfde bron niet dubbel verschijnt
  const gezien = new Set();
  const bronnen = [];
  for (const s of secties) {
    if (!s.bron) continue;
    const sleutel = `${s.bestand || s.bron}#${s.pagina || ""}`;
    if (gezien.has(sleutel)) continue;
    gezien.add(sleutel);
    bronnen.push(s);
  }
  if (!bronnen.length) return;

  const balk = document.createElement("div");
  balk.className = "bron-balk";

  const label = document.createElement("span");
  label.className = "bron-label";
  label.textContent = bronnen.length > 1 ? "Bronnen:" : "Bron:";
  balk.appendChild(label);

  bronnen.forEach((s) => {
    const isPdf = s.bestand && s.bestand.toLowerCase().endsWith(".pdf");
    const paginaTekst = s.pagina ? ` · p. ${s.pagina}` : "";
    if (isPdf) {
      const pagina = s.pagina ? `#page=${s.pagina}` : "";
      const link = document.createElement("a");
      link.className = "bron-knop";
      link.href = `/handleidingen/${encodeURIComponent(s.bestand)}${pagina}`;
      link.target = "_blank";
      link.title = "Open in de handleiding";
      link.innerHTML = `${_docIcoon}<span>${s.bron}${paginaTekst}</span>`;
      balk.appendChild(link);
    } else {
      const span = document.createElement("span");
      span.className = "bron-knop statisch";
      span.innerHTML = `${_docIcoon}<span>${s.bron}${paginaTekst}</span>`;
      balk.appendChild(span);
    }
  });

  inhoud.appendChild(balk);
  scrollNaarOnderen();
}

// Fasen die de gebruiker te zien krijgt terwijl op het antwoord wordt gewacht.
// De backend antwoordt in één keer (geen streaming), dus deze lopen op een timer
// en geven een indicatie van wat er ongeveer gebeurt. Per fase een eigen duur (ms):
// later wat langzamer, zodat het niet meteen op de laatste fase vastloopt.
const TYP_FASEN = [
  { tekst: "Zoeken in de handleiding…",        duur: 2200 },
  { tekst: "Relevante secties analyseren…",    duur: 3000 },
  { tekst: "Nadenken over uw vraag…",          duur: 3800 },
  { tekst: "Antwoord opstellen…",              duur: null }, // laatste: blijft staan
];
let _typFaseTimer = null;

function toonTypIndicator() {
  const rij = document.createElement("div");
  rij.className = "bericht-rij bot";
  rij.id = "typIndicator";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "B";

  const inhoud = document.createElement("div");
  inhoud.className = "bericht-inhoud";
  inhoud.innerHTML = `<div class="typ-indicator"><span class="typ-status">${TYP_FASEN[0].tekst}</span></div>`;

  rij.appendChild(avatar);
  rij.appendChild(inhoud);
  chatVenster.appendChild(rij);
  scrollNaarOnderen();

  // Plan elke volgende fase in op basis van de duur van de vorige.
  let i = 0;
  const volgendeFase = () => {
    if (i >= TYP_FASEN.length - 1) return; // laatste fase blijft staan
    i++;
    const status = document.querySelector("#typIndicator .typ-status");
    if (status) status.textContent = TYP_FASEN[i].tekst;
    if (TYP_FASEN[i].duur !== null) {
      _typFaseTimer = setTimeout(volgendeFase, TYP_FASEN[i].duur);
    }
  };
  _typFaseTimer = setTimeout(volgendeFase, TYP_FASEN[0].duur);
}

function verwijderTypIndicator() {
  if (_typFaseTimer) {
    clearTimeout(_typFaseTimer);
    _typFaseTimer = null;
  }
  const el = document.getElementById("typIndicator");
  if (el) el.remove();
}

function setLaadStatus(laden) {
  invoerVeld.disabled = laden;
  verstuurKnop.disabled = laden;
  if (!laden) invoerVeld.focus();
}

// ── Versturen ─────────────────────────────────────────────────────────────────
async function verstuurBericht() {
  const tekst = invoerVeld.value.trim();
  if (!tekst) return;

  invoerVeld.value = "";
  invoerVeld.style.height = "auto";
  _renderBericht(tekst, "gebruiker");
  slaBerichtOp(tekst, "gebruiker");
  setLaadStatus(true);
  toonTypIndicator();

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tekst, filter: huidigFilter }),
    });
    if (!response.ok) throw new Error();
    const data = await response.json();

    verwijderTypIndicator();

    if (data.set_filter !== undefined && data.set_filter !== null) {
      huidigFilter = data.set_filter.length > 0 ? data.set_filter : null;
    }
    const botInhoud = _renderBericht(data.tekst, "bot");
    slaBerichtOp(data.tekst, "bot", data.secties);  // slaat ook huidigFilter op
    _renderBronnen(botInhoud, data.secties);
    _renderOpties(botInhoud, data.opties);
  } catch {
    verwijderTypIndicator();
    _renderBericht("Er ging iets mis. Probeer het opnieuw.", "bot");
  }

  setLaadStatus(false);
}

function stuurVoorbeeldVraag(vraag) {
  invoerVeld.value = vraag;
  verstuurBericht();
}

async function laadHandleidingNamen() {
  try {
    const res = await fetch("/handleidingen-lijst");
    const data = await res.json();
    alleHandleidingNamen = (data.handleidingen || []).map(h => h.naam);
  } catch {
    alleHandleidingNamen = [];
  }
}

async function stuurWelkomBericht() {
  await laadHandleidingNamen();

  const welkomTekst = "Welkom! Voor welke handleiding kan ik u helpen?";
  const botInhoud = _renderBericht(welkomTekst, "bot");
  _renderOpties(botInhoud, alleHandleidingNamen);
}

// ── Autocomplete ──────────────────────────────────────────────────────────────
function toonAutocomplete(waarde) {
  const dropdown = document.getElementById("autocompleteDropdown");
  if (!dropdown) return;

  if (!waarde.trim() || huidigFilter) {
    dropdown.innerHTML = "";
    dropdown.classList.remove("open");
    autocompleteIndex = -1;
    return;
  }

  const zoek = waarde.toLowerCase();
  const matches = alleHandleidingNamen.filter(n => n.toLowerCase().includes(zoek));

  if (!matches.length) {
    dropdown.innerHTML = "";
    dropdown.classList.remove("open");
    autocompleteIndex = -1;
    return;
  }

  dropdown.innerHTML = "";
  autocompleteIndex = -1;
  matches.forEach((naam) => {
    const item = document.createElement("div");
    item.className = "autocomplete-item";
    // Vetgedrukt de getypte deel
    const idx = naam.toLowerCase().indexOf(zoek);
    item.innerHTML = naam.slice(0, idx)
      + "<strong>" + naam.slice(idx, idx + waarde.length) + "</strong>"
      + naam.slice(idx + waarde.length);
    item.addEventListener("mousedown", (e) => {
      e.preventDefault(); // voorkom blur vóór click
      sluitAutocomplete();
      stuurVoorbeeldVraag(naam);
    });
    dropdown.appendChild(item);
  });

  dropdown.classList.add("open");
}

function sluitAutocomplete() {
  const dropdown = document.getElementById("autocompleteDropdown");
  if (dropdown) { dropdown.innerHTML = ""; dropdown.classList.remove("open"); }
  autocompleteIndex = -1;
}

function behandelInvoerToets(e) {
  const dropdown = document.getElementById("autocompleteDropdown");
  const items = dropdown ? dropdown.querySelectorAll(".autocomplete-item") : [];

  if (e.key === "ArrowDown") {
    e.preventDefault();
    autocompleteIndex = Math.min(autocompleteIndex + 1, items.length - 1);
    items.forEach((el, i) => el.classList.toggle("actief", i === autocompleteIndex));
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    autocompleteIndex = Math.max(autocompleteIndex - 1, -1);
    items.forEach((el, i) => el.classList.toggle("actief", i === autocompleteIndex));
  } else if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (autocompleteIndex >= 0 && items[autocompleteIndex]) {
      const naam = alleHandleidingNamen.find(n =>
        items[autocompleteIndex].textContent === n
      );
      sluitAutocomplete();
      if (naam) { stuurVoorbeeldVraag(naam); return; }
    }
    verstuurBericht();
  } else if (e.key === "Escape") {
    sluitAutocomplete();
  }
}

// ── Auto-resize textarea ──────────────────────────────────────────────────────
function resizeInvoer() {
  invoerVeld.style.height = "auto";
  invoerVeld.style.height = Math.min(invoerVeld.scrollHeight, 68) + "px";
}

invoerVeld.addEventListener("input", () => {
  resizeInvoer();
  toonAutocomplete(invoerVeld.value);
});

invoerVeld.addEventListener("blur", () => {
  setTimeout(sluitAutocomplete, 150);
});

// ── Init ──────────────────────────────────────────────────────────────────────
initialiseerSessie();
const _heeftBestaandeSessie = (() => {
  const s = getSessies();
  return s.length > 0 && s[s.length - 1].berichten.length > 0;
})();
laadHuidigeSessie();
renderSessieLijst();
if (!_heeftBestaandeSessie) {
  stuurWelkomBericht();
} else {
  laadHandleidingNamen();
}
invoerVeld.focus();
