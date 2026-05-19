import os
import re
import logging
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

HANDLEIDINGEN_DIR = os.path.join(os.path.dirname(__file__), "handleidingen")

STOPWOORDEN = {
    "de", "het", "een", "en", "of", "is", "ik", "je", "jij", "mijn", "hoe",
    "wat", "waar", "wanneer", "waarom", "kan", "kun", "wil", "moet", "mag",
    "dat", "dit", "die", "deze", "met", "van", "voor", "naar", "in", "op",
    "aan", "uit", "over", "bij", "om", "te", "zijn", "heeft", "hebben",
    "niet", "ook", "maar", "dan", "als", "er", "nog", "al", "zo", "wel",
    "via", "door", "wordt", "worden", "werd", "was", "bent", "ben",
    "had", "zal", "zou", "ga", "gaan", "ging",
}

FUZZY_DREMPEL   = 82
MIN_WOORDLENGTE = 4

BEGROETINGEN = {"hoi", "hallo", "hey", "hi", "goedemorgen", "goedemiddag", "goedenavond"}
BEDANKJES    = {"bedankt", "dankjewel", "dank", "dankje", "thanks"}
AFSCHEID     = {"doei", "dag", "bye", "ciao"}

# ── Embeddings model (lazy geladen) ───────────────────────────────────────────
_model = None

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Laden van embedding model...")
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        logger.info("Embedding model geladen.")
    return _model


@dataclass
class Sectie:
    titel: str
    inhoud: str
    handleiding_naam: str
    bestand_naam: str = ""
    pagina: int | None = None
    _tokens: set[str]     = field(default_factory=set, repr=False)
    _embedding: np.ndarray | None = field(default=None, repr=False)


# ── Laden ─────────────────────────────────────────────────────────────────────

def laad_handleidingen() -> dict[str, list[Sectie]]:
    # wordt ingevuld na definitie van de parsers
    handleidingen: dict[str, list[Sectie]] = {}
    if not os.path.exists(HANDLEIDINGEN_DIR):
        return handleidingen

    parsers = {
        ".md":   _parseer_md,
        ".docx": _parseer_docx,
        ".pdf":  _parseer_pdf,
    }

    for bestand in sorted(os.listdir(HANDLEIDINGEN_DIR)):
        ext  = os.path.splitext(bestand)[1].lower()
        if ext not in parsers:
            continue
        pad  = os.path.join(HANDLEIDINGEN_DIR, bestand)
        naam = os.path.splitext(bestand)[0].replace("_", " ").replace("-", " ").title()
        try:
            secties = parsers[ext](pad, naam, bestand)
        except Exception as e:
            logger.warning("Kon %s niet inladen: %s", bestand, e)
            continue
        # slechte secties weggooien: lege inhoud, te korte titel of te weinig inhoud
        secties = [
            s for s in secties
            if s.inhoud.strip()
            and len(s.titel.strip()) >= 3
            and len(s.inhoud.strip()) >= 80
        ]
        for s in secties:
            s._tokens = _trefwoorden(s.titel + " " + s.inhoud)
        handleidingen[naam] = secties
        logger.info("Geladen: %s (%d secties)", naam, len(secties))

    _bereken_embeddings(handleidingen)
    return handleidingen


# ── Markdown parser ───────────────────────────────────────────────────────────

def _parseer_md(pad: str, naam: str, bestand: str) -> list[Sectie]:
    with open(pad, encoding="utf-8") as f:
        return _parseer_secties(f.read(), naam, bestand)


# ── Word parser (.docx) ───────────────────────────────────────────────────────

def _parseer_docx(pad: str, naam: str, bestand: str) -> list[Sectie]:
    from docx import Document
    doc = Document(pad)

    secties: list[Sectie] = []
    huidige_titel = "Algemeen"
    huidige_regels: list[str] = []

    for para in doc.paragraphs:
        tekst = para.text.strip()
        if not tekst:
            continue
        stijl = para.style.name
        is_heading = (
            stijl.startswith("Heading")
            or stijl.startswith("Kop")
            or stijl in {"Title", "Titel", "Subtitle", "Subtitel"}
        )
        if is_heading:
            if huidige_regels:
                secties.append(Sectie(
                    titel=huidige_titel,
                    inhoud="\n".join(huidige_regels).strip(),
                    handleiding_naam=naam,
                    bestand_naam=bestand,
                ))
            huidige_titel = tekst
            huidige_regels = []
        else:
            huidige_regels.append(tekst)

    if huidige_regels:
        secties.append(Sectie(
            titel=huidige_titel,
            inhoud="\n".join(huidige_regels).strip(),
            handleiding_naam=naam,
            bestand_naam=bestand,
        ))
    return secties


# ── PDF parser ────────────────────────────────────────────────────────────────

def _parseer_pdf(pad: str, naam: str, bestand: str) -> list[Sectie]:
    import fitz  # pymupdf

    doc = fitz.open(pad)
    secties: list[Sectie] = []
    huidige_titel = "Algemeen"
    huidige_regels: list[str] = []
    huidige_pagina = 1

    # Bepaal de meest voorkomende fontgrootte (= body-tekst)
    alle_groottes: list[float] = []
    for pagina in doc:
        for blok in pagina.get_text("dict")["blocks"]:
            if blok.get("type") != 0:
                continue
            for regel in blok.get("lines", []):
                for span in regel.get("spans", []):
                    alle_groottes.append(round(span.get("size", 0), 1))

    body_grootte = max(set(alle_groottes), key=alle_groottes.count) if alle_groottes else 11.0

    for pagina_idx, pagina in enumerate(doc):
        for blok in pagina.get_text("dict")["blocks"]:
            if blok.get("type") != 0:
                continue
            for regel in blok.get("lines", []):
                regel_tekst = "".join(s.get("text", "") for s in regel.get("spans", [])).strip()
                if not regel_tekst:
                    continue

                # Heading als: groter dan body-tekst OF bold, en niet te lang
                max_grootte = max((s.get("size", 0) for s in regel.get("spans", [])), default=0)
                is_bold     = any(s.get("flags", 0) & 16 for s in regel.get("spans", []))
                is_heading  = (max_grootte > body_grootte + 1 or is_bold) and len(regel_tekst) < 100

                if is_heading:
                    if huidige_regels:
                        secties.append(Sectie(
                            titel=huidige_titel,
                            inhoud="\n".join(huidige_regels).strip(),
                            handleiding_naam=naam,
                            bestand_naam=bestand,
                            pagina=huidige_pagina,
                        ))
                    huidige_titel = regel_tekst
                    huidige_regels = []
                    huidige_pagina = pagina_idx + 1
                else:
                    huidige_regels.append(regel_tekst)

    if huidige_regels:
        secties.append(Sectie(
            titel=huidige_titel,
            inhoud="\n".join(huidige_regels).strip(),
            handleiding_naam=naam,
            bestand_naam=bestand,
            pagina=huidige_pagina,
        ))
    return secties


def _parseer_secties(tekst: str, handleiding_naam: str, bestand_naam: str = "") -> list[Sectie]:
    secties: list[Sectie] = []
    huidige_titel = "Algemeen"
    huidige_regels: list[str] = []

    for regel in tekst.splitlines():
        if regel.startswith("## "):
            if huidige_regels:
                secties.append(Sectie(
                    titel=huidige_titel,
                    inhoud="\n".join(huidige_regels).strip(),
                    handleiding_naam=handleiding_naam,
                    bestand_naam=bestand_naam,
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
            bestand_naam=bestand_naam,
        ))
    return secties


# ── Embeddings ────────────────────────────────────────────────────────────────

def _bereken_embeddings(handleidingen: dict[str, list[Sectie]]) -> None:
    alle_secties = [s for secties in handleidingen.values() for s in secties]
    if not alle_secties:
        return

    teksten = [f"{s.titel}\n{s.inhoud}" for s in alle_secties]
    model   = _get_model()
    vecs    = model.encode(teksten, convert_to_numpy=True, show_progress_bar=False)
    # normaliseer voor cosine-similariteit via dot-product
    norms   = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs    = vecs / np.maximum(norms, 1e-10)

    for sectie, vec in zip(alle_secties, vecs):
        sectie._embedding = vec

    logger.info("Embeddings berekend voor %d secties.", len(alle_secties))


def _cosine_scores(
    vraag_vec: np.ndarray,
    secties: list[Sectie],
) -> list[float]:
    matrix = np.stack([s._embedding for s in secties])
    return (matrix @ vraag_vec).tolist()


# ── Fuzzy fallback ────────────────────────────────────────────────────────────

def _trefwoorden(tekst: str) -> set[str]:
    woorden = re.findall(r"[a-zA-ZÀ-ÿ]+", tekst.lower())
    return {w for w in woorden if w not in STOPWOORDEN and len(w) >= MIN_WOORDLENGTE}


def _fuzzy_score(sectie: Sectie, zoekwoorden: set[str]) -> float:
    if not zoekwoorden:
        return 0.0

    token_lijst  = list(sectie._tokens)
    titel_str    = sectie.titel.lower()
    titel_tokens = _trefwoorden(sectie.titel)
    totaal = 0.0

    for zoek in zoekwoorden:
        # 1. Exacte token-match
        if zoek in sectie._tokens:
            totaal += 3.0 if zoek in titel_tokens else 1.0
            continue

        # 2. Partial-ratio tegen volledige titeltekst — vangt samengestelde woorden
        #    bv. "beschrijving" in "opdrachtbeschrijving"
        pr_titel = fuzz.partial_ratio(zoek, titel_str)
        if pr_titel >= FUZZY_DREMPEL:
            totaal += (pr_titel / 100.0) * 3.0
            continue

        # 3. Fuzzy token-match (typfouten)
        beste = max((fuzz.ratio(zoek, t) for t in token_lijst), default=0)
        if beste >= FUZZY_DREMPEL:
            in_titel = any(fuzz.ratio(zoek, t) >= FUZZY_DREMPEL for t in titel_tokens)
            totaal += (beste / 100.0) * (3.0 if in_titel else 1.0)

    return totaal


# ── Zoeken ─────────────────────────────────────────────────────────────────────

def zoek_secties(
    vraag: str,
    handleidingen: dict[str, list[Sectie]],
    filter_namen: list[str] | None = None,
    top_n: int = 2,
) -> list[Sectie]:
    kandidaten = [
        s
        for naam, secties in handleidingen.items()
        if not filter_namen or naam in filter_namen
        for s in secties
    ]
    if not kandidaten:
        return []

    zoekwoorden = _trefwoorden(vraag)

    # ── Semantisch zoeken (primair) ──
    secties_met_embedding = [s for s in kandidaten if s._embedding is not None]
    if secties_met_embedding:
        model     = _get_model()
        vraag_vec = model.encode([vraag], convert_to_numpy=True, show_progress_bar=False)[0]
        vraag_vec = vraag_vec / max(np.linalg.norm(vraag_vec), 1e-10)
        cos_scores = _cosine_scores(vraag_vec, secties_met_embedding)

        # Hybride score: cosine + genormaliseerde fuzzy-boost voor titelmatch
        fuz_max = max(len(zoekwoorden) * 3, 1)
        gecombineerd = []
        for cos, sectie in zip(cos_scores, secties_met_embedding):
            fuz   = _fuzzy_score(sectie, zoekwoorden)
            score = cos + (fuz / fuz_max) * 0.35
            gecombineerd.append((score, cos, sectie))

        gecombineerd.sort(key=lambda x: x[0], reverse=True)
        # verwerp matches waarbij zowel cosine als hybride score te laag zijn
        resultaat = [s for score, cos, s in gecombineerd[:top_n] if cos > 0.42]
        if resultaat:
            return resultaat

    # ── Fuzzy fallback (als embeddings ontbreken) ──
    gescoord = [(s, _fuzzy_score(s, zoekwoorden)) for s in kandidaten]
    gescoord = [(s, sc) for s, sc in gescoord if sc > 0]
    gescoord.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in gescoord[:top_n]]


# ── Antwoord genereren ────────────────────────────────────────────────────────

def _detecteer_intentie(bericht: str) -> str:
    tekst   = bericht.lower().strip()
    woorden = set(tekst.split())
    if woorden & BEGROETINGEN:  return "begroeting"
    if woorden & BEDANKJES:     return "bedankje"
    if woorden & AFSCHEID:      return "afscheid"
    if any(w in tekst for w in ["help", "wat kun jij", "wat kan jij", "hoe werkt"]):
        return "help"
    return "vraag"


def genereer_antwoord(
    bericht: str,
    handleidingen: dict[str, list[Sectie]],
    filter_namen: list[str] | None = None,
) -> dict:
    intentie = _detecteer_intentie(bericht)

    if intentie == "begroeting":
        return {"tekst": "Hoi! Ik ben hier om u te helpen. Stel me een vraag over een van de beschikbare handleidingen en ik zoek het voor je op.", "secties": []}
    if intentie == "bedankje":
        return {"tekst": "Graag gedaan! Heb je nog andere vragen?", "secties": []}
    if intentie == "afscheid":
        return {"tekst": "Tot ziens! Als je weer vragen hebt, staan de handleidingen klaar.", "secties": []}
    if intentie == "help":
        beschikbaar = ", ".join(handleidingen.keys()) if handleidingen else "geen handleidingen geladen"
        return {
            "tekst": f"Ik zoek in de beschikbare handleidingen op basis van jouw vraag.\n\n**Beschikbare handleidingen:** {beschikbaar}",
            "secties": [],
        }

    gevonden = zoek_secties(bericht, handleidingen, filter_namen=filter_namen)

    if not gevonden:
        return {
            "tekst": "Ik kon geen relevante informatie vinden. Probeer het anders te formuleren.",
            "secties": [],
        }

    return {
        "tekst": f"Ik vond **{len(gevonden)}** relevante sectie(s) voor jouw vraag:",
        "secties": [
            {
                "titel": s.titel,
                "inhoud": s.inhoud,
                "bron": s.handleiding_naam,
                "bestand": s.bestand_naam,
                "pagina": s.pagina,
            }
            for s in gevonden
        ],
    }
