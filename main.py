"""Webserver en HTTP-endpoints (FastAPI).

Dit is de instaplaag van de applicatie: hier draait de webserver en worden alle
URL's gedefinieerd. De inhoudelijke logica zit in het chatbot-package en settings.py;
dit bestand vertaalt HTTP-verzoeken naar aanroepen daarvan en stuurt het resultaat
als JSON of bestand terug.

Bij het starten worden de handleidingen één keer ingelezen (load_manuals) en in
geheugen gehouden, zodat elke vraag snel beantwoord wordt.

Endpoints:
- GET  /                  -> de chatinterface (static/index.html)
- POST /chat              -> beantwoordt een vraag (kernfunctie)
- GET  /afbeelding        -> rendert één figuur uit een PDF live als PNG
- GET  /handleidingen-lijst -> namen + aantal secties per handleiding
- GET  /admin             -> de adminpagina (static/admin.html)
- GET/POST /admin/settings, /admin/settings/reset, /admin/models  -> instellingen
- GET  /admin/testset, POST /admin/test-een  -> testset draaien en scoren

NB: de route-paden en JSON-keys (tekst, secties, vraag, ...) zijn het contract met
de frontend en blijven bewust Nederlands.
"""

import os
import re
import json
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

import settings
from chatbot import load_manuals, generate_answer, generate_answer_stream, STOPWORDS

logger = logging.getLogger(__name__)

# De ingelezen handleidingen (gevuld bij het opstarten, in geheugen gehouden).
manuals: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lees de handleidingen één keer in bij het opstarten. Dit laadt ook het
    embedding-model (warm bij de eerste vraag) en gebruikt de schijf-cache, zodat
    een herstart snel is. Door dit hier te doen (i.p.v. bij import) blijft het
    importeren van main lichtgewicht voor tests en tooling."""
    global manuals
    manuals = load_manuals()
    yield


app = FastAPI(title="HandleidingChat", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/handleidingen", StaticFiles(directory="handleidingen"), name="handleidingen-bestanden")

_TESTSET_PATH  = os.path.join(os.path.dirname(__file__), "testset.json")
_FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), "feedback.jsonl")


class ChatRequest(BaseModel):
    tekst: str
    filter: list[str] | None = None


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/metesco-favicon.svg")
def favicon():
    return FileResponse("metesco-favicon.svg", media_type="image/svg+xml")


@app.post("/chat")
def chat(request: ChatRequest):
    return generate_answer(request.tekst, manuals, filter_names=request.filter or None)


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """Beantwoordt een vraag als Server-Sent Events, zodat de frontend het antwoord
    woord-voor-woord kan tonen. Elke regel is `data: <json>` met een event van
    generate_answer_stream (type "delta" of "final")."""
    def event_gen():
        try:
            for event in generate_answer_stream(
                request.tekst, manuals, filter_names=request.filter or None
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Fout tijdens streamen: %s", e)
            fout = {"type": "final", "tekst": "Er ging iets mis. Probeer het opnieuw.",
                    "secties": [], "opties": [], "set_filter": None}
            yield f"data: {json.dumps(fout, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class Feedback(BaseModel):
    vraag: str
    antwoord: str
    oordeel: str  # "positief" of "negatief"


@app.post("/feedback")
def feedback(item: Feedback):
    """Bewaar duim-omhoog/omlaag bij een antwoord in feedback.jsonl, zodat we later
    kunnen zien welke vragen goed of slecht beantwoord worden."""
    oordeel = item.oordeel if item.oordeel in ("positief", "negatief") else "onbekend"
    regel = {
        "tijd": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "oordeel": oordeel,
        "vraag": item.vraag,
        "antwoord": item.antwoord,
    }
    try:
        with open(_FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(regel, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Kon feedback niet opslaan: %s", e)
        raise HTTPException(status_code=500, detail="Kon feedback niet opslaan")
    return {"ok": True}


@app.get("/afbeelding")
def image(bestand: str, pagina: int, clip: str):
    """Render één figuurregio van een PDF-pagina live als PNG.

    Er wordt niets op schijf bewaard; de regio (clip = "x0,y0,x1,y1" in PDF-punten)
    wordt per verzoek uit de PDF gerenderd. De browser cachet de respons."""
    import fitz  # pymupdf

    # path traversal voorkomen: enkel bestandsnaam, geen mappen
    veilige_naam = os.path.basename(bestand)
    pad = os.path.join("handleidingen", veilige_naam)
    if not veilige_naam.lower().endswith(".pdf") or not os.path.exists(pad):
        raise HTTPException(status_code=404, detail="Bestand niet gevonden")

    try:
        coords = [float(x) for x in clip.split(",")]
        if len(coords) != 4:
            raise ValueError("clip moet 4 coördinaten hebben")
        with fitz.open(pad) as doc:
            blad = doc[pagina - 1]
            rect = fitz.Rect(coords[0] - 4, coords[1] - 4, coords[2] + 4, coords[3] + 4)
            rect = rect & blad.rect  # binnen de pagina houden
            pix = blad.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
            data = pix.tobytes("png")
    except Exception:
        raise HTTPException(status_code=404, detail="Afbeelding niet gevonden")

    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/handleidingen-lijst")
def list_manuals():
    return {
        "handleidingen": [
            {"naam": naam, "aantal_secties": len(secties)}
            for naam, secties in manuals.items()
        ]
    }


# ── Admin ──────────────────────────────────────────────────────────────────────

@app.get("/admin")
def admin_page():
    return FileResponse("static/admin.html")


@app.get("/admin/settings")
def admin_get_settings():
    return settings.get_settings()


@app.post("/admin/settings")
def admin_update_settings(new: dict):
    return settings.update_settings(new)


@app.post("/admin/settings/reset")
def admin_reset_settings():
    return settings.reset_settings()


@app.get("/admin/models")
def admin_models():
    """Lokaal beschikbare Ollama-modellen + status van de Gemini-provider.

    De adminpagina gebruikt dit om de modelkeuze te vullen en om te tonen of er
    een Gemini-API-key in de omgeving (.env) gevonden is."""
    import llm_providers

    try:
        import ollama
        antwoord = ollama.list()
        namen = [m.get("model") or m.get("name") for m in antwoord.get("models", [])]
        ollama_models = [n for n in namen if n]
        fout = None
    except Exception as e:
        ollama_models, fout = [], str(e)

    return {
        "models": ollama_models,         # behouden voor bestaande frontend-logica
        "fout": fout,
        "gemini_beschikbaar": llm_providers.gemini_available(),
        "gemini_modellen": [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ],
    }


def _load_testset() -> list[dict]:
    if not os.path.exists(_TESTSET_PATH):
        return []
    with open(_TESTSET_PATH, encoding="utf-8") as f:
        return json.load(f).get("vragen", [])


@app.get("/admin/testset")
def admin_testset():
    return {"vragen": _load_testset()}


class TestQuestion(BaseModel):
    vraag: str
    verwacht: str | None = None


def _key_tokens(tekst: str) -> list[str]:
    """Sleutelwoorden uit een tekst: alfanumerieke runs (incl. Ω, µ, accenten, getallen),
    zonder stopwoorden. Korte tokens tellen alleen mee als ze een cijfer bevatten
    (zo blijven eenheden/waarden als '10000' of '2000' behouden, maar 'de'/'is' niet)."""
    # verwijder duizendtal-/decimaalscheidingstekens tussen cijfers zodat
    # "10.000", "10,000" en "10000" als hetzelfde getal tellen
    tekst = re.sub(r"(?<=\d)[.,](?=\d)", "", tekst.lower())
    ruw = re.findall(r"[^\W_]+", tekst, re.UNICODE)
    tokens = []
    for t in ruw:
        if t in STOPWORDS:
            continue
        if len(t) >= 3 or any(c.isdigit() for c in t):
            tokens.append(t)
    return tokens


def _score_answer(antwoord: str, verwacht: str | None) -> dict:
    """Heuristische dekkingsscore: welk aandeel van de sleutelwoorden uit het
    verwachte antwoord komt terug in het gegenereerde antwoord."""
    if not verwacht or not verwacht.strip():
        return {"score": None, "oordeel": "geen-referentie", "gemist": []}

    verwacht_tokens = _key_tokens(verwacht)
    if not verwacht_tokens:
        return {"score": None, "oordeel": "geen-referentie", "gemist": []}

    antwoord_set = set(_key_tokens(antwoord))
    gemist = [t for t in dict.fromkeys(verwacht_tokens) if t not in antwoord_set]
    uniek = list(dict.fromkeys(verwacht_tokens))
    raak = len(uniek) - len(gemist)
    score = round(raak / len(uniek), 2)

    if score >= 0.7:
        oordeel = "goed"
    elif score >= 0.4:
        oordeel = "deels"
    else:
        oordeel = "mis"
    return {"score": score, "oordeel": oordeel, "gemist": gemist}


@app.post("/admin/test-een")
def admin_test_one(item: TestQuestion):
    """Draai één testvraag tegen de huidige instellingen en geef het antwoord terug."""
    resultaat = generate_answer(item.vraag, manuals, filter_names=None)
    antwoord = resultaat.get("tekst", "")
    return {
        "vraag": item.vraag,
        "verwacht": item.verwacht,
        "antwoord": antwoord,
        "scoring": _score_answer(antwoord, item.verwacht),
        "secties": [
            {
                "titel": s.get("titel"),
                "bron": s.get("bron"),
                "pagina": s.get("pagina"),
            }
            for s in resultaat.get("secties", [])
        ],
    }
