# Changelog

Alle versiewijzigingen van HandleidingChat worden hier bijgehouden.  
Formaat gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.0.0/).

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
