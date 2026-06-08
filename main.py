import os
import re
import json

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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


@app.post("/chat")
def chat(bericht: Bericht):
    return genereer_antwoord(bericht.tekst, handleidingen, filter_namen=bericht.filter or None)


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
