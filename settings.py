"""Persistente, tijdens runtime aanpasbare instellingen voor de chatbot.

De admin-pagina leest en schrijft deze instellingen via de /admin-endpoints.
Wijzigingen worden opgeslagen in admin_settings.json zodat ze een herstart
overleven. Niets hier vereist een herstart van de server: alle waarden worden
bij elke vraag opnieuw uitgelezen.
"""

import os
import json
import logging
from copy import deepcopy

logger = logging.getLogger(__name__)

_SETTINGS_PAD = os.path.join(os.path.dirname(__file__), "admin_settings.json")

# Standaard-systeemprompt (zelfde inhoud als voorheen hardcoded in chatbot.py)
_STANDAARD_SYSTEEM_PROMPT = """Je bent een technische klantenservice-assistent voor professionele meetinstrumenten.
Je beantwoordt vragen uitsluitend op basis van de meegeleverde handleidingsecties.

Regels:
- Antwoord altijd in het Nederlands.
- Gebruik ALLEEN informatie uit de meegeleverde secties. Verzin niets bij.
- Staat het antwoord niet in de secties? Zeg dan kort: "Deze informatie staat niet in de beschikbare handleiding." Stel GEEN tegenvragen.
- Valt de vraag buiten scope (offertes, reparatiekosten, monteur sturen, concurrenten, firmware schrijven)? Verwijs vriendelijk door naar de juiste afdeling.
- Is de vraag te vaag (geen model of apparaattype duidelijk)? Stel één gerichte verduidelijkende vraag.
- Formuleer antwoorden bondig en praktisch. Gebruik genummerde stappen bij procedures.
- Foutcodes op meetinstrument-displays worden gesplitst weergegeven: primair display toont bv. "ERR 1" (fouttype), secundair display toont bv. "0004" (bijkomende code). Verwijder voorloopnullen: "0004" = 4, "0008" = 8. Zoek in de secties naar de primaire code (bv. "1") EN de secundaire waarde (bv. "4:") los van elkaar. Leg beide uit in je antwoord."""

# Standaardwaarden. Het env-var OLLAMA_MODEL blijft als standaardmodel werken.
STANDAARD_INSTELLINGEN: dict = {
    # ── LLM (Ollama) ──
    "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
    "temperature": 0.0,      # 0 = deterministisch/feitelijk, hoger = creatiever
    "top_p": 0.9,            # nucleus sampling
    "top_k": 40,             # beperk tot k meest waarschijnlijke tokens
    "repeat_penalty": 1.1,   # ontmoedig herhaling
    "num_predict": 512,      # max. aantal tokens in het antwoord (-1 = oneindig)
    "num_ctx": 4096,         # contextvenster (tokens)
    "seed": 0,               # 0 = vaste seed → reproduceerbaar voor testen
    "system_prompt": _STANDAARD_SYSTEEM_PROMPT,

    # ── Zoeken / retrieval ──
    "top_n": 2,              # aantal handleidingsecties dat naar de LLM gaat (context)
    "bronnen_tonen": 1,      # aantal bronnen dat aan de gebruiker getoond wordt
    "drempel_globaal": 0.42, # min. hybride score zonder handleidingfilter
    "drempel_filter": 0.28,  # min. hybride score met handleidingfilter
}

# Welke sleutels horen bij de Ollama-aanroep (options=...)
_LLM_OPTIE_SLEUTELS = (
    "temperature", "top_p", "top_k",
    "repeat_penalty", "num_predict", "num_ctx", "seed",
)

# Numerieke grenzen voor validatie (min, max)
_GRENZEN = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "top_k": (1, 200),
    "repeat_penalty": (0.5, 2.0),
    "num_predict": (-1, 8192),
    "num_ctx": (512, 32768),
    "seed": (0, 2**31 - 1),
    "top_n": (1, 8),
    "bronnen_tonen": (1, 8),
    "drempel_globaal": (0.0, 1.0),
    "drempel_filter": (0.0, 1.0),
}

_huidige: dict | None = None


def _laad_van_schijf() -> dict:
    instellingen = deepcopy(STANDAARD_INSTELLINGEN)
    if os.path.exists(_SETTINGS_PAD):
        try:
            with open(_SETTINGS_PAD, encoding="utf-8") as f:
                opgeslagen = json.load(f)
            # alleen bekende sleutels overnemen
            for sleutel in STANDAARD_INSTELLINGEN:
                if sleutel in opgeslagen:
                    instellingen[sleutel] = opgeslagen[sleutel]
            logger.info("Admin-instellingen geladen van schijf.")
        except Exception as e:
            logger.warning("Kon admin_settings.json niet lezen: %s", e)
    return instellingen


def get_instellingen() -> dict:
    """Geef een kopie van de huidige instellingen terug."""
    global _huidige
    if _huidige is None:
        _huidige = _laad_van_schijf()
    return deepcopy(_huidige)


def get_llm_opties() -> dict:
    """Geef de Ollama options-dict terug (temperature, top_p, ...)."""
    inst = get_instellingen()
    return {k: inst[k] for k in _LLM_OPTIE_SLEUTELS}


def _valideer(sleutel: str, waarde):
    """Cast en begrens een waarde; gooi ValueError bij ongeldige invoer."""
    if sleutel == "system_prompt":
        return str(waarde)
    if sleutel == "model":
        waarde = str(waarde).strip()
        if not waarde:
            raise ValueError("model mag niet leeg zijn")
        return waarde

    standaard = STANDAARD_INSTELLINGEN[sleutel]
    try:
        waarde = int(waarde) if isinstance(standaard, int) else float(waarde)
    except (TypeError, ValueError):
        raise ValueError(f"{sleutel} moet een getal zijn")

    if sleutel in _GRENZEN:
        lo, hi = _GRENZEN[sleutel]
        waarde = max(lo, min(hi, waarde))
    return waarde


def update_instellingen(nieuw: dict) -> dict:
    """Werk een of meer instellingen bij, valideer, en sla op. Geef het resultaat terug."""
    global _huidige
    inst = get_instellingen()
    for sleutel, waarde in nieuw.items():
        if sleutel not in STANDAARD_INSTELLINGEN:
            continue  # onbekende sleutels negeren
        inst[sleutel] = _valideer(sleutel, waarde)
    _huidige = inst
    _schrijf_naar_schijf(inst)
    return deepcopy(inst)


def reset_instellingen() -> dict:
    """Zet alle instellingen terug naar de standaardwaarden."""
    global _huidige
    _huidige = deepcopy(STANDAARD_INSTELLINGEN)
    _schrijf_naar_schijf(_huidige)
    return deepcopy(_huidige)


def _schrijf_naar_schijf(inst: dict) -> None:
    try:
        with open(_SETTINGS_PAD, "w", encoding="utf-8") as f:
            json.dump(inst, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Kon admin_settings.json niet schrijven: %s", e)
