"""Inladen: handleidingen (PDF/Word/Markdown) inlezen en opdelen in secties.

`load_manuals` is het instappunt: het loopt door de map `handleidingen/`, kiest per
extensie de juiste parser, gooit zwakke secties weg (kwaliteitsfilter), bepaalt voor
PDF-secties het figuur-paginabereik, berekent per sectie de trefwoord-set en laat
tot slot de embeddings berekenen. De PDF-parser vult ook de figuur-index in
images._FIGURE_INDEX, zodat tekstverwijzingen naar afbeeldingen later kloppen.
"""

import os
import json
import logging

from .model import Section, MANUALS_DIR
from .text import _keywords
from .embeddings import _compute_embeddings
from . import images

logger = logging.getLogger(__name__)

# Parse-cache op schijf: PDF-parsen (incl. tabeldetectie via find_tables) is traag,
# dus we bewaren het resultaat per bestand. Bij een ongewijzigd bestand (zelfde
# mtime + grootte) laden we secties + figuur-index uit de cache i.p.v. opnieuw te
# parsen. Hoort bij de losse PDF-parser; Word/Markdown zijn snel genoeg.
_PARSE_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "parse_cache.json")
# Verhoog dit nummer bij élke wijziging aan de PDF-parserlogica, zodat een oude cache
# (die nog de vorige opdeling bevat) automatisch ongeldig wordt en opnieuw opbouwt.
_PARSE_VERSION = 2
_parse_cache: dict | None = None


def _bestand_sleutel(pad: str) -> str:
    st = os.stat(pad)
    return f"{int(st.st_mtime)}-{st.st_size}"


def _get_parse_cache() -> dict:
    global _parse_cache
    if _parse_cache is None:
        try:
            with open(_PARSE_CACHE_PATH, encoding="utf-8") as f:
                opgeslagen = json.load(f)
            # Cache uit een oudere parserversie negeren (opnieuw opbouwen).
            _parse_cache = opgeslagen.get("bestanden", {}) if opgeslagen.get("versie") == _PARSE_VERSION else {}
        except Exception:
            _parse_cache = {}
    return _parse_cache


def _schrijf_parse_cache(cache: dict) -> None:
    try:
        with open(_PARSE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"versie": _PARSE_VERSION, "bestanden": cache}, f)
    except Exception as e:
        logger.warning("Kon parse-cache niet schrijven: %s", e)


def load_manuals() -> dict[str, list[Section]]:
    handleidingen: dict[str, list[Section]] = {}
    if not os.path.exists(MANUALS_DIR):
        return handleidingen

    parsers = {
        ".md":   _parse_md,
        ".docx": _parse_docx,
        ".pdf":  _parse_pdf,
    }

    pdf_bestanden: list[str] = []
    for bestand in sorted(os.listdir(MANUALS_DIR)):
        ext  = os.path.splitext(bestand)[1].lower()
        if ext not in parsers:
            continue
        if ext == ".pdf":
            pdf_bestanden.append(bestand)
        pad  = os.path.join(MANUALS_DIR, bestand)
        naam = os.path.splitext(bestand)[0].replace("_", " ").replace("-", " ").title()
        try:
            secties = parsers[ext](pad, naam, bestand)
        except Exception as e:
            logger.warning("Kon %s niet inladen: %s", bestand, e)
            continue
        # slechte secties weggooien: lege inhoud, te korte titel, te weinig inhoud,
        # of inhoud die grotendeels uit niet-letters bestaat (inhoudsopgave, nummers)
        def _is_good_section(s: "Section") -> bool:
            inhoud = s.content.strip()
            if not inhoud or len(s.title.strip()) < 3 or len(inhoud) < 80:
                return False
            letters = sum(c.isalpha() for c in inhoud)
            return (letters / len(inhoud)) >= 0.40

        secties = [s for s in secties if _is_good_section(s)]

        # Bepaal per PDF-sectie het figuur-paginabereik: een sectie 'bezit' de
        # pagina's tot aan de eerstvolgende behouden sectie die op een látere pagina
        # begint. Zo worden ook figuren op vervolgpagina's meegenomen, ook als een
        # tussenliggende mini-sectie is weggevallen of als meerdere secties op
        # dezelfde pagina beginnen. De laatste paginagroep houdt de door de parser
        # bepaalde eind_pagina (inhoud die er echt staat).
        pdf_secties = [s for s in secties if s.page is not None]
        if pdf_secties:
            distinct = sorted({s.page for s in pdf_secties})
            volgende_groter = {
                p: (distinct[i + 1] if i + 1 < len(distinct) else None)
                for i, p in enumerate(distinct)
            }
            for s in pdf_secties:
                ng = volgende_groter.get(s.page)
                if ng is not None:
                    s.end_page = max(s.page, ng - 1)

        for s in secties:
            s._tokens = _keywords(s.title + " " + s.content)
        handleidingen[naam] = secties
        logger.info("Geladen: %s (%d secties)", naam, len(secties))

    # Parse-cache wegschrijven; alleen entries voor nog bestaande PDF's bewaren.
    cache = _get_parse_cache()
    cache = {b: cache[b] for b in pdf_bestanden if b in cache}
    globals()["_parse_cache"] = cache
    _schrijf_parse_cache(cache)

    _compute_embeddings(handleidingen)
    return handleidingen


# ── Markdown parser ───────────────────────────────────────────────────────────

def _parse_md(pad: str, naam: str, bestand: str) -> list[Section]:
    with open(pad, encoding="utf-8") as f:
        return _parse_sections(f.read(), naam, bestand)


# ── Word parser (.docx) ───────────────────────────────────────────────────────

def _parse_docx(pad: str, naam: str, bestand: str) -> list[Section]:
    from docx import Document
    doc = Document(pad)

    secties: list[Section] = []
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
                secties.append(Section(
                    title=huidige_titel,
                    content="\n".join(huidige_regels).strip(),
                    manual_name=naam,
                    file_name=bestand,
                ))
            huidige_titel = tekst
            huidige_regels = []
        else:
            huidige_regels.append(tekst)

    if huidige_regels:
        secties.append(Section(
            title=huidige_titel,
            content="\n".join(huidige_regels).strip(),
            manual_name=naam,
            file_name=bestand,
        ))
    return secties


# ── PDF parser ────────────────────────────────────────────────────────────────

def _pagina_tabellen(pagina) -> tuple[list, list[str]]:
    """Herken tabellen op een pagina en geef (bounding-rects, markdown-blokken)
    terug. De markdown bewaart de rij-structuur ("label | waarde"), zodat het
    verband tussen een spec en zijn waarde niet verloren gaat. De rects gebruiken
    we om de losse tabel-tekstregels in de gewone tekstverwerking over te slaan."""
    import fitz  # pymupdf

    rects: list = []
    blokken: list[str] = []
    try:
        gevonden = pagina.find_tables()
    except Exception:
        return rects, blokken
    for tb in getattr(gevonden, "tables", []):
        try:
            md = tb.to_markdown().strip()
        except Exception:
            continue
        if not md:
            continue
        rects.append(fitz.Rect(tb.bbox))
        # <br> binnen cellen -> spatie zodat het leesbare platte tekst blijft.
        md = md.replace("<br>", " ")
        # Markdown-scheidingsregels (|---|---|) weglaten: ze voegen niets toe voor
        # het LLM én hun streepjes zouden de symboolreeks-boost ("-----") vervuilen,
        # waardoor élke tabel onterecht bovenaan komt bij een streepjes-vraag.
        regels = [
            r for r in md.split("\n")
            if r.replace("|", "").replace("-", "").replace(":", "").strip()
        ]
        blokken.append("\n".join(regels).strip())
    return rects, blokken


def _regel_in_tabel(bbox, tabel_rects: list) -> bool:
    """True als een tekstregel grotendeels binnen een herkende tabel valt."""
    if not bbox or not tabel_rects:
        return False
    import fitz  # pymupdf

    r = fitz.Rect(bbox)
    opp = r.get_area()
    if opp <= 0:
        return False
    return any((r & t).get_area() >= 0.5 * opp for t in tabel_rects)


def _parse_pdf(pad: str, naam: str, bestand: str) -> list[Section]:
    """Cached PDF-parser: hergebruik het eerdere resultaat als het bestand niet is
    gewijzigd, anders opnieuw parsen en de cache bijwerken."""
    sleutel = _bestand_sleutel(pad)
    cache = _get_parse_cache()
    entry = cache.get(bestand)
    if entry and entry.get("key") == sleutel:
        images._FIGURE_INDEX[bestand] = {
            int(n): tuple(v) for n, v in entry.get("figures", {}).items()
        }
        return [
            Section(
                title=d["title"], content=d["content"],
                manual_name=naam, file_name=bestand,
                page=d["page"], end_page=d["end_page"],
            )
            for d in entry["sections"]
        ]

    secties = _parse_pdf_uncached(pad, naam, bestand)
    cache[bestand] = {
        "key": sleutel,
        "sections": [
            {"title": s.title, "content": s.content, "page": s.page, "end_page": s.end_page}
            for s in secties
        ],
        "figures": {str(n): list(v) for n, v in images._FIGURE_INDEX.get(bestand, {}).items()},
    }
    return secties


def _parse_pdf_uncached(pad: str, naam: str, bestand: str) -> list[Section]:
    import fitz  # pymupdf

    # find_tables() print bij sommige PDFs onschuldige MuPDF-structuurwaarschuwingen
    # naar stderr ("No common ancestor in structure tree"). Tijdelijk dempen zodat de
    # opstartlog schoon blijft; daarna weer aanzetten voor echte fouten elders.
    fitz.TOOLS.mupdf_display_errors(False)
    doc = fitz.open(pad)
    secties: list[Section] = []
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
        # Tabellen op deze pagina als samenhangend markdown-blok bewaren. De losse
        # tekstregels binnen een tabel slaan we hieronder over, zodat de (vette)
        # labelcellen niet als headings de tabel in mini-secties versnipperen.
        tabel_rects, tabel_blokken = _pagina_tabellen(pagina)

        for blok in pagina.get_text("dict")["blocks"]:
            if blok.get("type") != 0:
                continue
            for regel in blok.get("lines", []):
                regel_tekst = "".join(s.get("text", "") for s in regel.get("spans", [])).strip()
                if not regel_tekst:
                    continue

                # Regels binnen een herkende tabel overslaan (komen via markdown terug).
                if _regel_in_tabel(regel.get("bbox"), tabel_rects):
                    continue

                # Figuur-bijschrift onthouden (nummer → pagina + y-positie van het bijschrift)
                m = images._CAPTION_RE.match(regel_tekst)
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
                        secties.append(Section(
                            title=huidige_titel,
                            content="\n".join(huidige_regels).strip(),
                            manual_name=naam,
                            file_name=bestand,
                            page=huidige_pagina,
                            end_page=huidige_eind_pagina,
                        ))
                    huidige_titel = regel_tekst
                    huidige_regels = []
                    huidige_pagina = pagina_idx + 1
                    huidige_eind_pagina = pagina_idx + 1
                else:
                    huidige_regels.append(regel_tekst)
                    huidige_eind_pagina = pagina_idx + 1

        # Elke herkende tabel als een eigen, gefocuste sectie opnemen (titel = de
        # heading die eraan voorafgaat). Zo blijft "label | waarde" intact én blijft
        # de embedding scherp — één grote samengevoegde tabel-blob zou de
        # semantische match juist verwateren.
        for md in tabel_blokken:
            secties.append(Section(
                title=huidige_titel,
                content=md,
                manual_name=naam,
                file_name=bestand,
                page=pagina_idx + 1,
                end_page=pagina_idx + 1,
            ))

    if huidige_regels:
        secties.append(Section(
            title=huidige_titel,
            content="\n".join(huidige_regels).strip(),
            manual_name=naam,
            file_name=bestand,
            page=huidige_pagina,
            end_page=huidige_eind_pagina,
        ))

    images._FIGURE_INDEX[bestand] = figuur_index
    fitz.TOOLS.mupdf_display_errors(True)
    return secties


def _parse_sections(tekst: str, handleiding_naam: str, bestand_naam: str = "") -> list[Section]:
    secties: list[Section] = []
    huidige_titel = "Algemeen"
    huidige_regels: list[str] = []

    for regel in tekst.splitlines():
        if regel.startswith("## "):
            if huidige_regels:
                secties.append(Section(
                    title=huidige_titel,
                    content="\n".join(huidige_regels).strip(),
                    manual_name=handleiding_naam,
                    file_name=bestand_naam,
                ))
            huidige_titel = regel.lstrip("# ").strip()
            huidige_regels = []
        elif regel.startswith("# "):
            continue
        else:
            huidige_regels.append(regel)

    if huidige_regels:
        secties.append(Section(
            title=huidige_titel,
            content="\n".join(huidige_regels).strip(),
            manual_name=handleiding_naam,
            file_name=bestand_naam,
        ))
    return secties
