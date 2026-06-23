"""Persistente, tijdens runtime aanpasbare instellingen voor de chatbot.

De admin-pagina leest en schrijft deze instellingen via de /admin-endpoints.
Wijzigingen worden opgeslagen in admin_settings.json zodat ze een herstart
overleven. Niets hier vereist een herstart van de server: alle waarden worden
bij elke vraag opnieuw uitgelezen.

NB: de keys van de settings-dict (model, temperature, drempel_globaal, ...) zijn het
contract met de adminpagina (element-id's) en met admin_settings.json en blijven
daarom bewust ongewijzigd.
"""

import os
import json
import logging
from copy import deepcopy

logger = logging.getLogger(__name__)

# .env inladen zodat sleutels als GEMINI_API_KEY beschikbaar zijn via os.getenv.
# settings wordt vroeg geïmporteerd, dus dit gebeurt vóór de eerste os.getenv hieronder.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logger.info("python-dotenv niet geïnstalleerd; .env wordt niet automatisch geladen.")

_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "admin_settings.json")

# Standaard-systeemprompt (zelfde inhoud als voorheen hardcoded in chatbot.py)
_DEFAULT_SYSTEM_PROMPT = """Je bent een technische klantenservice-assistent voor professionele meetinstrumenten.
Je beantwoordt vragen uitsluitend op basis van de meegeleverde handleidingsecties.

Regels:
- Antwoord altijd in het Nederlands.
- Gebruik ALLEEN informatie uit de meegeleverde secties. Verzin niets bij.
- Staat het antwoord niet in de secties? Zeg dan kort: "Deze informatie staat niet in de beschikbare handleiding." Stel GEEN tegenvragen.
- Valt de vraag buiten scope (offertes, reparatiekosten, monteur sturen, concurrenten, firmware schrijven)? Verwijs vriendelijk door naar de juiste afdeling.
- Is de vraag te vaag (geen model of apparaattype duidelijk)? Stel één gerichte verduidelijkende vraag.
- Formuleer antwoorden bondig en praktisch. Gebruik genummerde stappen bij procedures.
- Foutcodes op meetinstrument-displays worden gesplitst weergegeven: primair display toont bv. "ERR 1" (fouttype), secundair display toont bv. "0004" (bijkomende code). Verwijder voorloopnullen: "0004" = 4, "0008" = 8. Zoek in de secties naar de primaire code (bv. "1") EN de secundaire waarde (bv. "4:") los van elkaar. Leg beide uit in je antwoord."""

# Welke provider standaard wordt gebruikt: expliciet via LLM_PROVIDER, anders
# automatisch "gemini" zodra er een API-key in de omgeving (.env) staat — zodat het
# toevoegen van enkel een key voldoende is — en anders "ollama".
def _default_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit in ("ollama", "gemini"):
        return explicit
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "ollama"


# Standaardwaarden. Het env-var OLLAMA_MODEL blijft als standaardmodel werken.
DEFAULT_SETTINGS: dict = {
    # ── Provider-keuze ──
    "provider": _default_provider(),            # "ollama" (lokaal) of "gemini" (cloud)
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),

    # ── LLM (Ollama) ──
    "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
    "temperature": 0.0,      # 0 = deterministisch/feitelijk, hoger = creatiever
    "top_p": 0.9,            # nucleus sampling
    "top_k": 40,             # beperk tot k meest waarschijnlijke tokens
    "repeat_penalty": 1.1,   # ontmoedig herhaling
    "num_predict": 512,      # max. aantal tokens in het antwoord (-1 = oneindig)
    "num_ctx": 4096,         # contextvenster (tokens)
    "seed": 0,               # 0 = vaste seed → reproduceerbaar voor testen
    "system_prompt": _DEFAULT_SYSTEM_PROMPT,

    # ── Zoeken / retrieval ──
    "top_n": 2,              # aantal handleidingsecties dat naar de LLM gaat (context)
    "bronnen_tonen": 1,      # aantal bronnen dat aan de gebruiker getoond wordt
    "drempel_globaal": 0.42, # min. hybride score zonder handleidingfilter
    "drempel_filter": 0.28,  # min. hybride score met handleidingfilter
}

# Welke sleutels horen bij de Ollama-aanroep (options=...)
_LLM_OPTION_KEYS = (
    "temperature", "top_p", "top_k",
    "repeat_penalty", "num_predict", "num_ctx", "seed",
)

# Numerieke grenzen voor validatie (min, max)
_BOUNDS = {
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

_current: dict | None = None


def _load_from_disk() -> dict:
    settings = deepcopy(DEFAULT_SETTINGS)
    if os.path.exists(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, encoding="utf-8") as f:
                stored = json.load(f)
            # alleen bekende sleutels overnemen
            for key in DEFAULT_SETTINGS:
                if key in stored:
                    settings[key] = stored[key]
            logger.info("Admin-instellingen geladen van schijf.")
        except Exception as e:
            logger.warning("Kon admin_settings.json niet lezen: %s", e)
    return settings


def get_settings() -> dict:
    """Geef een kopie van de huidige instellingen terug."""
    global _current
    if _current is None:
        _current = _load_from_disk()
    return deepcopy(_current)


def get_llm_options() -> dict:
    """Geef de Ollama options-dict terug (temperature, top_p, ...)."""
    settings = get_settings()
    return {k: settings[k] for k in _LLM_OPTION_KEYS}


def _validate(key: str, value):
    """Cast en begrens een waarde; gooi ValueError bij ongeldige invoer."""
    if key == "system_prompt":
        return str(value)
    if key == "provider":
        value = str(value).strip().lower()
        if value not in ("ollama", "gemini"):
            raise ValueError("provider moet 'ollama' of 'gemini' zijn")
        return value
    if key in ("model", "gemini_model"):
        value = str(value).strip()
        if not value:
            raise ValueError(f"{key} mag niet leeg zijn")
        return value

    default = DEFAULT_SETTINGS[key]
    try:
        value = int(value) if isinstance(default, int) else float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} moet een getal zijn")

    if key in _BOUNDS:
        lo, hi = _BOUNDS[key]
        value = max(lo, min(hi, value))
    return value


def update_settings(new: dict) -> dict:
    """Werk een of meer instellingen bij, valideer, en sla op. Geef het resultaat terug."""
    global _current
    settings = get_settings()
    for key, value in new.items():
        if key not in DEFAULT_SETTINGS:
            continue  # onbekende sleutels negeren
        settings[key] = _validate(key, value)
    _current = settings
    _write_to_disk(settings)
    return deepcopy(settings)


def reset_settings() -> dict:
    """Zet alle instellingen terug naar de standaardwaarden."""
    global _current
    _current = deepcopy(DEFAULT_SETTINGS)
    _write_to_disk(_current)
    return deepcopy(_current)


def _write_to_disk(settings: dict) -> None:
    try:
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Kon admin_settings.json niet schrijven: %s", e)
