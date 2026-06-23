"""Antwoord genereren: van gebruikersbericht naar het volledige chat-antwoord.

`generate_answer` is de kernfunctie die main.py aanroept; `generate_answer_stream`
is de streaming-variant die het antwoord woord-voor-woord oplevert. Beide delen
dezelfde voorbewerking (intentie, handleiding-keuze, ambiguïteit, zoeken) en
nabewerking (opschonen, hedging weghalen, afbeelding-verwijzing); alleen de
LLM-aanroep verschilt (in één keer vs. als stroom).

NB: de keys in de teruggegeven dict (tekst, secties, titel, inhoud, bron, ...) zijn
het API-contract met de frontend en blijven bewust Nederlands.
"""

import re
from collections.abc import Iterator

import settings
import llm_providers

from .model import Section, GREETINGS, THANKS, FAREWELLS
from .text import _clean_glyphs, _clarify_symbols
from .search import search_sections, _detect_model_filter
from .images import _image_urls, MAX_IMAGES


# ── Intentie & relevantie ──────────────────────────────────────────────────────

def _detect_intent(bericht: str) -> str:
    tekst   = bericht.lower().strip()
    woorden = {re.sub(r"[^\w]", "", w) for w in tekst.split()}
    if woorden & GREETINGS:  return "begroeting"
    if woorden & THANKS:     return "bedankje"
    if woorden & FAREWELLS:  return "afscheid"
    if any(w in tekst for w in ["help", "wat kun jij", "wat kan jij", "hoe werkt"]):
        return "help"
    return "vraag"


def _relevant_manuals(
    vraag: str, handleidingen: dict[str, list[Section]], limiet: int = 6
) -> list[str]:
    """Geef de handleidingen die een relevante sectie voor de vraag bevatten, op
    volgorde van relevantie. Gebruikt om te bepalen of een model-loze vraag ambigu
    is (meerdere apparaten) en we eerst om het apparaat moeten vragen."""
    namen: list[str] = []
    for s in search_sections(vraag, handleidingen, top_n=8):
        if s.manual_name not in namen:
            namen.append(s.manual_name)
    return namen[:limiet]


# ── Voorbewerking (niet-LLM) ───────────────────────────────────────────────────

def _control_flow(
    bericht: str,
    handleidingen: dict[str, list[Section]],
    filter_names: list[str] | None,
) -> tuple[dict | None, list[Section] | None]:
    """Doorloop alle niet-LLM-stappen en geef terug:

    - (early, None): een compleet antwoord-dict waarmee we kunnen kortsluiten
      (begroeting, handleiding-keuze, apparaatkeuze, niets gevonden, ...), of
    - (None, gevonden): de gevonden secties als er wél een LLM-antwoord moet komen.
    """
    intentie = _detect_intent(bericht)
    beschikbare_namen = list(handleidingen.keys())

    if intentie == "begroeting":
        return {
            "tekst": "Hoi! Waarmee kan ik u helpen? Kies een handleiding of stel uw vraag.",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": None,
        }, None
    if intentie == "bedankje":
        return {
            "tekst": "Graag gedaan! Heeft u nog andere vragen?",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": None,
        }, None
    if intentie == "afscheid":
        return {
            "tekst": "Tot ziens! Als u weer vragen heeft, staan de handleidingen klaar.",
            "secties": [],
            "opties": [],
            "set_filter": None,
        }, None
    if intentie == "help":
        beschikbaar = ", ".join(beschikbare_namen) if beschikbare_namen else "geen handleidingen geladen"
        return {
            "tekst": f"Ik zoek in de beschikbare handleidingen op basis van uw vraag.\n\n**Beschikbaar:** {beschikbaar}",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": None,
        }, None

    # Gebruiker kiest "Andere handleiding" om filter te wissen
    if bericht.strip().lower() == "andere handleiding":
        return {
            "tekst": "Kies een handleiding:",
            "secties": [],
            "opties": beschikbare_namen,
            "set_filter": [],
        }, None

    # Gebruiker klikt op een handleiding-chip → filter instellen en topicvragen tonen
    bericht_lower = bericht.strip().lower()
    matched_naam = next(
        (naam for naam in beschikbare_namen if naam.lower() == bericht_lower),
        None,
    )
    if matched_naam and not filter_names:
        return {
            "tekst": f"U hebt **{matched_naam}** gekozen. Stel uw vraag.",
            "secties": [],
            "opties": [],
            "set_filter": [matched_naam],
        }, None

    # Geen handleiding gekozen én geen model in de vraag? Als het onderwerp in
    # meerdere handleidingen voorkomt, weten we niet welk apparaat bedoeld is →
    # vraag dat eerst (met alleen de relevante apparaten als opties), zodat we niet
    # het antwoord van het verkeerde apparaat geven.
    if not filter_names and _detect_model_filter(bericht, handleidingen) is None:
        relevante = _relevant_manuals(bericht, handleidingen)
        if len(relevante) >= 2:
            return {
                "tekst": "Voor welk apparaat is uw vraag? Dit onderwerp staat in meerdere "
                         "handleidingen — kies het apparaat, dan geef ik het juiste antwoord.",
                "secties": [],
                "opties": relevante,
                "set_filter": None,
                "kies_apparaat": True,
            }, None

    top_n = settings.get_settings()["top_n"]
    gevonden = search_sections(bericht, handleidingen, filter_names=filter_names, top_n=top_n)

    if not gevonden:
        return {
            "tekst": "Ik kon geen relevante informatie vinden in de handleiding. Probeer het anders te formuleren.",
            "secties": [],
            "opties": [],
            "set_filter": None,
        }, None

    return None, gevonden


def _assemble_sources(gevonden: list[Section]) -> tuple[list[dict], list[str]]:
    """Stel de getoonde bron(nen) en de afbeeldingsgalerij samen uit de gevonden
    secties. Geeft (secties_uit, alle_figuren) terug."""
    aantal_tonen = settings.get_settings()["bronnen_tonen"]

    # Afbeeldingen verzamelen uit ALLE secties die het LLM ziet — het antwoord kan
    # over een figuur in elke sectie gaan, ook in een die we niet als bron tonen.
    # Gededupliceerd en afgetopt op MAX_IMAGES.
    alle_figuren: list[str] = []
    afb_gezien: set[str] = set()
    for s in gevonden:
        if len(alle_figuren) >= MAX_IMAGES:
            break
        for url in _image_urls(s):
            if url in afb_gezien:
                continue
            afb_gezien.add(url)
            alle_figuren.append(url)
            if len(alle_figuren) >= MAX_IMAGES:
                break

    # De getoonde bron(nen); de verzamelde figuren hangen we aan de eerste, zodat
    # ze als één galerij onder het antwoord verschijnen (de frontend bundelt ze).
    secties_uit: list[dict] = []
    for idx, s in enumerate(gevonden[:aantal_tonen]):
        secties_uit.append({
            "titel": s.title,
            "inhoud": s.content,
            "bron": s.manual_name,
            "bestand": s.file_name,
            "pagina": s.page,
            "afbeeldingen": alle_figuren if idx == 0 else [],
        })
    return secties_uit, alle_figuren


# ── LLM-prompt & nabewerking ───────────────────────────────────────────────────

def _build_prompt(vraag: str, secties: list[Section]) -> tuple[str, str]:
    """Bouw de (system_prompt, user_prompt) voor de LLM uit de gevonden secties."""
    inst = settings.get_settings()

    context_blokken = []
    for i, s in enumerate(secties, 1):
        bron = s.manual_name
        if s.page:
            bron += f", pagina {s.page}"
        context_blokken.append(f"[Sectie {i} – {s.title} | {bron}]\n{s.content}")

    context = "\n\n".join(context_blokken) if context_blokken else "(Geen relevante handleidingsecties gevonden.)"

    # NB: we voegen hier bewust géén afbeelding-instructie toe aan de system-prompt.
    # Dat maakte kleinere modellen overdreven terughoudend bij randgevallen. De
    # verwijzing naar een afbeelding wordt in _finalize_text in code toegevoegd.
    return inst["system_prompt"], f"Handleidingsecties:\n{context}\n\nVraag: {vraag}"


def _generate_llm_answer(vraag: str, secties: list[Section]) -> str:
    system_inhoud, user_inhoud = _build_prompt(vraag, secties)
    return llm_providers.generate(system_inhoud, user_inhoud)


def _generate_llm_answer_stream(vraag: str, secties: list[Section]) -> Iterator[str]:
    system_inhoud, user_inhoud = _build_prompt(vraag, secties)
    yield from llm_providers.generate_stream(system_inhoud, user_inhoud)


def _finalize_text(antwoord: str, alle_figuren: list[str]) -> str:
    """Schoon het ruwe LLM-antwoord op: glyphs verwijderen, de "niet gevonden"-
    hedging weghalen als er een inhoudelijk antwoord overblijft, en een verwijzing
    naar de afbeelding toevoegen als die er is."""
    # De handleidingen bevatten icoon-glyphs (Private Use Area) die het model soms
    # in zijn antwoord overneemt; die halen we hier uit de getoonde tekst.
    antwoord = _clean_glyphs(antwoord)

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

    return antwoord


# ── Publieke API ───────────────────────────────────────────────────────────────

def generate_answer(
    bericht: str,
    handleidingen: dict[str, list[Section]],
    filter_names: list[str] | None = None,
) -> dict:
    """Beantwoord een vraag in één keer (zonder streaming)."""
    early, gevonden = _control_flow(bericht, handleidingen, filter_names)
    if early is not None:
        return early

    secties_uit, alle_figuren = _assemble_sources(gevonden)
    ruw = _generate_llm_answer(_clarify_symbols(bericht), gevonden)
    antwoord = _finalize_text(ruw, alle_figuren)

    return {
        "tekst": antwoord,
        "secties": secties_uit,
        "opties": ["Andere handleiding"],
        "set_filter": None,
    }


def generate_answer_stream(
    bericht: str,
    handleidingen: dict[str, list[Section]],
    filter_names: list[str] | None = None,
) -> Iterator[dict]:
    """Beantwoord een vraag als stroom van events (voor SSE).

    Levert dicts op met een "type":
    - {"type": "delta", "tekst": <chunk>}  → een stukje ruw antwoord (live tonen).
    - {"type": "final", ...payload...}     → het definitieve, opgeschoonde antwoord
      met secties/opties/afbeeldingen (zelfde vorm als generate_answer).

    Bij kortsluitende antwoorden (begroeting, apparaatkeuze, niets gevonden) komt er
    geen delta — alleen één final-event."""
    early, gevonden = _control_flow(bericht, handleidingen, filter_names)
    if early is not None:
        yield {"type": "final", **early}
        return

    secties_uit, alle_figuren = _assemble_sources(gevonden)

    ruwe_delen: list[str] = []
    for chunk in _generate_llm_answer_stream(_clarify_symbols(bericht), gevonden):
        ruwe_delen.append(chunk)
        yield {"type": "delta", "tekst": chunk}

    antwoord = _finalize_text("".join(ruwe_delen), alle_figuren)
    yield {
        "type": "final",
        "tekst": antwoord,
        "secties": secties_uit,
        "opties": ["Andere handleiding"],
        "set_filter": None,
    }
