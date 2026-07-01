# Metesco Chat — Setup Guide

Een chatbot die vragen beantwoordt op basis van handleidingen (PDF, Word, Markdown). De bot doorzoekt de handleidingen met semantisch zoeken en laat de meest relevante secties zien als antwoord, inclusief een directe link naar de exacte pagina in de PDF.

Deze guide legt **stap voor stap** uit hoe je de applicatie lokaal draait. Er is een apart hoofdstuk voor **Windows** en voor **Mac** — volg alleen het hoofdstuk voor jouw besturingssysteem.

**Huidige versie:** zie [CHANGELOG.md](CHANGELOG.md)

---

## Wat ga je installeren?

De applicatie heeft dit nodig om te draaien:

| Onderdeel | Waarvoor | Verplicht? |
|---|---|---|
| **Python 3.10+** | De taal waarin de app draait | ✅ Ja |
| **Git** | Om het project te downloaden | ✅ Ja (of download de ZIP) |
| **Python-pakketten** | FastAPI, zoekmodel, PDF-lezer, enz. | ✅ Ja (via `pip`) |
| **Embedding-model** (~470 MB) | Het zoekmodel; wordt automatisch gedownload | ✅ Ja (automatisch) |
| **Een taalmodel voor de antwoorden** | Kies **Ollama (lokaal)** óf **Google Gemini (cloud)** | ✅ Ja, één van beide |

Voor het **antwoord** heb je een taalmodel (LLM) nodig. Je hebt twee opties:

- **Optie A — Ollama (lokaal):** het model draait op je eigen computer. Geen API-key, geen internet nodig na de download, alles blijft lokaal. Wel zwaarder voor je computer. **Dit is de "local model"-optie.**
- **Optie B — Google Gemini (cloud):** het model draait in de cloud van Google. Sneller en lichter voor je computer, maar je hebt een (gratis) API-key en internet nodig.

Beide worden hieronder per besturingssysteem uitgelegd. Het **zoekmodel** (embedding) wordt altijd gebruikt, ongeacht je keuze.

---

<br>

# 🪟 Windows

Volg deze stappen in volgorde. Open **PowerShell** (Startmenu → typ "PowerShell" → Enter).

## Stap 1 — Python installeren

1. Ga naar [python.org/downloads](https://www.python.org/downloads/) en download Python 3.10 of hoger.
2. Start de installer. **Belangrijk:** vink onderaan **"Add python.exe to PATH"** aan voordat je op *Install Now* klikt.
3. Controleer de installatie in PowerShell:

```powershell
python --version
```

Je moet iets zien als `Python 3.12.x`. Zie je een foutmelding? Herstart PowerShell, of herinstalleer Python met "Add to PATH" aangevinkt.

## Stap 2 — Git installeren (of ZIP downloaden)

- **Met Git:** download en installeer [Git voor Windows](https://git-scm.com/download/win) (standaardopties zijn prima).
- **Zonder Git:** ga naar de GitHub-pagina van het project, klik op de groene **Code**-knop → **Download ZIP**, en pak het bestand uit. Sla dan Stap 3 over en ga verder in de uitgepakte map.

## Stap 3 — Project downloaden

```powershell
git clone https://github.com/JorisFietje/HandleidingChat.git
cd HandleidingChat
```

## Stap 4 — Virtuele omgeving aanmaken en activeren (OPTIONEEL)

Een virtuele omgeving (venv) houdt de pakketten van dit project apart van de rest van je systeem.

```powershell
python -m venv venv
venv\Scripts\activate
```

Je ziet nu `(venv)` vóór je prompt. Dat betekent dat de omgeving actief is.

> **Foutmelding over "running scripts is disabled"?** Voer eenmalig uit:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
> en probeer `venv\Scripts\activate` opnieuw.

> **Liever geen venv?** Dat kan: sla deze stap over en ga verder met Stap 5. De pakketten worden dan in je globale Python geïnstalleerd. Op Windows werkt dit meestal direct. Nadeel: bij meerdere Python-projecten kun je versieconflicten krijgen — daarom is een venv de aanbevolen route.

## Stap 5 — Python-pakketten installeren

```powershell
pip install -r docs\requirements.txt
```

Dit installeert onder andere:

| Pakket | Waarvoor |
|---|---|
| `fastapi` + `uvicorn` | Webframework en webserver |
| `sentence-transformers` | Semantisch zoeken (embedding-model) |
| `rapidfuzz` | Fuzzy-matching voor typefouten |
| `pymupdf` | PDF-bestanden inlezen |
| `python-docx` | Word-bestanden inlezen |
| `ollama` | Lokaal taalmodel aansturen |
| `google-genai` | Antwoorden via Google Gemini (cloud) |
| `python-dotenv` | Instellingen uit `.env` inladen |

## Stap 6 — Kies je taalmodel

### Optie A — Ollama (lokaal model) 🖥️

1. Download en installeer **Ollama** via [ollama.com/download](https://ollama.com/download) (Windows-installer).
2. Na installatie draait Ollama automatisch op de achtergrond (je ziet het icoon in de systeembalk).
3. Haal het standaardmodel op — open een **nieuwe** PowerShell en voer uit:

```powershell
ollama pull qwen2.5:7b
```

Dit downloadt het model (~4,7 GB, eenmalig). Klaar? De chatbot gebruikt automatisch Ollama zolang er **geen** Gemini-key is ingesteld.

> **Let op:** een lokaal model vraagt behoorlijk wat geheugen. Voor `qwen2.5:7b` heb je bij voorkeur 8 GB RAM of meer. Werkt het traag? Probeer een kleiner model, bijvoorbeeld `ollama pull qwen2.5:3b`, en stel dat model in op de adminpagina.

### Optie B — Google Gemini (cloud)

1. Vraag de API-key op bij de projecteigenaar (deze wordt apart toegestuurd), óf haal een eigen gratis key op via [Google AI Studio](https://aistudio.google.com/apikey).
2. Kopieer het voorbeeldbestand naar `.env`:

```powershell
copy .env.example .env
```

3. Open `.env` in een teksteditor en vervang `jouw_sleutel_hier` door de echte key achter `GEMINI_API_KEY=`.

Zodra de key aanwezig is, schakelt de chatbot **automatisch** over op Gemini. Standaardmodel is `gemini-2.5-flash` (aan te passen via de adminpagina of de variabele `GEMINI_MODEL` in `.env`).

## Stap 7 — Server starten

```powershell
uvicorn main:app --reload
```

Open daarna [http://localhost:8000](http://localhost:8000) in je browser.

> De **eerste** keer wordt het embedding-model (~470 MB) gedownload — dat kan even duren. Daarna start het snel.

**Server stoppen:** druk op `CTRL + C` in PowerShell.

---

<br>

# 🍎 Mac

Volg deze stappen in volgorde. Open **Terminal** (Cmd + spatie → typ "Terminal" → Enter).

## Stap 1 — Python installeren

macOS heeft vaak een oude Python. Installeer een actuele versie via [Homebrew](https://brew.sh) (aanbevolen) of via [python.org](https://www.python.org/downloads/macos/).

Met Homebrew:

```bash
brew install python
```

Controleer:

```bash
python3 --version
```

Je moet `Python 3.10` of hoger zien.

> Op Mac gebruik je meestal `python3` en `pip3` in plaats van `python` en `pip`.

## Stap 2 — Git installeren (of ZIP downloaden)

Git zit vaak al op macOS. Controleer met `git --version`. Ontbreekt het, dan installeert de eerste `git`-opdracht de Xcode Command Line Tools automatisch, of gebruik `brew install git`.

Geen Git? Download de ZIP via de groene **Code**-knop op GitHub en pak deze uit.

## Stap 3 — Project downloaden

```bash
git clone https://github.com/JorisFietje/HandleidingChat.git
cd HandleidingChat
```

## Stap 4 — Virtuele omgeving aanmaken en activeren

```bash
python3 -m venv venv
source venv/bin/activate
```

Je ziet nu `(venv)` vóór je prompt. Dat betekent dat de omgeving actief is.

> **Liever geen venv?** Dat kan: sla deze stap over en ga verder met Stap 5. Bij een via Homebrew geïnstalleerde Python blokkeert een globale installatie vaak met `externally-managed-environment`. Gebruik dan `pip3 install --user -r docs/requirements.txt`, of forceer met `--break-system-packages`. Dit vervuilt je systeem-Python en kan versieconflicten geven — daarom is een venv de aanbevolen route.

## Stap 5 — Python-pakketten installeren

```bash
pip install -r docs/requirements.txt
```

Dit installeert onder andere:

| Pakket | Waarvoor |
|---|---|
| `fastapi` + `uvicorn` | Webframework en webserver |
| `sentence-transformers` | Semantisch zoeken (embedding-model) |
| `rapidfuzz` | Fuzzy-matching voor typefouten |
| `pymupdf` | PDF-bestanden inlezen |
| `python-docx` | Word-bestanden inlezen |
| `ollama` | Lokaal taalmodel aansturen |
| `google-genai` | Antwoorden via Google Gemini (cloud) |
| `python-dotenv` | Instellingen uit `.env` inladen |

## Stap 6 — Kies je taalmodel

### Optie A — Ollama (lokaal model) 🖥️

1. Installeer **Ollama** via [ollama.com/download](https://ollama.com/download) (Mac-app) of met Homebrew:

```bash
brew install ollama
```

2. Start Ollama (als app, of via `ollama serve` in een aparte Terminal).
3. Haal het standaardmodel op:

```bash
ollama pull qwen2.5:7b
```

Dit downloadt het model (~4,7 GB, eenmalig). De chatbot gebruikt automatisch Ollama zolang er **geen** Gemini-key is ingesteld.

> **Let op:** een lokaal model vraagt behoorlijk wat geheugen. Voor `qwen2.5:7b` heb je bij voorkeur 8 GB RAM of meer. Op een Apple Silicon Mac (M1/M2/M3) draait dit prima. Te zwaar? Gebruik een kleiner model met `ollama pull qwen2.5:3b` en stel dat in op de adminpagina.

### Optie B — Google Gemini (cloud)

1. Vraag de API-key op bij de projecteigenaar (deze wordt apart toegestuurd), óf haal een eigen gratis key op via [Google AI Studio](https://aistudio.google.com/apikey).
2. Kopieer het voorbeeldbestand naar `.env`:

```bash
cp .env.example .env
```

3. Open `.env` in een teksteditor en vervang `jouw_sleutel_hier` door de echte key achter `GEMINI_API_KEY=`.

Zodra de key aanwezig is, schakelt de chatbot **automatisch** over op Gemini. Standaardmodel is `gemini-2.5-flash` (aan te passen via de adminpagina of de variabele `GEMINI_MODEL` in `.env`).

## Stap 7 — Server starten

```bash
uvicorn main:app --reload
```

Open daarna [http://localhost:8000](http://localhost:8000) in je browser.

> De **eerste** keer wordt het embedding-model (~470 MB) gedownload — dat kan even duren. Daarna start het snel.

**Server stoppen:** druk op `CTRL + C` in Terminal.

---

<br>

# 📚 Handleidingen toevoegen (Windows & Mac)

Zet je handleidingen in de map `handleidingen/`. Ondersteunde formaten:

| Formaat | Vereisten |
|---|---|
| `.pdf` | Secties worden automatisch gedetecteerd op basis van lettergrootte en vetgedrukte tekst |
| `.docx` | Gebruik Heading-stijlen (Heading 1, Heading 2 enz.) voor sectieopschriften |
| `.md` | Gebruik `##` voor sectieopschriften |

Richtlijn voor goede resultaten:
- Elke sectie moet **minstens 80 tekens** inhoud bevatten.
- Sectietitels moeten **minstens 3 tekens** lang zijn.
- Hoe duidelijker de opbouw van het document, hoe beter de zoekresultaten.

> Na het toevoegen of wijzigen van handleidingen wordt de zoek-index opnieuw opgebouwd bij de eerstvolgende start.

---

# ⚙️ Adminpagina — het taalmodel afstellen

Open [http://localhost:8000/admin](http://localhost:8000/admin) om het taalmodel live bij te stellen. Wijzigingen worden direct toegepast en opgeslagen in `admin_settings.json` (geen herstart nodig).

**Belangrijkste instellingen:**

| Instelling | Betekenis |
|---|---|
| `provider` | Welk platform de antwoorden genereert: `ollama` (lokaal) of `gemini` (cloud) |
| `gemini_model` | Welk Gemini-model wordt gebruikt (bv. `gemini-2.5-flash` of `gemini-2.5-pro`) |
| `model` | Welk lokaal Ollama-model wordt gebruikt (dropdown van beschikbare modellen) |
| `temperature` | 0 = feitelijk/deterministisch, hoger = creatiever (en meer hallucinatierisico) |
| `top_p` / `top_k` | Sampling-instellingen |
| `num_predict` | Max. tokens in het antwoord (-1 = onbeperkt) |
| `num_ctx` | Contextvenster in tokens |
| `system_prompt` | De volledige systeeminstructie aan het taalmodel |
| `top_n` | Aantal handleidingsecties dat naar het model gaat |
| `drempel_globaal` / `drempel_filter` | Minimale zoekscore (lager = meer resultaten, hoger = strikter) |

**Testset draaien:** onderaan de adminpagina kun je de testvragen (`testset.json`) tegen de huidige instellingen draaien. Elk antwoord wordt naast het verwachte antwoord getoond, zodat je direct ziet of een wijziging de antwoorden verbetert. Pas een instelling aan → opslaan → tests opnieuw draaien → vergelijken.

> Tip: zet `temperature` op `0` tijdens het testen, zodat verschillen tussen runs door je instellingen komen en niet door toeval.

---

# 🛟 Problemen oplossen

| Probleem | Oplossing |
|---|---|
| `python` niet herkend (Windows) | Herinstalleer Python met "Add to PATH" aangevinkt, of herstart PowerShell |
| `python` niet herkend (Mac) | Gebruik `python3` en `pip3` |
| `pip` niet herkend | Gebruik `pip3`, of activeer eerst de venv (Stap 4) |
| venv activeren geeft "scripts disabled" (Windows) | Voer `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` uit |
| Poort 8000 al in gebruik | `uvicorn main:app --reload --port 8080` en open dan poort 8080 |
| Embedding-model downloadt niet | Controleer internetverbinding; het model wordt eenmalig gecached in `~/.cache/huggingface/` |
| Ollama-antwoorden werken niet | Controleer of Ollama draait en of je `ollama pull qwen2.5:7b` hebt uitgevoerd |
| Gemini werkt niet | Controleer of `.env` bestaat met een geldige `GEMINI_API_KEY` en dat je internet hebt |
| PDF geeft geen resultaten | Controleer of de PDF een tekstlaag heeft (geen gescande afbeelding) |
