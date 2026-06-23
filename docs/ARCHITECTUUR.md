# Architectuur & Techniek — HandleidingChat

Dit document legt uit hoe HandleidingChat technisch in elkaar zit: welke technologie
wij in welk bestand gebruiken en waarvoor het dient. Het is bedoeld als naslag voor
iedereen die de code wil begrijpen of uitbreiden.

Voor de functionele geschiedenis (wat wij bouwden en welke problemen wij oplosten),
zie [ROADMAP.md](ROADMAP.md). Voor installeren en starten, zie [README.md](README.md).

---

## 1. Wat doet de applicatie in het kort?

Een gebruiker stelt een vraag in de chat. De applicatie zoekt de meest relevante
secties uit de handleidingen, geeft die als context aan een taalmodel (LLM) — lokaal
via Ollama of in de cloud via Google Gemini — en toont het gegenereerde antwoord met
een bronvermelding en eventueel afbeeldingen.

**De reis van een vraag (request flow):**

```
Browser (script.js)
   │  POST /chat  { tekst, filter }
   ▼
main.py  ──►  chatbot.generate_answer()        (chatbot/answer.py)
                 │
                 ├─ search_sections()      → relevante secties (semantisch + fuzzy)
                 │     └─ settings.get_settings()      (drempels, top_n)
                 │
                 ├─ _generate_llm_answer()  → llm_providers.generate()
                 │     └─ Ollama (lokaal)  óf  Gemini (cloud), o.b.v. settings.provider
                 │        └─ settings.get_llm_options()  (temperature, seed, ...)
                 │
                 └─ _image_urls()          → links naar PDF-figuren
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
| **Ollama** | Draait het taalmodel (LLM) lokaal op de eigen machine; genereert het antwoord zonder API-kosten. Standaardmodel: `qwen2.5:7b`. |
| **Google Gemini** (`google-genai`) | Alternatieve LLM-provider in de cloud; wordt automatisch gebruikt zodra er een `GEMINI_API_KEY` in `.env` staat. Standaardmodel: `gemini-2.5-flash`. |
| **python-dotenv** | Laadt sleutels (bv. `GEMINI_API_KEY`) uit het `.env`-bestand in de omgeving. |
| **Vanilla HTML/CSS/JS** | De frontend, bewust zonder framework — klein en zonder buildstap. |
| **marked.js** | Zet de Markdown uit het LLM-antwoord om naar HTML (via CDN geladen). |
| **localStorage** | Bewaart de gespreksgeschiedenis in de browser (geen database nodig). |

> **Lokaal (Ollama) of cloud (Gemini)?** Ollama houdt handleidingen en vragen op de
> eigen machine en kost niets per vraag; Gemini vereist alleen een API-key in `.env`
> en geen lokale GPU/model. De keuze staat in `settings.provider` (of automatisch:
> Gemini zodra er een key is). De abstractie zit in `llm_providers.py`, zodat de rest
> van de code niet weet welke provider draait.

---

## 3. Bestand voor bestand

### Backend (Python)

#### `main.py` — webserver & endpoints
De instaplaag. Hier draait FastAPI en worden alle URL's gedefinieerd. Dit bestand
bevat zelf weinig logica: het vertaalt HTTP-verzoeken naar aanroepen van het
`chatbot`-package en `settings.py`, en stuurt het resultaat terug als JSON of bestand.
Bij het starten worden de handleidingen één keer ingelezen en in geheugen gehouden.

Belangrijkste endpoints:
- `POST /chat` — de kernfunctie: beantwoordt een vraag.
- `GET /afbeelding` — rendert één figuurregio uit een PDF live als PNG (niets wordt
  opgeslagen; bevat een check tegen path-traversal voor de veiligheid).
- `GET /admin` + `/admin/*` — de adminpagina en de instellingen-/testset-endpoints.
- De scorings­logica voor de testset (`_key_tokens`, `_score_answer`) zit hier, omdat
  ze alleen voor de admin-endpoints nodig is.

> De route-paden en JSON-keys (`tekst`, `secties`, `vraag`, ...) zijn het contract met
> de frontend en zijn daarom Nederlands gebleven; de Python-namen zijn Engels.

#### `chatbot/` — de "denklaag" (package)
Het hart van de applicatie, opgesplitst per verantwoordelijkheid. `__init__.py`
her-exporteert de publieke API (`load_manuals`, `generate_answer`, `STOPWORDS`).

| Module | Verantwoordelijkheid |
|---|---|
| `model.py` | De `Section`-dataclass + gedeelde constanten (`STOPWORDS`, `MANUALS_DIR`, ...). Geen interne afhankelijkheden. |
| `text.py` | Tekst-helpers: taaldetectie, trefwoorden (`_keywords`), fuzzy-score, glyph-opschoning, symboolpatronen. |
| `embeddings.py` | Het embedding-model (lazy via `_get_model`) + `_compute_embeddings` en `_cosine_scores`. |
| `loading.py` | Inladen: `load_manuals` + de PDF/Word/Markdown-parsers + kwaliteitsfilter. |
| `search.py` | `search_sections`: hybride score (cosine + fuzzy) met modelnummer-routing, taalfilter, boosts (foutcodes, symboolpatronen) en deduplicatie. |
| `images.py` | PDF-figuren lokaliseren (`_image_urls`, `_regions_on_page`) + de figuur-index die `loading.py` vult. |
| `answer.py` | `generate_answer`: intentieherkenning, het zoeken aansturen, de LLM aanroepen (`_generate_llm_answer`) en bronnen/figuren samenstellen. |

Afhankelijkheidsgraaf (acyclisch): `model` → {`text`, `embeddings`, `images`} →
`loading`; {`text`, `embeddings`} → `search`; {`model`, `text`, `search`, `images`}
→ `answer`.

#### `llm_providers.py` — taalmodel-abstractie
De enige plek die weet hóé een antwoord bij een LLM wordt opgehaald. `generate()`
kiest op basis van `settings.provider` tussen Ollama (lokaal) en Gemini (cloud) en
vertaalt de samplingparameters naar het formaat van die provider. `gemini_available()`
meldt of er een API-key in `.env` staat. De Gemini-client wordt lazy opgebouwd.

#### `settings.py` — instellingen (runtime aanpasbaar)
Centrale plek voor alle afstelbare waarden: de provider, het LLM-model (Ollama én
Gemini), samplingparameters (temperature, top_p, seed, ...), de systeemprompt en de
retrieval-drempels. Laadt ook `.env` (via python-dotenv). De adminpagina leest en
schrijft deze via de `/admin`-endpoints. Waarden worden **gevalideerd en begrensd**
(`_validate` + `_BOUNDS`) en opgeslagen in `admin_settings.json`, zodat ze een herstart
overleven. Niets vereist een herstart: elke vraag leest de instellingen opnieuw uit.
De dict-keys (`model`, `temperature`, `drempel_globaal`, ...) zijn het contract met de
adminpagina en blijven daarom Nederlands.

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
| `docs/requirements.txt` | De Python-pakketten met versies. |
| `.env` / `.env.example` | Sleutels (bv. `GEMINI_API_KEY`) voor de cloud-provider. `.env.example` is het sjabloon; `.env` zelf staat in `.gitignore`. |
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
dan elk apart. De details (boosts, drempels, taalfilter) staan in `search_sections`.

---

## 5. Hoe alles samenkomt bij het starten

1. `uvicorn main:app` start de webserver.
2. `main.py` roept `load_manuals()` aan → PDF's/Word/Markdown worden ingelezen,
   opgedeeld in secties en van embeddings voorzien (eenmalig, in geheugen).
3. De server serveert `index.html`; de browser laadt `script.js`.
4. Elke vraag gaat via `POST /chat` naar `generate_answer()`, die zoekt, de LLM
   aanroept (Ollama of Gemini) en het antwoord met bronnen/afbeeldingen teruggeeft.
5. Via `/admin` kunnen instellingen live worden aangepast zonder herstart.
