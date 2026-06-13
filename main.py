"""Webserver en HTTP-endpoints (FastAPI).

Dit is de instaplaag van de applicatie: hier draait de webserver en worden alle
URL's gedefinieerd. De inhoudelijke logica zit in chatbot.py en settings.py; dit
bestand vertaalt HTTP-verzoeken naar aanroepen daarvan en stuurt het resultaat als
JSON of bestand terug.

Bij het starten worden de handleidingen één keer ingelezen (laad_handleidingen) en
in geheugen gehouden, zodat elke vraag snel beantwoord wordt.

Endpoints:
- GET  /                  -> de chatinterface (static/index.html)
- POST /chat              -> beantwoordt een vraag (kernfunctie)
- GET  /afbeelding        -> rendert één figuur uit een PDF live als PNG
- GET  /handleidingen-lijst -> namen + aantal secties per handleiding
- GET  /admin             -> de adminpagina (static/admin.html)
- GET/POST /admin/settings, /admin/settings/reset, /admin/models  -> instellingen
- GET  /admin/testset, POST /admin/test-een  -> testset draaien en scoren
"""

import os
import re
import json

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import settings
from chatbot import laad_handleidingen, genereer_antwoord, STOPWOORDEN

app = FastAPI(title="HandleidingChat")
handleidingen = laad_handleidingen()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/handleidingen", StaticFiles(directory="handleidingen"), name="handleidingen-bestanden")

_TESTSET_PAD = os.path.join(os.path.dirname(__file__), "testset.json")


class Bericht(BaseModel):
    tekst: str
    filter: list[str] | None = None


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/metesco-favicon.svg")
def favicon():
    return FileResponse("metesco-favicon.svg", media_type="image/svg+xml")


@app.post("/chat")
def chat(bericht: Bericht):
    return genereer_antwoord(bericht.tekst, handleidingen, filter_namen=bericht.filter or None)


@app.get("/afbeelding")
def afbeelding(bestand: str, pagina: int, clip: str):
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
def lijst_handleidingen():
    return {
        "handleidingen": [
            {"naam": naam, "aantal_secties": len(secties)}
            for naam, secties in handleidingen.items()
        ]
    }


# ── Admin ──────────────────────────────────────────────────────────────────────

@app.get("/admin")
def admin_pagina():
    return FileResponse("static/admin.html")


@app.get("/admin/settings")
def admin_get_settings():
    return settings.get_instellingen()


@app.post("/admin/settings")
def admin_update_settings(nieuw: dict):
    return settings.update_instellingen(nieuw)


@app.post("/admin/settings/reset")
def admin_reset_settings():
    return settings.reset_instellingen()


@app.get("/admin/models")
def admin_models():
    """Lijst van lokaal beschikbare Ollama-modellen."""
    try:
        import ollama
        antwoord = ollama.list()
        namen = [m.get("model") or m.get("name") for m in antwoord.get("models", [])]
        return {"models": [n for n in namen if n]}
    except Exception as e:
        return {"models": [], "fout": str(e)}


def _laad_testset() -> list[dict]:
    if not os.path.exists(_TESTSET_PAD):
        return []
    with open(_TESTSET_PAD, encoding="utf-8") as f:
        return json.load(f).get("vragen", [])


@app.get("/admin/testset")
def admin_testset():
    return {"vragen": _laad_testset()}


class TestVraag(BaseModel):
    vraag: str
    verwacht: str | None = None


def _belangrijke_tokens(tekst: str) -> list[str]:
    """Sleutelwoorden uit een tekst: alfanumerieke runs (incl. Ω, µ, accenten, getallen),
    zonder stopwoorden. Korte tokens tellen alleen mee als ze een cijfer bevatten
    (zo blijven eenheden/waarden als '10000' of '2000' behouden, maar 'de'/'is' niet)."""
    # verwijder duizendtal-/decimaalscheidingstekens tussen cijfers zodat
    # "10.000", "10,000" en "10000" als hetzelfde getal tellen
    tekst = re.sub(r"(?<=\d)[.,](?=\d)", "", tekst.lower())
    ruw = re.findall(r"[^\W_]+", tekst, re.UNICODE)
    tokens = []
    for t in ruw:
        if t in STOPWOORDEN:
            continue
        if len(t) >= 3 or any(c.isdigit() for c in t):
            tokens.append(t)
    return tokens


def _scoor_antwoord(antwoord: str, verwacht: str | None) -> dict:
    """Heuristische dekkingsscore: welk aandeel van de sleutelwoorden uit het
    verwachte antwoord komt terug in het gegenereerde antwoord."""
    if not verwacht or not verwacht.strip():
        return {"score": None, "oordeel": "geen-referentie", "gemist": []}

    verwacht_tokens = _belangrijke_tokens(verwacht)
    if not verwacht_tokens:
        return {"score": None, "oordeel": "geen-referentie", "gemist": []}

    antwoord_set = set(_belangrijke_tokens(antwoord))
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
def admin_test_een(item: TestVraag):
    """Draai één testvraag tegen de huidige instellingen en geef het antwoord terug."""
    resultaat = genereer_antwoord(item.vraag, handleidingen, filter_namen=None)
    antwoord = resultaat.get("tekst", "")
    return {
        "vraag": item.vraag,
        "verwacht": item.verwacht,
        "antwoord": antwoord,
        "scoring": _scoor_antwoord(antwoord, item.verwacht),
        "secties": [
            {
                "titel": s.get("titel"),
                "bron": s.get("bron"),
                "pagina": s.get("pagina"),
            }
            for s in resultaat.get("secties", [])
        ],
    }
