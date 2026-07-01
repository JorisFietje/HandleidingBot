"""Zoeken: de meest relevante secties bij een vraag vinden.

`search_sections` combineert semantisch zoeken (cosine-similariteit op embeddings)
met een fuzzy trefwoord-boost, plus extra's als modelnummer-routing (een vraag over
model "789" wordt naar die handleiding gerouteerd), een error-/foutcode-boost, een
symboolreeks-boost, een taalfilter en deduplicatie. Drempels komen uit settings.
"""

import re

import numpy as np
from rapidfuzz import fuzz

import settings

from .model import Section
from .text import (
    _keywords, _detect_language, _fuzzy_score, _expand_query, _symbol_run_patterns,
)
from .embeddings import _get_model, _cosine_scores


def _model_index(handleidingen: dict[str, list[Section]]) -> dict[str, set[str]]:
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


def _detect_model_filter(
    vraag: str, handleidingen: dict[str, list[Section]]
) -> list[str] | None:
    """Als de vraag een modelnummer noemt dat bij een handleiding hoort, geef die
    handleiding(en) terug zodat de zoekopdracht zich daarop richt. Anders None."""
    idx = _model_index(handleidingen)
    matches: set[str] = set()
    for tok in re.findall(r"[A-Za-z0-9]+", vraag.lower()):
        if tok in idx:
            matches |= idx[tok]
    return list(matches) if matches else None


def search_sections(
    vraag: str,
    handleidingen: dict[str, list[Section]],
    filter_names: list[str] | None = None,
    top_n: int = 2,
) -> list[Section]:
    # Geen handmatig filter? Probeer op modelnummer in de vraag te routeren, zodat
    # een vraag over een 789 niet uit de handleiding van een ander model wordt
    # beantwoord.
    if not filter_names:
        filter_names = _detect_model_filter(vraag, handleidingen)

    kandidaten = [
        s
        for naam, secties in handleidingen.items()
        if not filter_names or naam in filter_names
        for s in secties
    ]
    if not kandidaten:
        return []

    zoekwoorden = _keywords(vraag)
    uitgebreide_vraag = _expand_query(vraag)

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
        for cos, section in zip(cos_scores, secties_met_embedding):
            fuz   = _fuzzy_score(section, zoekwoorden)
            score = cos + (fuz / fuz_max) * 0.35
            gecombineerd.append((score, cos, section))

        # Extra boost voor oplossings-/foutcodes-secties bij error-queries
        if re.search(r'\berr\b|\bfout', uitgebreide_vraag, re.IGNORECASE):
            relevante_titels = {'oplossing', 'foutcode', 'fout', 'storing', 'probleem', 'solution', 'error'}
            gecombineerd = [
                (score + (0.20 if any(w in s.title.lower() for w in relevante_titels) else 0), cos, s)
                for score, cos, s in gecombineerd
            ]

        # Sterke boost als de vraag een symboolreeks bevat (bv. "-----") die letterlijk
        # in een sectie voorkomt — handleidingen beschrijven displaypatronen zo.
        sym_patronen = _symbol_run_patterns(vraag)
        if sym_patronen:
            gecombineerd = [
                (score + (0.50 if any(p.search(s.content) for p in sym_patronen) else 0), cos, s)
                for score, cos, s in gecombineerd
            ]

        # Boost voor secties die de getallen uit de vraag letterlijk bevatten.
        # Spec-/tabelvragen ("... bij 400 V?", "bereik 2000 Ω") draaien om een exact
        # getal; dat pikt semantisch zoeken slecht op, maar het staat letterlijk in de
        # (tabel)tekst. We matchen op getalgrenzen, zodat "400" niet ook "1400" of
        # "4000" raakt; losse cijfers negeren we om ruis te voorkomen. Modelnummers
        # (bv. "789", "1664") sluiten we uit: die staan overal in de eigen handleiding
        # en worden al voor de routing gebruikt, dus als boost zijn ze juist ruis.
        modeltokens = set(_model_index(handleidingen))
        getallen = {g for g in re.findall(r"\d+", vraag) if len(g) >= 2 and g not in modeltokens}
        if getallen:
            getal_patronen = [re.compile(rf"(?<!\d){re.escape(g)}(?!\d)") for g in getallen]
            opnieuw = []
            for score, cos, s in gecombineerd:
                boost = 0.0
                if any(p.search(s.content) for p in getal_patronen):
                    boost = 0.30
                    # Extra zetje als óók alle inhoudswoorden van de vraag in de sectie
                    # staan: dan is dit vrijwel zeker de gezochte spec-rij (bv. "maximale
                    # teststroom bij 400 V"). Tabel-secties scoren semantisch laag, dus
                    # zonder dit signaal worden ze door generieke secties verdrongen.
                    if zoekwoorden and all(w in s._tokens for w in zoekwoorden):
                        boost = 0.60
                opnieuw.append((score + boost, cos, s))
            gecombineerd = opnieuw

        # Taalvoorkeur als zachte boost (geen harde filter). Secties in dezelfde taal
        # als de vraag krijgen een klein zetje, zodat bij een handleiding met zowel
        # NL- als EN-tekst de juiste taal voorgaat. Cruciaal: Engelstalige
        # handleidingen worden NIET meer weggegooid bij een Nederlandse vraag — het
        # multilinguale embeddingmodel matcht over talen heen, en de bot antwoordt in
        # het Nederlands op basis van Engelse brontekst.
        vraag_taal = _detect_language(vraag)
        if vraag_taal != "onbekend":
            gecombineerd = [
                (score + (0.06 if getattr(s, "_taal", "onbekend") == vraag_taal else 0), cos, s)
                for score, cos, s in gecombineerd
            ]

        gecombineerd.sort(key=lambda x: x[0], reverse=True)
        # Drempel op hybride score zodat sterke fuzzy-matches de threshold kunnen halen
        inst = settings.get_settings()
        drempel = inst["drempel_filter"] if filter_names else inst["drempel_globaal"]
        kandidaten = [(score, cos, s) for score, cos, s in gecombineerd if score > drempel]

        # dedupliceer: verwijder secties die te veel lijken op een eerder gekozen sectie
        resultaat: list[Section] = []
        for _, _, s in kandidaten:
            if len(resultaat) >= top_n:
                break
            is_duplicaat = any(
                s.title.strip().lower() == r.title.strip().lower()
                or fuzz.ratio(s.content[:300], r.content[:300]) > 88
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
