# Changelog

Alle versiewijzigingen van HandleidingChat worden hier bijgehouden.  
Formaat gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.0.0/).

---

## [1.3.0] — 2026-06-07

### Toegevoegd
- **Adminpagina** op `/admin` om de lokale LLM live af te stellen zonder herstart
- Instelbare LLM-parameters: model, `temperature`, `top_p`, `top_k`, `repeat_penalty`, `num_predict`, `num_ctx`, `seed` en de volledige systeemprompt
- Instelbare retrieval-parameters: `top_n` en de zoekdrempels (`drempel_globaal`, `drempel_filter`)
- Instellingen worden gevalideerd, begrensd en opgeslagen in `admin_settings.json`
- **Testset-runner** in de adminpagina: draait de handleidingspecifieke testvragen (`testset.json`) tegen de huidige instellingen en toont het antwoord naast het verwachte antwoord
- **Automatische scoring** per testvraag: dekkingsscore op sleutelwoorden met oordeel goed/deels/mis, een lijst met ontbrekende sleutelwoorden, en een samenvatting (gem. dekking + telling) bovenaan. Getalnotaties (`10.000` / `10000`) worden genormaliseerd zodat ze gelijk tellen
- **Admin-knop** in de header van de chatinterface, met directe link naar `/admin`
- Nieuwe endpoints: `GET/POST /admin/settings`, `POST /admin/settings/reset`, `GET /admin/models`, `GET /admin/testset`, `POST /admin/test-een`

### Gewijzigd
- De Ollama-aanroep stuurt nu expliciet `options` mee (voorheen werden de standaardwaarden van Ollama gebruikt, niet instelbaar)
- Systeemprompt, modelkeuze, `top_n` en zoekdrempels worden nu uit de centrale `settings`-module gelezen i.p.v. hardcoded in `chatbot.py`
- **Bronvermelding compacter**: de twee grote sectiekaarten onder elk antwoord zijn vervangen door een compacte bronbalk met klikbare pill-knoppen (bestandsnaam + paginanummer, link naar de juiste PDF-pagina) in hetzelfde berichtblok. Dubbele bronnen worden samengevoegd.

---

## [1.2.0] — 2026-05-19

### Toegevoegd
- Klikbare bronvermelding met directe link naar de exacte pagina in de PDF (`#page=N`)
- PDF-bestanden worden geserveerd via `/handleidingen/<bestandsnaam>`
- Paginanummer wordt bijgehouden per sectie tijdens het inladen van PDFs

### Verbeterd
- Cosine-drempel verhoogd van 0.15 → 0.42 zodat irrelevante vragen geen resultaten meer opleveren
- Secties met een titel korter dan 3 tekens of inhoud korter dan 80 tekens worden weggefilterd
- Invoerveld is nu een auto-resizing textarea (start op 1 regel, groeit naar max. 2 regels)
- Invoerbalk beperkt tot max. 860px breedte gecentreerd in beeld
- Bot-berichten beperkt tot 75% breedte, gebruikersberichten tot 60%

### Gewijzigd
- Accentkleur rood: `#c0291e` → `#df252c`
- Achtergrondkleur zijbalk/header: `#1a2d4f` (donkerblauw) → `#1b75bc` (middenblauw)
- Zijbalk-teksten bijgewerkt naar wit voor betere leesbaarheid op de lichtere achtergrond

---

## [1.1.0] — 2026-05-18

### Toegevoegd
- Ondersteuning voor PDF-bestanden (`.pdf`) via PyMuPDF — automatische sectiedetectie op lettergrootte en vetgedrukte tekst
- Ondersteuning voor Word-bestanden (`.docx`) via python-docx — sectiedetectie op Heading-stijlen
- Sessies krijgen automatisch een titel op basis van de eerste vraag
- 3-punten menu naast elke sessie voor hernoemen en verwijderen
- Inline naam-editor in de zijbalk

### Verbeterd
- Hybride zoekscoring: cosine-similariteit + fuzzy-boost voor betere trefwoord- en typefoutafhandeling
- `partial_ratio` tegen de volledige titeltekst voor samengestelde woorden
- Lege secties worden weggefilterd bij het laden

### Verwijderd
- Filterwidget voor handleidingen (vervangen door automatisch zoeken over alle handleidingen)

---

## [1.0.0] — 2026-05-17

### Toegevoegd
- Volledige pagina-layout met uitschuifbare zijbalk (niet meer als chat-widget)
- Sessiebeheer via localStorage (max. 20 gesprekken, 2 uur inactiviteit = nieuw gesprek)
- Semantisch zoeken via `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers)
- Fuzzy-matching via rapidfuzz voor typefoutbestendig zoeken
- Sectiekaarten met titel, inhoud en bronvermelding
- Ondersteuning voor Markdown-handleidingen (`.md`)
- FastAPI backend met `/chat` endpoint
- Metesco huisstijl: navy zijbalk/header, rode accenten
