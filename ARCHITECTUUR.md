# Architectuur & Techniek — HandleidingChat

Dit document legt uit hoe HandleidingChat technisch in elkaar zit: welke technologie
wij in welk bestand gebruiken en waarvoor het dient. Het is bedoeld als naslag voor
iedereen die de code wil begrijpen of uitbreiden.

Voor de functionele geschiedenis (wat wij bouwden en welke problemen wij oplosten),
zie [ROADMAP.md](ROADMAP.md). Voor installeren en starten, zie [README.md](README.md).

---

## 1. Wat doet de applicatie in het kort?

Een gebruiker stelt een vraag in de chat. De applicatie zoekt de meest relevante
secties uit de handleidingen, geeft die als context aan een lokale taalmodel (LLM),
en toont het gegenereerde antwoord met een bronvermelding en eventueel afbeeldingen.

**De reis van een vraag (request flow):**

```
Browser (script.js)
   │  POST /chat  { tekst, filter }
   ▼
main.py  ──►  chatbot.genereer_antwoord()
                 │
                 ├─ zoek_secties()        → relevante secties (semantisch + fuzzy)
                 │     └─ settings.get_instellingen()  (drempels, top_n)
                 │
                 ├─ _genereer_llm_antwoord()  → Ollama (lokaal model)
                 │     └─ settings.get_llm_opties()    (temperature, seed, ...)
                 │
                 └─ _afbeelding_urls()     → links naar PDF-figuren
   ▼
Browser krijgt JSON terug { tekst, secties, opties, afbeeldingen }
   │  rendert antwoord, bronknoppen en afbeeldingsgalerij
```

---

## 2. Technologiekeuzes (de stack)

| Technologie | Waarvoor wij het gebruiken |
|---|---|
| **Python 3.10+** | De volledige backend. |
| **FastAPI** | Webframework: definieert de HTTP-endpoints en serialiseert JSON. |
| **Uvicorn** | De ASGI-webserver die FastAPI draait (`uvicorn main:app`). |
| **sentence-transformers** | Zet tekst om in vectoren (embeddings) voor *semantisch* zoeken — zoeken op betekenis i.p.v. exacte woorden. Model: `paraphrase-multilingual-MiniLM-L12-v2` (meertalig, ~470 MB). |
| **NumPy** | Snelle vectorberekeningen (cosine-similariteit tussen embeddings). |
| **rapidfuzz** | Fuzzy-matching: trefwoorden vinden ondanks typefouten en samengestelde woorden. Vult het semantisch zoeken aan. |
| **PyMuPDF (`fitz`)** | PDF's inlezen (tekst + opmaak voor sectiedetectie) en figuren live als PNG renderen. |
| **python-docx** | Word-bestanden (`.docx`) inlezen via Heading-stijlen. |
| **Ollama** | Draait het taalmodel (LLM) lokaal op de eigen machine; genereert het uiteindelijke antwoord. Standaardmodel: `qwen2.5:7b`. |
| **Vanilla HTML/CSS/JS** | De frontend, bewust zonder framework — klein en zonder buildstap. |
| **marked.js** | Zet de Markdown uit het LLM-antwoord om naar HTML (via CDN geladen). |
| **localStorage** | Bewaart de gespreksgeschiedenis in de browser (geen database nodig). |

> **Waarom lokaal (Ollama) i.p.v. een cloud-API?** Privacy en kosten: de handleidingen
> en vragen verlaten de eigen machine niet, en er zijn geen API-kosten per vraag.

---

## 3. Bestand voor bestand

### Backend (Python)

#### `main.py` — webserver & endpoints
De instaplaag. Hier draait FastAPI en worden alle URL's gedefinieerd. Dit bestand
bevat zelf weinig logica: het vertaalt HTTP-verzoeken naar aanroepen van `chatbot.py`
en `settings.py`, en stuurt het resultaat terug als JSON of bestand. Bij het starten
worden de handleidingen één keer ingelezen en in geheugen gehouden.

Belangrijkste endpoints:
- `POST /chat` — de kernfunctie: beantwoordt een vraag.
- `GET /afbeelding` — rendert één figuurregio uit een PDF live als PNG (niets wordt
  opgeslagen; bevat een check tegen path-traversal voor de veiligheid).
- `GET /admin` + `/admin/*` — de adminpagina en de instellingen-/testset-endpoints.
- De scorings­logica voor de testset (`_belangrijke_tokens`, `_scoor_antwoord`) zit
  hier, omdat ze alleen voor de admin-endpoints nodig is.

#### `chatbot.py` — de "denklaag"
Het hart van de applicatie. Vier verantwoordelijkheden:
1. **Inladen** (`laad_handleidingen`, `_parseer_pdf/_docx/_md`): handleidingen inlezen
   en opdelen in secties, met een kwaliteitsfilter dat rommel (inhoudsopgaven, lege
   blokken) wegfiltert.
2. **Indexeren** (`_bereken_embeddings`, `_trefwoorden`): per sectie een embedding en
   een trefwoord-set berekenen.
3. **Zoeken** (`zoek_secties`): de relevante secties bij een vraag vinden via een
   hybride score (semantische cosine-similariteit + fuzzy trefwoordmatch), met
   modelnummer-routing, taalfilter, score-boosts (foutcodes, symboolpatronen) en
   deduplicatie.
4. **Antwoord** (`genereer_antwoord`, `_genereer_llm_antwoord`, `_afbeelding_urls`):
   de gevonden secties als context aan Ollama geven, het antwoord opschonen, en de
   bronnen en figuren samenstellen.

#### `settings.py` — instellingen (runtime aanpasbaar)
Centrale plek voor alle afstelbare waarden: het LLM-model, samplingparameters
(temperature, top_p, seed, ...), de systeemprompt en de retrieval-drempels. De
adminpagina leest en schrijft deze via de `/admin`-endpoints. Waarden worden
**gevalideerd en begrensd** (`_valideer` + `_GRENZEN`) en opgeslagen in
`admin_settings.json`, zodat ze een herstart overleven. Niets vereist een herstart:
elke vraag leest de instellingen opnieuw uit.

### Frontend (in `static/`)

#### `index.html` — de chatinterface
De HTML-structuur: zijbalk (geschiedenis), header, chatvenster en invoerbalk. Laadt
`style.css`, `script.js` en marked.js. De `?v=...` achter de bestandsnamen is
cache-busting, zodat de browser na een wijziging de nieuwe versie ophaalt.

#### `script.js` — logica van de chat
Vanilla JS, geen framework. Regelt: sessiebeheer in `localStorage`, berichten
versturen naar `POST /chat`, het antwoord renderen (Markdown via marked, bronknoppen,
afbeeldingsgalerij met lightbox, keuze-chips), plus UX-hulp zoals de typ-indicator,
het auto-resizing invoerveld en autocomplete op handleidingnamen.

#### `style.css` — opmaak van de chat
Alle styling van de chatinterface: layout, kleuren (Metesco-huisstijl), chatbubbels,
zijbalk, bronbalk, afbeeldingsgalerij en lightbox.

#### `admin.html` + `admin.js` + `admin.css` — de adminpagina
Een los schermpje om de LLM af te stellen en de testset te draaien. `admin.html` is
het formulier (sliders en velden), `admin.js` praat met de `/admin`-endpoints (laden,
opslaan, tests draaien en scoren), en `admin.css` verzorgt de opmaak.

### Data & configuratie

| Bestand/map | Wat het is |
|---|---|
| `handleidingen/` | De bronbestanden (PDF/Word/Markdown) die doorzocht worden. Hier nieuwe handleidingen neerzetten. |
| `testset.json` | Testvragen met een verwacht antwoord, voor de testset-runner op de adminpagina. |
| `admin_settings.json` | De opgeslagen admin-instellingen. Wordt automatisch aangemaakt; staat in `.gitignore` (machine-specifiek). |
| `metesco-favicon.svg` | Het logo/favicon. |
| `requirements.txt` | De Python-pakketten met versies. |
| `.gitignore` | Houdt `__pycache__/`, `.env` en `admin_settings.json` buiten git. |

---

## 4. Twee kernconcepten uitgelegd

### Semantisch zoeken met embeddings
Een **embedding** is een lijst getallen (een vector) die de *betekenis* van een stuk
tekst vastlegt. Teksten met een vergelijkbare betekenis krijgen vergelijkbare vectoren.
Bij het inladen berekenen wij één embedding per sectie. Bij een vraag berekenen wij de
embedding van de vraag en zoeken wij de secties met de meest gelijkende vector
(**cosine-similariteit**, een dot-product van genormaliseerde vectoren). Zo vinden wij
het juiste antwoord ook als de gebruiker andere woorden gebruikt dan de handleiding.

### Waarom een hybride score (embeddings + fuzzy)?
Puur semantisch zoeken mist soms exacte trefwoorden, typefouten en samengestelde
woorden (bv. "789" of "opdrachtbeschrijving"). Daarom combineren wij de cosine-score
met een **fuzzy trefwoord-score** (rapidfuzz). Het semantische deel vangt de betekenis;
het fuzzy deel vangt de letterlijke termen. Samen geeft dat duidelijk betere resultaten
dan elk apart. De details (boosts, drempels, taalfilter) staan in `zoek_secties`.

---

## 5. Hoe alles samenkomt bij het starten

1. `uvicorn main:app` start de webserver.
2. `main.py` roept `laad_handleidingen()` aan → PDF's/Word/Markdown worden ingelezen,
   opgedeeld in secties en van embeddings voorzien (eenmalig, in geheugen).
3. De server serveert `index.html`; de browser laadt `script.js`.
4. Elke vraag gaat via `POST /chat` naar `genereer_antwoord()`, die zoekt, de LLM
   aanroept en het antwoord met bronnen/afbeeldingen teruggeeft.
5. Via `/admin` kunnen instellingen live worden aangepast zonder herstart.
