import os
import re
from dataclasses import dataclass

HANDLEIDINGEN_DIR = os.path.join(os.path.dirname(__file__), "handleidingen")

STOPWOORDEN = {
    "de", "het", "een", "en", "of", "is", "ik", "je", "jij", "mijn", "hoe",
    "wat", "waar", "wanneer", "waarom", "kan", "kun", "wil", "moet", "mag",
    "dat", "dit", "die", "deze", "met", "van", "voor", "naar", "in", "op",
    "aan", "uit", "over", "bij", "om", "te", "zijn", "heeft", "hebben",
    "niet", "ook", "maar", "dan", "als", "er", "nog", "al", "zo", "wel",
}

BEGROETINGEN = {"hoi", "hallo", "hey", "hi", "goedemorgen", "goedemiddag", "goedenavond"}
BEDANKJES = {"bedankt", "dankjewel", "dank", "dankje", "thanks"}
AFSCHEID = {"doei", "dag", "tot ziens", "bye", "ciao"}


@dataclass
class Sectie:
    titel: str
    inhoud: str
    handleiding_naam: str
    score: float = 0.0


def laad_handleidingen() -> dict[str, list[Sectie]]:
    handleidingen = {}
    if not os.path.exists(HANDLEIDINGEN_DIR):
        return handleidingen

    for bestand in os.listdir(HANDLEIDINGEN_DIR):
        if not bestand.endswith(".md"):
            continue
        pad = os.path.join(HANDLEIDINGEN_DIR, bestand)
        naam = bestand.replace(".md", "").replace("_", " ").title()
        with open(pad, encoding="utf-8") as f:
            tekst = f.read()
        handleidingen[naam] = _parseer_secties(tekst, naam)

    return handleidingen


def _parseer_secties(tekst: str, handleiding_naam: str) -> list[Sectie]:
    secties = []
    huidige_titel = "Algemeen"
    huidige_regels: list[str] = []

    for regel in tekst.splitlines():
        if regel.startswith("## "):
            if huidige_regels:
                secties.append(Sectie(
                    titel=huidige_titel,
                    inhoud="\n".join(huidige_regels).strip(),
                    handleiding_naam=handleiding_naam,
                ))
            huidige_titel = regel.lstrip("# ").strip()
            huidige_regels = []
        elif regel.startswith("# "):
            continue
        else:
            huidige_regels.append(regel)

    if huidige_regels:
        secties.append(Sectie(
            titel=huidige_titel,
            inhoud="\n".join(huidige_regels).strip(),
            handleiding_naam=handleiding_naam,
        ))

    return secties


def _trefwoorden(tekst: str) -> set[str]:
    woorden = re.findall(r"[a-zA-ZÀ-ÿ]+", tekst.lower())
    return {w for w in woorden if w not in STOPWOORDEN and len(w) > 2}


def _score_sectie(sectie: Sectie, zoekwoorden: set[str]) -> float:
    if not zoekwoorden:
        return 0.0

    titel_woorden = _trefwoorden(sectie.titel)
    inhoud_woorden = _trefwoorden(sectie.inhoud)

    titel_hits = len(zoekwoorden & titel_woorden)
    inhoud_hits = len(zoekwoorden & inhoud_woorden)

    # Titel-match telt zwaarder
    return titel_hits * 3 + inhoud_hits


def zoek_secties(vraag: str, handleidingen: dict[str, list[Sectie]], top_n: int = 2) -> list[Sectie]:
    zoekwoorden = _trefwoorden(vraag)
    alle_secties = [s for secties in handleidingen.values() for s in secties]

    gescoord = []
    for sectie in alle_secties:
        score = _score_sectie(sectie, zoekwoorden)
        if score > 0:
            gescoord.append((score, sectie))

    gescoord.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in gescoord[:top_n]]


def _detecteer_intentie(bericht: str) -> str:
    tekst = bericht.lower().strip()
    woorden = set(tekst.split())

    if woorden & BEGROETINGEN:
        return "begroeting"
    if woorden & BEDANKJES:
        return "bedankje"
    if woorden & AFSCHEID:
        return "afscheid"
    if any(w in tekst for w in ["help", "wat kun jij", "wat kan jij", "wat doe jij", "hoe werkt"]):
        return "help"
    return "vraag"


def genereer_antwoord(bericht: str, handleidingen: dict[str, list[Sectie]]) -> dict:
    intentie = _detecteer_intentie(bericht)

    if intentie == "begroeting":
        return {
            "tekst": "Hoi! Ik ben de HandleidingBot. Stel me een vraag over een van de beschikbare handleidingen en ik zoek het voor je op.",
            "secties": [],
        }

    if intentie == "bedankje":
        return {
            "tekst": "Graag gedaan! Heb je nog andere vragen?",
            "secties": [],
        }

    if intentie == "afscheid":
        return {
            "tekst": "Tot ziens! Als je weer vragen hebt, staan de handleidingen klaar.",
            "secties": [],
        }

    if intentie == "help":
        beschikbaar = ", ".join(handleidingen.keys()) if handleidingen else "geen handleidingen geladen"
        return {
            "tekst": (
                "Ik kan je helpen door te zoeken in beschikbare handleidingen. "
                f"Stel gewoon een vraag, bijvoorbeeld: *'Hoe verbind ik met Eduroam?'*\n\n"
                f"**Beschikbare handleidingen:** {beschikbaar}"
            ),
            "secties": [],
        }

    gevonden = zoek_secties(bericht, handleidingen)

    if not gevonden:
        return {
            "tekst": (
                "Ik kon geen relevante informatie vinden voor jouw vraag. "
                "Probeer het anders te formuleren of vraag naar een specifiek onderwerp."
            ),
            "secties": [],
        }

    return {
        "tekst": f"Ik vond **{len(gevonden)}** relevante sectie(s) voor jouw vraag:",
        "secties": [
            {
                "titel": s.titel,
                "inhoud": s.inhoud,
                "bron": s.handleiding_naam,
            }
            for s in gevonden
        ],
    }
