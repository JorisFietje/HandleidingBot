const chatVenster = document.getElementById("chatVenster");
const invoerVeld = document.getElementById("invoerVeld");
const verstuurKnop = document.getElementById("verstuurKnop");
const chatPopup = document.getElementById("chatPopup");
const chatKnop = document.getElementById("chatKnop");

let isOpen = false;
let isGroot = false;
const vergrotKnop = document.getElementById("vergrotKnop");

function toggleChat() {
  isOpen = !isOpen;
  chatPopup.classList.toggle("zichtbaar", isOpen);
  chatPopup.setAttribute("aria-hidden", String(!isOpen));
  chatKnop.classList.toggle("open", isOpen);
  if (isOpen) invoerVeld.focus();
}

function vergrotChat() {
  isGroot = !isGroot;
  chatPopup.classList.toggle("groot", isGroot);
  vergrotKnop.classList.toggle("groot", isGroot);
  scrollNaarOnderen();
}

function scrollNaarOnderen() {
  chatVenster.scrollTop = chatVenster.scrollHeight;
}

function voegBerichtToe(tekst, rol) {
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

function voegSectieKaartToe(inhoud, sectie) {
  const kaart = document.createElement("div");
  kaart.className = "sectie-kaart";
  kaart.innerHTML = `
    <div class="sectie-header">
      <span class="sectie-titel">${sectie.titel}</span>
      <span class="sectie-bron">${sectie.bron}</span>
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

  const tik = document.createElement("div");
  tik.className = "tik-tik";
  tik.innerHTML = "<span></span><span></span><span></span>";

  inhoud.appendChild(tik);
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

async function verstuurBericht() {
  const tekst = invoerVeld.value.trim();
  if (!tekst) return;

  invoerVeld.value = "";
  voegBerichtToe(tekst, "gebruiker");
  setLaadStatus(true);
  toonTypIndicator();

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tekst }),
    });

    if (!response.ok) throw new Error("Server fout");

    const data = await response.json();
    verwijderTypIndicator();

    const botInhoud = voegBerichtToe(data.tekst, "bot");
    for (const sectie of data.secties || []) {
      voegSectieKaartToe(botInhoud, sectie);
    }
  } catch {
    verwijderTypIndicator();
    voegBerichtToe("Er ging iets mis. Probeer het opnieuw.", "bot");
  }

  setLaadStatus(false);
}

function stuurVoorbeeldVraag(vraag) {
  invoerVeld.value = vraag;
  verstuurBericht();
}
