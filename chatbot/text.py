"""Tekstverwerking: opschonen, taaldetectie, trefwoorden, fuzzy-matching en symbolen.

Dit zijn de tekst-hulpfuncties die het zoeken (search.py) en de antwoordopbouw
(answer.py) gebruiken. De functies hebben geen kennis van handleidingen of LLM's;
ze werken puur op strings en `Section`-tokens.
"""

import re

from rapidfuzz import fuzz

from .model import STOPWORDS, ENGLISH_STOPWORDS, Section

FUZZY_THRESHOLD = 82
MIN_WORD_LENGTH = 4


# ── Tekst opschonen ───────────────────────────────────────────────────────────

# Private Use Area (U+E000–U+F8FF): icoon-glyphs uit de symboolfonts van de
# handleidingen (knoppen, ™/©, waarschuwings- en aansluitmarkers). Die hebben geen
# leesbare Unicode-betekenis en tonen als een vervang-teken. De PDF heeft er geen
# Unicode-mapping voor, dus de exacte knopnaam (bv. "GO") is niet uit de tekst te
# halen — die zit alleen in de glyph-vorm. We vervangen zo'n glyph daarom door een
# neutrale placeholder, zodat duidelijk blijft dát er een knop ingedrukt moet worden.
_PUA_RE = re.compile("[\uE000-\uF8FF]+")

_GLYPH_PLACEHOLDER = "[knop]"

def _clean_glyphs(tekst: str) -> str:
    if not tekst:
        return tekst
    tekst = _PUA_RE.sub(_GLYPH_PLACEHOLDER, tekst)
    tekst = re.sub(r"[ \t]+([.,;:!?])", r"\1", tekst)  # spatie vóór leesteken weg
    tekst = re.sub(r"[ \t]{2,}", " ", tekst)           # dubbele spaties samenvoegen
    return tekst.strip()


# ── Taal & trefwoorden ────────────────────────────────────────────────────────

def _detect_language(tekst: str) -> str:
    woorden = re.findall(r"[a-zA-Z]+", tekst.lower())
    if not woorden:
        return "onbekend"
    nl = sum(1 for w in woorden if w in STOPWORDS)
    en = sum(1 for w in woorden if w in ENGLISH_STOPWORDS)
    if nl > en:
        return "nl"
    if en > nl:
        return "en"
    return "onbekend"


def _keywords(tekst: str) -> set[str]:
    woorden = re.findall(r"[a-zA-Z0-9À-ÿ]+", tekst.lower())
    return {w for w in woorden if w not in STOPWORDS and len(w) >= MIN_WORD_LENGTH}


def _fuzzy_score(section: Section, zoekwoorden: set[str]) -> float:
    if not zoekwoorden:
        return 0.0

    token_lijst  = list(section._tokens)
    titel_str    = section.title.lower()
    titel_tokens = _keywords(section.title)
    totaal = 0.0

    for zoek in zoekwoorden:
        # 1. Exacte token-match
        if zoek in section._tokens:
            totaal += 3.0 if zoek in titel_tokens else 1.0
            continue

        # 2. Partial-ratio tegen volledige titeltekst — vangt samengestelde woorden
        #    bv. "beschrijving" in "opdrachtbeschrijving"
        pr_titel = fuzz.partial_ratio(zoek, titel_str)
        if pr_titel >= FUZZY_THRESHOLD:
            totaal += (pr_titel / 100.0) * 3.0
            continue

        # 3. Fuzzy token-match (typfouten)
        beste = max((fuzz.ratio(zoek, t) for t in token_lijst), default=0)
        if beste >= FUZZY_THRESHOLD:
            in_titel = any(fuzz.ratio(zoek, t) >= FUZZY_THRESHOLD for t in titel_tokens)
            totaal += (beste / 100.0) * (3.0 if in_titel else 1.0)

    return totaal


# ── Query-uitbreiding ─────────────────────────────────────────────────────────

def _expand_query(vraag: str) -> str:
    """Voeg zoektermen toe voor error-code-vragen zodat de foutcodes-sectie beter gevonden wordt."""
    if re.search(r'\berr(?:or)?\s*\d', vraag, re.IGNORECASE) or \
       re.search(r'\bfout(?:code)?\b', vraag, re.IGNORECASE):
        return vraag + " foutcode fout oplossing zelftest tabel err"
    return vraag


# Een reeks van 3+ keer hetzelfde leesteken in de vraag (bv. "-----" of "....") is
# een displaypatroon waar de gebruiker naar vraagt. De handleidingen beschrijven dat
# letterlijk (bv. "streepjes (-----)"), dus daar matchen we letterlijk op.
_SYMBOL_RUN_RE = re.compile(r"([^\w\s])\1{2,}")

def _symbol_run_patterns(vraag: str) -> list[re.Pattern]:
    chars = {m.group(1) for m in _SYMBOL_RUN_RE.finditer(vraag)}
    return [re.compile(re.escape(c) + r"{3,}") for c in chars]


# Hoe een symboolreeks in de handleidingen meestal in woorden heet. Gebruikt om de
# vraag aan het LLM te verduidelijken: het model koppelt kale "-----" niet vanzelf
# aan "streepjes", terwijl de handleiding het zo beschrijft.
_SYMBOL_WORD = {"-": "streepjes", ".": "puntjes", "_": "liggende streepjes"}

def _clarify_symbols(vraag: str) -> str:
    """Vervang een symboolreeks in de vraag door 'woord (reeks)', zodat het LLM
    'wat betekent -----' koppelt aan 'streepjes' in de handleiding. Het model
    struikelt over een kale reeks; met het woord ervoor antwoordt het wél."""
    def vervang(m: re.Match) -> str:
        woord = _SYMBOL_WORD.get(m.group(1))
        return f"{woord} ({m.group(0)})" if woord else m.group(0)
    return _SYMBOL_RUN_RE.sub(vervang, vraag)
