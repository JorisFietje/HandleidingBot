const chatVenster  = document.getElementById("chatVenster");
const invoerVeld   = document.getElementById("invoerVeld");
const verstuurKnop = document.getElementById("verstuurKnop");
const sessieLijst  = document.getElementById("sessieLijst");
const zijbalk      = document.getElementById("zijbalk");

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
  saveSessies(sessies);
  renderSessieLijst();
}

function laadHuidigeSessie() {
  const sessies = getSessies();
  if (!sessies.length) return;
  const sessie = sessies[sessies.length - 1];
  if (!sessie.berichten.length) return;

  const welkom = chatVenster.querySelector(".welkom-bericht");
  if (welkom) welkom.remove();

  sessie.berichten.forEach(({ tekst, rol, secties }) => {
    const inhoud = _renderBericht(tekst, rol);
    (secties || []).forEach(s => _renderSectieKaart(inhoud, s));
  });
}

// ── Sessielijst ───────────────────────────────────────────────────────────────
function renderSessieLijst() {
  const sessies = getSessies().filter(s => s.berichten.length > 0);
  sessieLijst.innerHTML = "";

  if (!sessies.length) {
    sessieLijst.innerHTML = '<div class="sessie-leeg">Nog geen eerdere gesprekken.</div>';
    return;
  }

  [...sessies].reverse().forEach((sessie) => {
    const alleSessies = getSessies();
    const isHuidig = alleSessies[alleSessies.length - 1]?.id === sessie.id;

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
          ${isHuidig ? '<span class="sessie-huidig">Nu</span>' : ""}
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

  chatVenster.innerHTML = "";
  sessie.berichten.forEach(({ tekst, rol, secties }) => {
    const inhoud = _renderBericht(tekst, rol);
    (secties || []).forEach(s => _renderSectieKaart(inhoud, s));
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

  chatVenster.innerHTML = `
    <div class="welkom-bericht">
      <div class="welkom-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
        </svg>
      </div>
      <h2>Welkom bij HandleidingChat</h2>
      <p>Stel een vraag over een van de beschikbare handleidingen.</p>
    </div>
  `;

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
  rij.appendChild(avatar);
  rij.appendChild(inhoud);
  chatVenster.appendChild(rij);
  scrollNaarOnderen();
  return inhoud;
}

function _renderSectieKaart(inhoud, sectie) {
  const kaart = document.createElement("div");
  kaart.className = "sectie-kaart";

  let bronEl;
  if (sectie.bestand && sectie.bestand.toLowerCase().endsWith(".pdf")) {
    const pagina = sectie.pagina ? `#page=${sectie.pagina}` : "";
    const paginaTekst = sectie.pagina ? ` — p. ${sectie.pagina}` : "";
    bronEl = `<a class="sectie-bron" href="/handleidingen/${encodeURIComponent(sectie.bestand)}${pagina}" target="_blank">${sectie.bron}${paginaTekst}</a>`;
  } else {
    bronEl = `<span class="sectie-bron">${sectie.bron}</span>`;
  }

  kaart.innerHTML = `
    <div class="sectie-header">
      <span class="sectie-titel">${sectie.titel}</span>
      ${bronEl}
    </div>
    <div class="sectie-body">${marked.parse(sectie.inhoud)}</div>
  `;
  inhoud.appendChild(kaart);
  scrollNaarOnderen();
}

function toonTypIndicator() {
  const rij = document.createElement("div");
  rij.className = "bericht-rij bot";
  rij.id = "typIndicator";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "B";

  const inhoud = document.createElement("div");
  inhoud.className = "bericht-inhoud";
  inhoud.innerHTML = '<div class="tik-tik"><span></span><span></span><span></span></div>';

  rij.appendChild(avatar);
  rij.appendChild(inhoud);
  chatVenster.appendChild(rij);
  scrollNaarOnderen();
}

function verwijderTypIndicator() {
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
      body: JSON.stringify({ tekst }),
    });
    if (!response.ok) throw new Error();
    const data = await response.json();
    verwijderTypIndicator();
    const botInhoud = _renderBericht(data.tekst, "bot");
    slaBerichtOp(data.tekst, "bot", data.secties);
    (data.secties || []).forEach(s => _renderSectieKaart(botInhoud, s));
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

// ── Auto-resize textarea ──────────────────────────────────────────────────────
function resizeInvoer() {
  invoerVeld.style.height = "auto";
  invoerVeld.style.height = Math.min(invoerVeld.scrollHeight, 68) + "px";
}

invoerVeld.addEventListener("input", resizeInvoer);

// ── Init ──────────────────────────────────────────────────────────────────────
initialiseerSessie();
laadHuidigeSessie();
renderSessieLijst();
invoerVeld.focus();
