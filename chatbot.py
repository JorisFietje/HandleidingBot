import os
import re
import logging
from dataclasses import dataclass, field
from urllib.parse import quote

import settings

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

ENGELSE_STOPWOORDEN = {
    "the", "and", "for", "are", "was", "were", "this", "that", "with",
    "have", "from", "they", "will", "been", "their", "when", "your",
    "can", "also", "use", "using", "used", "call", "visit", "contact",
    "press", "select", "display", "function", "button", "connect",
}

FUZZY_DREMPEL   = 82
MIN_WOORDLENGTE = 4

# Figuren smaller/lager dan dit (in PDF-punten) zijn meestal logo's/iconen → overslaan.
MIN_AFBEELDING_PT = 80
# Maximaal aantal afbeeldingen dat we per antwoord tonen.
MAX_AFBEELDINGEN  = 4

# Index van figuur-bijschriften per PDF: {bestand: {nummer: (pagina, bijschrift_y0)}}.
# Gevuld tijdens het inladen, zodat een tekstverwijzing als "afbeelding 17" naar de
# juiste pagina kan worden herleid — ook als die figuur op een vervolgpagina staat.
_FIGUUR_INDEX: dict[str, dict[int, tuple[int, float]]] = {}
# Herkent bijschriften als "Afbeelding 16." of "Figure 7" (begin van een regel).
_BIJSCHRIFT_RE = re.compile(r"^(?:afbeelding|figure|fig\.?)\s+(\d+)\b", re.IGNORECASE)
# Herkent een verwijzing in de lopende tekst, bv. "zie afbeelding 17".
_VERWIJZING_RE = re.compile(r"(?:afbeelding|figure|fig\.?)\s*(\d+)", re.IGNORECASE)

BEGROETINGEN = {"hoi", "hallo", "hey", "hi", "goedemorgen", "goedemiddag", "goedenavond"}
BEDANKJES    = {"bedankt", "dankjewel", "dank", "dankje", "thanks"}
AFSCHEID     = {"doei", "dag", "bye", "ciao"}

TOPIC_OPTIES = [
    "Installatie",
    "Storing of foutcode",
    "Onderhoud & reiniging",
    "Technische specificaties",
    "Andere handleiding",
]

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
    eind_pagina: int | None = None
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
        # slechte secties weggooien: lege inhoud, te korte titel, te weinig inhoud,
        # of inhoud die grotendeels uit niet-letters bestaat (inhoudsopgave, nummers)
        def _is_goede_sectie(s: "Sectie") -> bool:
            inhoud = s.inhoud.strip()
            if not inhoud or len(s.titel.strip()) < 3 or len(inhoud) < 80:
                return False
            letters = sum(c.isalpha() for c in inhoud)
            return (letters / len(inhoud)) >= 0.40

        secties = [s for s in secties if _is_goede_sectie(s)]

        # Bepaal per PDF-sectie het figuur-paginabereik: een sectie 'bezit' de
        # pagina's tot aan de eerstvolgende behouden sectie die op een látere pagina
        # begint. Zo worden ook figuren op vervolgpagina's meegenomen, ook als een
        # tussenliggende mini-sectie is weggevallen of als meerdere secties op
        # dezelfde pagina beginnen. De laatste paginagroep houdt de door de parser
        # bepaalde eind_pagina (inhoud die er echt staat).
        pdf_secties = [s for s in secties if s.pagina is not None]
        if pdf_secties:
            distinct = sorted({s.pagina for s in pdf_secties})
            volgende_groter = {
                p: (distinct[i + 1] if i + 1 < len(distinct) else None)
                for i, p in enumerate(distinct)
            }
            for s in pdf_secties:
                ng = volgende_groter.get(s.pagina)
                if ng is not None:
                    s.eind_pagina = max(s.pagina, ng - 1)

        for s in secties:
            s._tokens = _trefwoorden(s.titel + " " + s.inhoud)
        handleidingen[naam] = secties
        logger.info("Geladen: %s (%d secties)", naam, len(secties))

    _bereken_embeddings(handleidingen)
    return handleidingen


# ── Tekst opschonen ───────────────────────────────────────────────────────────

# Private Use Area (U+E000–U+F8FF): icoon-glyphs uit de symboolfonts van de
# handleidingen (knoppen, ™/©, waarschuwings- en aansluitmarkers). Die hebben geen
# leesbare Unicode-betekenis en tonen als een vervang-teken. De PDF heeft er geen
# Unicode-mapping voor, dus de exacte knopnaam (bv. "GO") is niet uit de tekst te
# halen — die zit alleen in de glyph-vorm. We vervangen zo'n glyph daarom door een
# neutrale placeholder, zodat duidelijk blijft dát er een knop ingedrukt moet worden.
_PUA_RE = re.compile("[\uE000-\uF8FF]+")

_GLYPH_PLACEHOLDER = "[knop]"

def _schoon_glyphs(tekst: str) -> str:
    if not tekst:
        return tekst
    tekst = _PUA_RE.sub(_GLYPH_PLACEHOLDER, tekst)
    tekst = re.sub(r"[ \t]+([.,;:!?])", r"\1", tekst)  # spatie vóór leesteken weg
    tekst = re.sub(r"[ \t]{2,}", " ", tekst)           # dubbele spaties samenvoegen
    return tekst.strip()


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
    huidige_eind_pagina = 1

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

    figuur_index: dict[int, tuple[int, float]] = {}

    for pagina_idx, pagina in enumerate(doc):
        for blok in pagina.get_text("dict")["blocks"]:
            if blok.get("type") != 0:
                continue
            for regel in blok.get("lines", []):
                regel_tekst = "".join(s.get("text", "") for s in regel.get("spans", [])).strip()
                if not regel_tekst:
                    continue

                # Figuur-bijschrift onthouden (nummer → pagina + y-positie van het bijschrift)
                m = _BIJSCHRIFT_RE.match(regel_tekst)
                if m:
                    nummer = int(m.group(1))
                    y0 = regel.get("bbox", [0, 0, 0, 0])[1]
                    figuur_index.setdefault(nummer, (pagina_idx + 1, y0))

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
                            eind_pagina=huidige_eind_pagina,
                        ))
                    huidige_titel = regel_tekst
                    huidige_regels = []
                    huidige_pagina = pagina_idx + 1
                    huidige_eind_pagina = pagina_idx + 1
                else:
                    huidige_regels.append(regel_tekst)
                    huidige_eind_pagina = pagina_idx + 1

    if huidige_regels:
        secties.append(Sectie(
            titel=huidige_titel,
            inhoud="\n".join(huidige_regels).strip(),
            handleiding_naam=naam,
            bestand_naam=bestand,
            pagina=huidige_pagina,
            eind_pagina=huidige_eind_pagina,
        ))

    _FIGUUR_INDEX[bestand] = figuur_index
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

def _detecteer_taal(tekst: str) -> str:
    woorden = re.findall(r"[a-zA-Z]+", tekst.lower())
    if not woorden:
        return "onbekend"
    nl = sum(1 for w in woorden if w in STOPWOORDEN)
    en = sum(1 for w in woorden if w in ENGELSE_STOPWOORDEN)
    if nl > en:
        return "nl"
    if en > nl:
        return "en"
    return "onbekend"


def _trefwoorden(tekst: str) -> set[str]:
    woorden = re.findall(r"[a-zA-Z0-9À-ÿ]+", tekst.lower())
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


# ── Query-uitbreiding ─────────────────────────────────────────────────────────

def _uitbreid_vraag(vraag: str) -> str:
    """Voeg zoektermen toe voor error-code-vragen zodat de foutcodes-sectie beter gevonden wordt."""
    if re.search(r'\berr(?:or)?\s*\d', vraag, re.IGNORECASE) or \
       re.search(r'\bfout(?:code)?\b', vraag, re.IGNORECASE):
        return vraag + " foutcode fout oplossing zelftest tabel err"
    return vraag


# Een reeks van 3+ keer hetzelfde leesteken in de vraag (bv. "-----" of "....") is
# een displaypatroon waar de gebruiker naar vraagt. De handleidingen beschrijven dat
# letterlijk (bv. "streepjes (-----)"), dus daar matchen we letterlijk op.
_SYMBOOL_RUN_RE = re.compile(r"([^\w\s])\1{2,}")

def _symbool_run_patronen(vraag: str) -> list[re.Pattern]:
    chars = {m.group(1) for m in _SYMBOOL_RUN_RE.finditer(vraag)}
    return [re.compile(re.escape(c) + r"{3,}") for c in chars]


# Hoe een symboolreeks in de handleidingen meestal in woorden heet. Gebruikt om de
# vraag aan het LLM te verduidelijken: het model koppelt kale "-----" niet vanzelf
# aan "streepjes", terwijl de handleiding het zo beschrijft.
_SYMBOOL_WOORD = {"-": "streepjes", ".": "puntjes", "_": "liggende streepjes"}

def _verduidelijk_symbolen(vraag: str) -> str:
    """Vervang een symboolreeks in de vraag door 'woord (reeks)', zodat het LLM
    'wat betekent -----' koppelt aan 'streepjes' in de handleiding. Het model
    struikelt over een kale reeks; met het woord ervoor antwoordt het wél."""
    def vervang(m: re.Match) -> str:
        woord = _SYMBOOL_WOORD.get(m.group(1))
        return f"{woord} ({m.group(0)})" if woord else m.group(0)
    return _SYMBOOL_RUN_RE.sub(vervang, vraag)


# ── Zoeken ─────────────────────────────────────────────────────────────────────

def _model_index(handleidingen: dict[str, list[Sectie]]) -> dict[str, set[str]]:
    """Bouw {modeltoken: {handleidingnaam}} uit de handleidingnamen.

    Modeltokens zijn de alfanumerieke delen van een naam die een cijfer bevatten
    en minstens 3 tekens lang zijn (bv. '1736', '789', '1654b', 'ti400'). Zo
    vallen losse aanduidingen als '2' uit '6500 2' of woorden als 'Fc' weg."""
    idx: dict[str, set[str]] = {}
    for naam in handleidingen:
        for tok in re.findall(r"[A-Za-z0-9]+", naam.lower()):
            if len(tok) >= 3 and any(c.isdigit() for c in tok):
                idx.setdefault(tok, set()).add(naam)
    return idx


def _detecteer_model_filter(
    vraag: str, handleidingen: dict[str, list[Sectie]]
) -> list[str] | None:
    """Als de vraag een modelnummer noemt dat bij een handleiding hoort, geef die
    handleiding(en) terug zodat de zoekopdracht zich daarop richt. Anders None."""
    idx = _model_index(handleidingen)
    matches: set[str] = set()
    for tok in re.findall(r"[A-Za-z0-9]+", vraag.lower()):
        if tok in idx:
            matches |= idx[tok]
    return list(matches) if matches else None


def zoek_secties(
    vraag: str,
    handleidingen: dict[str, list[Sectie]],
    filter_namen: list[str] | None = None,
    top_n: int = 2,
) -> list[Sectie]:
    # Geen handmatig filter? Probeer op modelnummer in de vraag te routeren, zodat
    # een vraag over een 789 niet uit de handleiding van een ander model wordt
    # beantwoord.
    if not filter_namen:
        filter_namen = _detecteer_model_filter(vraag, handleidingen)

    kandidaten = [
        s
        for naam, secties in handleidingen.items()
        if not filter_namen or naam in filter_namen
        for s in secties
    ]
    if not kandidaten:
        return []

    zoekwoorden = _trefwoorden(vraag)
    uitgebreide_vraag = _uitbreid_vraag(vraag)

    # ── Semantisch zoeken (primair) ──
    secties_met_embedding = [s for s in kandidaten if s._embedding is not None]
    if secties_met_embedding:
        model     = _get_model()
        vraag_vec = model.encode([uitgebreide_vraag], convert_to_numpy=True, show_progress_bar=False)[0]
        vraag_vec = vraag_vec / max(np.linalg.norm(vraag_vec), 1e-10)
        cos_scores = _cosine_scores(vraag_vec, secties_met_embedding)

        # Hybride score: cosine + genormaliseerde fuzzy-boost voor titelmatch
        fuz_max = max(len(zoekwoorden) * 3, 1)
        gecombineerd = []
        for cos, sectie in zip(cos_scores, secties_met_embedding):
            fuz   = _fuzzy_score(sectie, zoekwoorden)
            score = cos + (fuz / fuz_max) * 0.35
            gecombineerd.append((score, cos, sectie))

        # Extra boost voor oplossings-/foutcodes-secties bij error-queries
        if re.search(r'\berr\b|\bfout', uitgebreide_vraag, re.IGNORECASE):
            relevante_titels = {'oplossing', 'foutcode', 'fout', 'storing', 'probleem', 'solution', 'error'}
            gecombineerd = [
                (score + (0.20 if any(w in s.titel.lower() for w in relevante_titels) else 0), cos, s)
                for score, cos, s in gecombineerd
            ]

        # Sterke boost als de vraag een symboolreeks bevat (bv. "-----") die letterlijk
        # in een sectie voorkomt — handleidingen beschrijven displaypatronen zo.
        sym_patronen = _symbool_run_patronen(vraag)
        if sym_patronen:
            gecombineerd = [
                (score + (0.50 if any(p.search(s.inhoud) for p in sym_patronen) else 0), cos, s)
                for score, cos, s in gecombineerd
            ]

        gecombineerd.sort(key=lambda x: x[0], reverse=True)
        # Drempel op hybride score zodat sterke fuzzy-matches de threshold kunnen halen
        inst = settings.get_instellingen()
        drempel = inst["drempel_filter"] if filter_namen else inst["drempel_globaal"]
        kandidaten = [(score, cos, s) for score, cos, s in gecombineerd if score > drempel]

        # taalfilter: prefereer secties in dezelfde taal als de vraag
        vraag_taal = _detecteer_taal(vraag)
        if vraag_taal != "onbekend":
            taal_match = [(sc, cos, s) for sc, cos, s in kandidaten
                          if _detecteer_taal(s.inhoud) == vraag_taal]
            if taal_match:
                kandidaten = taal_match

        # dedupliceer: verwijder secties die te veel lijken op een eerder gekozen sectie
        resultaat: list[Sectie] = []
        for _, _, s in kandidaten:
            if len(resultaat) >= top_n:
                break
            is_duplicaat = any(
                s.titel.strip().lower() == r.titel.strip().lower()
                or fuzz.ratio(s.inhoud[:300], r.inhoud[:300]) > 88
                for r in resultaat
            )
            if not is_duplicaat:
                resultaat.append(s)

        if resultaat:
            return resultaat

    # ── Fuzzy fallback (als embeddings ontbreken) ──
    gescoord = [(s, _fuzzy_score(s, zoekwoorden)) for s in kandidaten]
    gescoord = [(s, sc) for s, sc in gescoord if sc > 0]
    gescoord.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in gescoord[:top_n]]


# ── LLM-antwoord genereren via Ollama ─────────────────────────────────────────

def _genereer_llm_antwoord(
    vraag: str,
    secties: list[Sectie],
    model: str | None = None,
) -> str:
    try:
        import ollama
    except ImportError:
        return "⚠️ Ollama-pakket niet gevonden. Voer `pip install ollama` uit."

    inst = settings.get_instellingen()
    gebruik_model = model or inst["model"]

    context_blokken = []
    for i, s in enumerate(secties, 1):
        bron = s.handleiding_naam
        if s.pagina:
            bron += f", pagina {s.pagina}"
        context_blokken.append(f"[Sectie {i} – {s.titel} | {bron}]\n{s.inhoud}")

    context = "\n\n".join(context_blokken) if context_blokken else "(Geen relevante handleidingsecties gevonden.)"

    # NB: we voegen hier bewust géén afbeelding-instructie toe aan de system-prompt.
    # Dat maakte kleinere modellen overdreven terughoudend bij randgevallen. De
    # verwijzing naar een afbeelding wordt in genereer_antwoord in code toegevoegd.
    system_inhoud = inst["system_prompt"]

    try:
        response = ollama.chat(
            model=gebruik_model,
            messages=[
                {"role": "system", "content": system_inhoud},
                {"role": "user", "content": f"Handleidingsecties:\n{context}\n\nVraag: {vraag}"},
            ],
            options=settings.get_llm_opties(),
        )
        return response["message"]["content"]
    except Exception as exc:
        logger.error("Ollama-fout: %s", exc)
        return f"⚠️ Kon geen antwoord genereren. Is Ollama gestart en model '{gebruik_model}' beschikbaar? (Fout: {exc})"


# ── Afbeeldingen (on-demand uit de PDF) ───────────────────────────────────────

def _regios_op_pagina(blad) -> list:
    """Filtert en dedupliceert de figuur-regio's (vectorclusters + rasters) op een
    PDF-pagina. Geeft fitz.Rect-objecten terug, op volgorde van boven naar onder."""
    import fitz
    pb, ph = blad.rect.width, blad.rect.height

    regios: list = []
    try:
        regios.extend(blad.cluster_drawings())  # vectorfiguren/diagrammen
    except Exception:
        pass
    for img in blad.get_images(full=True):       # ingebedde rasterafbeeldingen
        try:
            regios.extend(blad.get_image_rects(img[0]))
        except Exception:
            pass

    geaccepteerd: list = []
    for r in regios:
        r = fitz.Rect(r)
        if r.width < MIN_AFBEELDING_PT or r.height < MIN_AFBEELDING_PT:
            continue
        if r.width > pb * 0.92 and r.height > ph * 0.92:  # volledige-paginakaders
            continue
        opp = r.get_area()
        if any(
            not (r & g).is_empty and (r & g).get_area() > 0.6 * min(opp, g.get_area())
            for g in geaccepteerd
        ):
            continue
        geaccepteerd.append(r)

    geaccepteerd.sort(key=lambda r: r.y0)
    return geaccepteerd


def _afbeelding_urls(sectie: Sectie) -> list[str]:
    """Geef URL's naar de relevante figuren bij een sectie.

    Twee bronnen, in deze volgorde:
    1. Figuren waar de sectietekst expliciet naar verwijst ("zie afbeelding 17").
       Via de figuur-index weten we op welke pagina dat bijschrift staat, ook als
       dat een vervolgpagina is die formeel bij een volgende sectie hoort.
    2. Overige figuren op het paginabereik van de sectie zelf.

    Veel handleidingen bevatten geen foto's maar vectortekeningen; we detecteren
    daarom figuur-regio's i.p.v. enkel ingebedde afbeeldingen. Er wordt niets
    opgeslagen — de afbeelding wordt pas gerenderd als de browser de URL opvraagt
    (zie /afbeelding in main.py). Nieuwe PDF's werken automatisch mee."""
    bestand = sectie.bestand_naam
    if not sectie.pagina or not bestand.lower().endswith(".pdf"):
        return []

    pad = os.path.join(HANDLEIDINGEN_DIR, bestand)
    if not os.path.exists(pad):
        return []

    def _url(pag: int, r) -> str:
        return (f"/afbeelding?bestand={quote(bestand)}&pagina={pag}"
                f"&clip={r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f}")

    try:
        import fitz  # pymupdf
        urls: list[str] = []
        gezien: set[str] = set()

        def voeg_toe(pag: int, r) -> bool:
            u = _url(pag, r)
            if u in gezien:
                return False
            gezien.add(u)
            urls.append(u)
            return len(urls) >= MAX_AFBEELDINGEN

        with fitz.open(pad) as doc:
            # 1) Figuren waarnaar de tekst verwijst (op nummer)
            index = _FIGUUR_INDEX.get(bestand, {})
            verwezen = [int(n) for n in _VERWIJZING_RE.findall(sectie.inhoud)]
            for nummer in dict.fromkeys(verwezen):           # uniek, in tekstvolgorde
                if nummer not in index:
                    continue
                pag, bijschrift_y = index[nummer]
                if pag - 1 < 0 or pag - 1 >= doc.page_count:
                    continue
                regios = _regios_op_pagina(doc[pag - 1])
                # bijschriften staan onder de figuur → kies de regio net boven het bijschrift
                boven = [r for r in regios if r.y1 <= bijschrift_y + 5]
                keuze = boven[-1] if boven else (regios[0] if regios else None)
                if keuze is not None and voeg_toe(pag, keuze):
                    return urls

            # 2) Overige figuren op het paginabereik van de sectie zelf
            start = sectie.pagina
            eind = min(sectie.eind_pagina or sectie.pagina, doc.page_count)
            for pag in range(start, eind + 1):
                if pag - 1 < 0 or pag - 1 >= doc.page_count:
                    continue
                for r in _regios_op_pagina(doc[pag - 1]):
                    if voeg_toe(pag, r):
                        return urls
        return urls
    except Exception as e:
        logger.warning("Kon figuren niet lezen uit %s: %s", bestand, e)
        return []


# ── Antwoord genereren ────────────────────────────────────────────────────────

def _detecteer_intentie(bericht: str) -> str:
    tekst   = bericht.lower().strip()
    woorden = {re.sub(r"[^\w]", "", w) for w in tekst.split()}
    if woorden & BEGROETINGEN:  return "begroeting"
    if woorden & BEDANKJES:     return "bedankje"
    if woorden & AFSCHEID:      return "afscheid"
    if any(w in tekst for w in ["help", "wat kun jij", "wat kan jij", "hoe werkt"]):
        return "help"
    return "vraag"


def _relevante_handleidingen(
    vraag: str, handleidingen: dict[str, list[Sectie]], limiet: int = 6
) -> list[str]:
    """Geef de handleidingen die een relevante sectie voor de vraag bevatten, op
    volgorde van relevantie. Gebruikt om te bepalen of een model-loze vraag ambigu
    is (meerdere apparaten) en we eerst om het apparaat moeten vragen."""
    namen: list[str] = []
    for s in zoek_secties(vraag, handleidingen, top_n=8):
        if s.handleiding_naam not in namen:
            namen.append(s.handleiding_naam)
    return namen[:limiet]


def genereer_antwoord(
    bericht: str,
    handleidingen: dict[str, list[Sectie]],
    filter_namen: list[str] | None = None,
) -> dict:
    intentie = _detecteer_intentie(bericht)
    beschikbare_namen = list(handleidingen.keys())

    if intentie == "begroeting":
        return {
            "tekst": "Hoi! Waarmee kan ik u helpen? Kies een handleiding of stel uw vraag.",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": None,
        }
    if intentie == "bedankje":
        return {
            "tekst": "Graag gedaan! Heeft u nog andere vragen?",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": None,
        }
    if intentie == "afscheid":
        return {
            "tekst": "Tot ziens! Als u weer vragen heeft, staan de handleidingen klaar.",
            "secties": [],
            "opties": [],
            "set_filter": None,
        }
    if intentie == "help":
        beschikbaar = ", ".join(beschikbare_namen) if beschikbare_namen else "geen handleidingen geladen"
        return {
            "tekst": f"Ik zoek in de beschikbare handleidingen op basis van uw vraag.\n\n**Beschikbaar:** {beschikbaar}",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": None,
        }

    # Gebruiker kiest "Andere handleiding" om filter te wissen
    if bericht.strip().lower() == "andere handleiding":
        return {
            "tekst": "Kies een handleiding:",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": [],
        }

    # Gebruiker klikt op een handleiding-chip → filter instellen en topicvragen tonen
    bericht_lower = bericht.strip().lower()
    matched_naam = next(
        (naam for naam in beschikbare_namen if naam.lower() == bericht_lower),
        None,
    )
    if matched_naam and not filter_namen:
        return {
            "tekst": f"U hebt **{matched_naam}** gekozen. Stel uw vraag.",
            "secties": [],
            "opties": [],
            "set_filter": [matched_naam],
        }

    # Geen handleiding gekozen én geen model in de vraag? Als het onderwerp in
    # meerdere handleidingen voorkomt, weten we niet welk apparaat bedoeld is →
    # vraag dat eerst (met alleen de relevante apparaten als opties), zodat we niet
    # het antwoord van het verkeerde apparaat geven.
    if not filter_namen and _detecteer_model_filter(bericht, handleidingen) is None:
        relevante = _relevante_handleidingen(bericht, handleidingen)
        if len(relevante) >= 2:
            return {
                "tekst": "Voor welk apparaat is uw vraag? Dit onderwerp staat in meerdere "
                         "handleidingen — kies het apparaat, dan geef ik het juiste antwoord.",
                "secties": [],
                "opties": relevante,
                "set_filter": None,
                "kies_apparaat": True,
            }

    top_n = settings.get_instellingen()["top_n"]
    gevonden = zoek_secties(bericht, handleidingen, filter_namen=filter_namen, top_n=top_n)

    if not gevonden:
        return {
            "tekst": "Ik kon geen relevante informatie vinden in de handleiding. Probeer het anders te formuleren.",
            "secties": [],
            "opties": [],
            "set_filter": None,
        }

    # De LLM krijgt alle gevonden secties als context, maar we tonen de gebruiker
    # alleen de sterkste bron(nen) — zwakkere secties zijn voor context nuttig maar
    # rommelen de bronvermelding op. (gevonden is op score gesorteerd)
    aantal_tonen = settings.get_instellingen()["bronnen_tonen"]

    # Afbeeldingen verzamelen uit ALLE secties die het LLM ziet — het antwoord kan
    # over een figuur in elke sectie gaan, ook in een die we niet als bron tonen.
    # Gededupliceerd en afgetopt op MAX_AFBEELDINGEN.
    alle_figuren: list[str] = []
    afb_gezien: set[str] = set()
    for s in gevonden:
        if len(alle_figuren) >= MAX_AFBEELDINGEN:
            break
        for url in _afbeelding_urls(s):
            if url in afb_gezien:
                continue
            afb_gezien.add(url)
            alle_figuren.append(url)
            if len(alle_figuren) >= MAX_AFBEELDINGEN:
                break

    # De getoonde bron(nen); de verzamelde figuren hangen we aan de eerste, zodat
    # ze als één galerij onder het antwoord verschijnen (de frontend bundelt ze).
    secties_uit: list[dict] = []
    for idx, s in enumerate(gevonden[:aantal_tonen]):
        secties_uit.append({
            "titel": s.titel,
            "inhoud": s.inhoud,
            "bron": s.handleiding_naam,
            "bestand": s.bestand_naam,
            "pagina": s.pagina,
            "afbeeldingen": alle_figuren if idx == 0 else [],
        })

    # De handleidingen bevatten icoon-glyphs (Private Use Area) die het model soms
    # in zijn antwoord overneemt; die halen we hier uit de getoonde tekst. We laten
    # de context die naar het model gaat bewust ongemoeid — opschonen daarvan
    # verandert de embeddings/context en kan het antwoord onbedoeld beïnvloeden.
    antwoord = _schoon_glyphs(_genereer_llm_antwoord(_verduidelijk_symbolen(bericht), gevonden))

    # Het model plakt de "niet gevonden"-melding soms achter een verder prima
    # antwoord (hedging). Verwijder die melding als er een inhoudelijk antwoord
    # overblijft; staat hij er alléén, dan laten we hem als echte melding staan.
    zonder_melding = re.sub(
        r"\s*Deze informatie staat niet in de beschikbare handleiding\.?", "", antwoord
    ).strip()
    if len(zonder_melding) >= 25:
        antwoord = zonder_melding

    # Verwijzing naar de getoonde afbeelding voegen we in code toe — niet via de
    # prompt. Een afbeelding-instructie maakt kleinere modellen overdreven
    # terughoudend bij randgevallen; zo houden we de antwoordkwaliteit én verwijzen
    # we deterministisch (juiste richting, geen verzonnen figuurnummers).
    if alle_figuren and "niet in de beschikbare handleiding" not in antwoord.lower():
        antwoord = antwoord.rstrip() + "\n\nZie de afbeelding hieronder."

    return {
        "tekst": antwoord,
        "secties": secties_uit,
        "opties": ["Andere handleiding"],
        "set_filter": None,
    }
