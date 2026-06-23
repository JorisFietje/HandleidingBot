"""Afbeeldingen: figuren uit PDF-handleidingen lokaliseren en als URL aanbieden.

Veel handleidingen bevatten geen foto's maar vectortekeningen; we detecteren daarom
figuur-regio's i.p.v. enkel ingebedde afbeeldingen. Er wordt niets op schijf bewaard:
`_image_urls` geeft URL's terug die pas gerenderd worden als de browser ze opvraagt
(zie het /afbeelding-endpoint in main.py).

`_FIGURE_INDEX` koppelt per PDF een figuurnummer aan (pagina, y-positie van het
bijschrift). Die index wordt tijdens het inladen gevuld door loading.py (de
PDF-parser) en hier gelezen om tekstverwijzingen als "zie afbeelding 17" naar de
juiste pagina te herleiden — ook als die figuur op een vervolgpagina staat.
"""

import os
import re
import logging
from urllib.parse import quote

from .model import Section, MANUALS_DIR

logger = logging.getLogger(__name__)

# Figuren smaller/lager dan dit (in PDF-punten) zijn meestal logo's/iconen → overslaan.
MIN_IMAGE_PT = 80
# Maximaal aantal afbeeldingen dat we per antwoord tonen.
MAX_IMAGES   = 4

# Index van figuur-bijschriften per PDF: {bestand: {nummer: (pagina, bijschrift_y0)}}.
# Gevuld tijdens het inladen (loading.py), zodat een tekstverwijzing als
# "afbeelding 17" naar de juiste pagina kan worden herleid.
_FIGURE_INDEX: dict[str, dict[int, tuple[int, float]]] = {}
# Herkent bijschriften als "Afbeelding 16." of "Figure 7" (begin van een regel).
_CAPTION_RE = re.compile(r"^(?:afbeelding|figure|fig\.?)\s+(\d+)\b", re.IGNORECASE)
# Herkent een verwijzing in de lopende tekst, bv. "zie afbeelding 17".
_REFERENCE_RE = re.compile(r"(?:afbeelding|figure|fig\.?)\s*(\d+)", re.IGNORECASE)


def _regions_on_page(blad) -> list:
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
        if r.width < MIN_IMAGE_PT or r.height < MIN_IMAGE_PT:
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


def _image_urls(section: Section) -> list[str]:
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
    bestand = section.file_name
    if not section.page or not bestand.lower().endswith(".pdf"):
        return []

    pad = os.path.join(MANUALS_DIR, bestand)
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
            return len(urls) >= MAX_IMAGES

        with fitz.open(pad) as doc:
            # 1) Figuren waarnaar de tekst verwijst (op nummer)
            index = _FIGURE_INDEX.get(bestand, {})
            verwezen = [int(n) for n in _REFERENCE_RE.findall(section.content)]
            for nummer in dict.fromkeys(verwezen):           # uniek, in tekstvolgorde
                if nummer not in index:
                    continue
                pag, bijschrift_y = index[nummer]
                if pag - 1 < 0 or pag - 1 >= doc.page_count:
                    continue
                regios = _regions_on_page(doc[pag - 1])
                # bijschriften staan onder de figuur → kies de regio net boven het bijschrift
                boven = [r for r in regios if r.y1 <= bijschrift_y + 5]
                keuze = boven[-1] if boven else (regios[0] if regios else None)
                if keuze is not None and voeg_toe(pag, keuze):
                    return urls

            # 2) Overige figuren op het paginabereik van de sectie zelf
            start = section.page
            eind = min(section.end_page or section.page, doc.page_count)
            for pag in range(start, eind + 1):
                if pag - 1 < 0 or pag - 1 >= doc.page_count:
                    continue
                for r in _regions_on_page(doc[pag - 1]):
                    if voeg_toe(pag, r):
                        return urls
        return urls
    except Exception as e:
        logger.warning("Kon figuren niet lezen uit %s: %s", bestand, e)
        return []
