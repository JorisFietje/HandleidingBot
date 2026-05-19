# HandleidingChat

Een chatbot die vragen beantwoordt op basis van handleidingen (PDF, Word, Markdown). De bot doorzoekt de beschikbare handleidingen met semantische zoekopdrachten en toont de meest relevante secties als antwoord, inclusief een directe link naar de exacte pagina in de PDF.

**Huidige versie:** zie [CHANGELOG.md](CHANGELOG.md)

---

## Functionaliteiten

- Semantisch zoeken via sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`)
- Hybride scoring: cosine-similariteit + fuzzy-matching voor typefouten en samengestelde woorden
- Ondersteunt PDF, Word (`.docx`) en Markdown (`.md`) handleidingen
- Klikbare bronvermelding met directe link naar de pagina in de PDF
- Sessiebeheer via localStorage (max. 20 gesprekken, 2 uur inactiviteit = nieuw gesprek)
- Volledige pagina-layout met uitschuifbare zijbalk

---

## Vereisten

- **Python 3.10 of hoger** — [python.org](https://www.python.org/downloads/)
- **pip** — wordt meegeleverd met Python
- Een **terminal** (PowerShell op Windows, Terminal op Mac/Linux)

---

## Installatie

### 1 — Project downloaden

```bash
git clone https://github.com/JorisFietje/HandleidingChat.git
cd HandleidingChat
```

Of download de ZIP via de groene **Code** knop op GitHub en pak deze uit.

---

### 2 — Virtuele omgeving aanmaken

```bash
python -m venv venv
```

Activeren:

```bash
# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

Je ziet `(venv)` voor je prompt als de omgeving actief is.

---

### 3 — Pakketten installeren

```bash
pip install -r requirements.txt
```

| Pakket | Waarvoor |
|---|---|
| `fastapi` | Webframework |
| `uvicorn` | Webserver |
| `sentence-transformers` | Semantisch zoeken (embedding model) |
| `rapidfuzz` | Fuzzy-matching voor typefouten |
| `pymupdf` | PDF-bestanden inlezen |
| `python-docx` | Word-bestanden inlezen |
| `numpy` | Vectorberekeningen |

> **Let op:** het embedding model (`paraphrase-multilingual-MiniLM-L12-v2`, ~470 MB) wordt automatisch gedownload bij de eerste start.

---

### 4 — Handleidingen toevoegen

Zet bestanden in de map `handleidingen/`. Ondersteunde formaten:

| Formaat | Vereisten |
|---|---|
| `.pdf` | Secties worden automatisch gedetecteerd op basis van lettergrootte en vetgedrukte tekst |
| `.docx` | Gebruik Heading-stijlen (Heading 1, Heading 2 etc.) voor sectieopschriften |
| `.md` | Gebruik `##` voor sectieopschriften |

Richtlijn voor goede resultaten:
- Elke sectie moet **minstens 80 tekens** inhoud bevatten
- Sectietitels moeten **minstens 3 tekens** lang zijn
- Hoe duidelijker de opbouw van het document, hoe beter de zoekresultaten

---

### 5 — Server starten

```bash
uvicorn main:app --reload
```

Open vervolgens [http://localhost:8000](http://localhost:8000) in je browser.

---

### 6 — Server stoppen

Druk op `CTRL + C` in de terminal.

---

## Zoekgedrag aanpassen

In `chatbot.py` staan een aantal constanten die het zoekgedrag bepalen:

| Constante | Standaard | Betekenis |
|---|---|---|
| `FUZZY_DREMPEL` | `82` | Minimale fuzzy-score (0–100) voor een trefwoordmatch |
| `MIN_WOORDLENGTE` | `4` | Kortere woorden worden genegeerd bij fuzzy-matching |
| `cosine > 0.42` | `0.42` | Minimale semantische relevantie; lager = meer resultaten, hoger = strikter |
| `top_n` | `2` | Aantal secties dat per vraag wordt teruggegeven |

---

## Problemen

| Probleem | Oplossing |
|---|---|
| `python` niet herkend | Probeer `python3` |
| `pip` niet herkend | Probeer `pip3` of herinstalleer Python met "Add to PATH" aangevinkt |
| Poort 8000 al in gebruik | `uvicorn main:app --reload --port 8080` |
| Model downloadt niet | Controleer internetverbinding; model wordt eenmalig gecached in `~/.cache/huggingface/` |
| PDF geeft geen resultaten | Controleer of de PDF tekstlagen heeft (geen gescande afbeelding) |
