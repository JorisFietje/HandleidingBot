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
| `ollama` | Lokale LLM aansturen voor het genereren van antwoorden |
| `google-genai` | Antwoorden genereren via Google Gemini (cloud) |
| `python-dotenv` | Sleutels uit het `.env`-bestand inladen |

De antwoorden kunnen door **twee** taalmodellen worden gegenereerd; je kiest welke via de adminpagina of automatisch via het `.env`-bestand:

> **Optie A — Google Gemini (cloud, eenvoudigst):** maak een `.env`-bestand aan (kopieer `.env.example`) en vul je sleutel in:
> ```bash
> cp .env.example .env
> # zet vervolgens in .env:  GEMINI_API_KEY=jouw_sleutel
> ```
> Een sleutel haal je gratis op via [Google AI Studio](https://aistudio.google.com/apikey). Zodra de key aanwezig is, schakelt de chatbot **automatisch** over op Gemini — verder hoeft er niets te worden ingesteld. Het standaardmodel is `gemini-2.5-flash` (aanpasbaar via de adminpagina of `GEMINI_MODEL`).

> **Optie B — Ollama (lokaal, geen API-key):** de antwoorden worden lokaal gegenereerd via [Ollama](https://ollama.com). Installeer Ollama, start het, en haal een model op, bijvoorbeeld:
> ```bash
> ollama pull qwen2.5:7b
> ```
> Het standaardmodel is `qwen2.5:7b`. Je kunt het wijzigen via de adminpagina of via de omgevingsvariabele `OLLAMA_MODEL`. Als er geen `GEMINI_API_KEY` is, gebruikt de chatbot standaard Ollama.

> **Let op:** het embedding model (`paraphrase-multilingual-MiniLM-L12-v2`, ~470 MB) wordt automatisch gedownload bij de eerste start. Dit wordt altijd gebruikt voor het zoeken, ongeacht welk antwoordmodel je kiest.

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

## Adminpagina — LLM tweaken

Open [http://localhost:8000/admin](http://localhost:8000/admin) om de LLM live af te stellen. Wijzigingen worden direct toegepast en opgeslagen in `admin_settings.json` (geen herstart nodig).

**Instelbaar:**

| Instelling | Betekenis |
|---|---|
| `provider` | Welk platform de antwoorden genereert: `ollama` (lokaal) of `gemini` (cloud) |
| `gemini_model` | Welk Gemini-model wordt gebruikt (bv. `gemini-2.5-flash` of `gemini-2.5-pro`) |
| `model` | Welk lokaal Ollama-model wordt gebruikt (dropdown van beschikbare modellen) |
| `temperature` | 0 = feitelijk/deterministisch, hoger = creatiever (en meer hallucinatierisico) |
| `top_p` / `top_k` | Sampling-instellingen |
| `repeat_penalty` | Ontmoedigt herhaling |
| `num_predict` | Max. tokens in het antwoord (-1 = onbeperkt) |
| `num_ctx` | Contextvenster in tokens |
| `seed` | Vaste seed = reproduceerbare antwoorden (handig bij testen) |
| `system_prompt` | De volledige systeeminstructie aan de LLM |
| `top_n` | Aantal handleidingsecties dat naar de LLM gaat |
| `drempel_globaal` / `drempel_filter` | Minimale zoekscore (lager = meer resultaten, hoger = strikter) |

**Testset draaien:** onderaan de adminpagina kun je de handleidingspecifieke testvragen (`testset.json`) tegen de huidige instellingen draaien. Elk antwoord wordt naast het verwachte antwoord getoond, zodat je direct ziet of een wijziging de antwoorden verbetert of verslechtert. Pas een instelling aan → opslaan → tests opnieuw draaien → vergelijken.

> Tip: zet `temperature` op `0` en een vaste `seed` tijdens het testen, zodat verschillen tussen runs door je instellingen komen en niet door toeval.

Voeg eigen testvragen toe door `testset.json` aan te vullen (elk item heeft een `vraag` en een `verwacht` antwoord).

---

## Problemen

| Probleem | Oplossing |
|---|---|
| `python` niet herkend | Probeer `python3` |
| `pip` niet herkend | Probeer `pip3` of herinstalleer Python met "Add to PATH" aangevinkt |
| Poort 8000 al in gebruik | `uvicorn main:app --reload --port 8080` |
| Model downloadt niet | Controleer internetverbinding; model wordt eenmalig gecached in `~/.cache/huggingface/` |
| PDF geeft geen resultaten | Controleer of de PDF tekstlagen heeft (geen gescande afbeelding) |
