# HandleidingChat

Een chatbot die vragen beantwoordt op basis van Markdown-handleidingen. De bot doorzoekt de beschikbare handleidingen en toont de meest relevante secties als antwoord.

---

## Wat heb je nodig?

- **Python 3.10 of hoger** — download via [python.org](https://www.python.org/downloads/)
- **pip** — wordt automatisch meegeleverd met Python
- Een **terminal** (PowerShell op Windows, Terminal op Mac/Linux)

---

## Stap-voor-stap installatie

### Stap 1 — Download het project

Klik op de groene **Code** knop rechtsboven op deze pagina en kies **Download ZIP**.  
Pak het ZIP-bestand uit naar een map naar keuze, bijvoorbeeld `C:\Projects\HandleidingBot`.

Of via Git (als je dat hebt geïnstalleerd):

```bash
git clone https://github.com/JorisFietje/HandleidingBot.git
cd HandleidingBot
```

---

### Stap 2 — Open de terminal in de projectmap

**Windows:**  
Open de map in Verkenner, klik in de adresbalk, typ `powershell` en druk op Enter.

**Mac/Linux:**  
Open Terminal en navigeer naar de map:
```bash
cd pad/naar/HandleidingBot
```

---

### Stap 3 — Maak een virtuele omgeving aan (aanbevolen)

Een virtuele omgeving zorgt ervoor dat de benodigde pakketten alleen voor dit project worden geïnstalleerd en niets op je systeem overschrijven.

```bash
python -m venv venv
```

Activeer de virtuele omgeving:

- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **Mac/Linux:**
  ```bash
  source venv/bin/activate
  ```

Je ziet nu `(venv)` voor je prompt staan — dat betekent dat de omgeving actief is.

---

### Stap 4 — Installeer de benodigde pakketten

```bash
pip install -r requirements.txt
```

Dit installeert automatisch:
- `fastapi` — het webframework
- `uvicorn` — de webserver
- `python-multipart` — voor formulierverwerking

---

### Stap 5 — Start de server

```bash
uvicorn main:app --reload
```

Je ziet output zoals:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

### Stap 6 — Open de chatbot in je browser

Ga naar: [http://localhost:8000](http://localhost:8000)

De chat-widget verschijnt rechtsonder in het scherm. Klik erop om een vraag te stellen.

---

## Handleidingen toevoegen of aanpassen

Alle handleidingen staan als Markdown-bestanden in de map `handleidingen/`.  
Je kunt eenvoudig een nieuwe handleiding toevoegen:

1. Maak een nieuw `.md`-bestand aan in de map `handleidingen/`, bijvoorbeeld `printer_handleiding.md`
2. Gebruik `##` voor sectieopschriften — de bot gebruikt deze om antwoorden op te splitsen:

```markdown
# Printer Handleiding

## Printer instellen
Sluit de printer aan via USB of stel het netwerk in via...

## Printer werkt niet
Controleer of de printer aan staat en of er papier in zit...
```

3. Herstart de server — de nieuwe handleiding wordt automatisch ingeladen.

---

## Server stoppen

Druk op `CTRL + C` in de terminal.

---

## Problemen?

| Probleem | Oplossing |
|---|---|
| `python` niet herkend | Probeer `python3` in plaats van `python` |
| `pip` niet herkend | Probeer `pip3` of herinstalleer Python met de optie "Add to PATH" aangevinkt |
| Poort 8000 al in gebruik | Start met een andere poort: `uvicorn main:app --reload --port 8080` |
| Pagina laadt niet | Controleer of de server nog draait in de terminal |
