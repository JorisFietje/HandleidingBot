"""LLM-providers: kies tussen lokaal (Ollama) en cloud (Google Gemini).

Dit bestand is de enige plek die "weet" hoe een antwoord bij een taalmodel wordt
opgehaald. De rest van de applicatie (chatbot-package) levert een systeemprompt en
een gebruikersprompt aan en krijgt platte tekst terug — welke provider daarachter
zit, maakt voor de aanroeper niet uit.

Welke provider wordt gebruikt, bepaalt de instelling 'provider' (zie settings.py):
- "ollama"  -> lokaal draaiend model via het ollama-pakket (standaard).
- "gemini"  -> Google Gemini via de cloud. Hiervoor is ALLEEN een GEMINI_API_KEY
               (of GOOGLE_API_KEY) in het .env-bestand nodig; verder hoeft er niets
               te worden aangepast.

Er zijn twee aanroepvormen:
- `generate()`        -> het volledige antwoord in één keer (str).
- `generate_stream()` -> een generator die tekst-chunks oplevert zodra ze binnenkomen,
                          zodat de frontend het antwoord woord-voor-woord kan tonen.

De instellingen voor sampling (temperature, top_p, top_k, ...) komen uit settings;
ze worden per provider naar het juiste formaat vertaald.
"""

import os
import logging
from collections.abc import Iterator

import settings

logger = logging.getLogger(__name__)

# Gemini-client wordt eenmalig opgebouwd en hergebruikt (lazy).
_gemini_client = None


def _api_key() -> str | None:
    """De Gemini-API-key uit de omgeving (.env). Beide gangbare namen worden geaccepteerd."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def gemini_available() -> bool:
    """True als er een API-key aanwezig is om Gemini mee te gebruiken."""
    return bool(_api_key())


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        key = _api_key()
        if not key:
            raise RuntimeError(
                "Geen GEMINI_API_KEY gevonden. Zet GEMINI_API_KEY=... in het .env-bestand."
            )
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


def generate(system_prompt: str, user_prompt: str) -> str:
    """Genereer een antwoord met de in settings ingestelde provider.

    Geeft platte tekst terug. Bij een fout wordt een leesbare ⚠️-melding
    teruggegeven (geen exception), zodat de chat blijft werken. Als Gemini de
    provider is maar faalt (bv. tijdelijk overbelast / 503), wordt automatisch
    teruggevallen op lokaal Ollama."""
    provider = settings.get_settings().get("provider", "ollama")
    if provider != "gemini":
        return _generate_ollama(system_prompt, user_prompt)

    model = settings.get_settings().get("gemini_model", "gemini-2.5-flash")
    try:
        return _generate_gemini(system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("Gemini faalde (%s) — terugval naar lokaal Ollama.", exc)
        terugval = _generate_ollama(system_prompt, user_prompt)
        if not terugval.startswith("⚠️"):
            return terugval
        logger.error("Terugval naar Ollama lukte ook niet.")
        return _gemini_error(model, exc)


def generate_stream(system_prompt: str, user_prompt: str) -> Iterator[str]:
    """Genereer een antwoord als stroom van tekst-chunks (generator).

    Bij een fout wordt één chunk met een leesbare ⚠️-melding opgeleverd, zodat de
    chat blijft werken en de gebruiker de oorzaak ziet. Als Gemini de provider is
    maar faalt vóórdat er tekst is (bv. 503 'high demand'), wordt automatisch
    teruggevallen op lokaal Ollama."""
    provider = settings.get_settings().get("provider", "ollama")
    if provider != "gemini":
        yield from _generate_ollama_stream(system_prompt, user_prompt)
        return

    model = settings.get_settings().get("gemini_model", "gemini-2.5-flash")
    gen = _generate_gemini_stream(system_prompt, user_prompt)
    try:
        eerste = next(gen)
    except StopIteration:
        return  # leeg antwoord
    except Exception as exc:
        # Gemini faalde nog vóór er tekst was → val terug op lokaal Ollama.
        logger.warning("Gemini-stream faalde (%s) — terugval naar lokaal Ollama.", exc)
        yield from _ollama_terugval_stream(system_prompt, user_prompt, _gemini_error(model, exc))
        return

    # Het eerste stukje kwam binnen; de rest streamen we door. Een fout midden in
    # de stream kunnen we niet meer terugdraaien, dus die tonen we als melding.
    yield eerste
    try:
        yield from gen
    except Exception as exc:
        yield _gemini_error(model, exc)


def _ollama_terugval_stream(system_prompt: str, user_prompt: str, gemini_fout: str) -> Iterator[str]:
    """Stream een Ollama-antwoord als terugval. Is Ollama óók niet beschikbaar,
    toon dan de (relevantere) oorspronkelijke Gemini-fout in plaats van de
    Ollama-fout."""
    gen = _generate_ollama_stream(system_prompt, user_prompt)
    try:
        eerste = next(gen)
    except StopIteration:
        yield gemini_fout
        return
    if eerste.startswith("⚠️"):
        yield gemini_fout
        return
    yield eerste
    yield from gen


# ── Ollama (lokaal) ────────────────────────────────────────────────────────────

def _ollama_messages(system_prompt: str, user_prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _ollama_error(model: str, exc: Exception) -> str:
    logger.error("Ollama-fout: %s", exc)
    return (
        f"⚠️ Kon geen antwoord genereren. Is Ollama gestart en model "
        f"'{model}' beschikbaar? (Fout: {exc})"
    )


def _generate_ollama(system_prompt: str, user_prompt: str) -> str:
    try:
        import ollama
    except ImportError:
        return "⚠️ Ollama-pakket niet gevonden. Voer `pip install ollama` uit."

    model = settings.get_settings()["model"]
    try:
        response = ollama.chat(
            model=model,
            messages=_ollama_messages(system_prompt, user_prompt),
            options=settings.get_llm_options(),
        )
        return response["message"]["content"]
    except Exception as exc:
        return _ollama_error(model, exc)


def _generate_ollama_stream(system_prompt: str, user_prompt: str) -> Iterator[str]:
    try:
        import ollama
    except ImportError:
        yield "⚠️ Ollama-pakket niet gevonden. Voer `pip install ollama` uit."
        return

    model = settings.get_settings()["model"]
    try:
        stream = ollama.chat(
            model=model,
            messages=_ollama_messages(system_prompt, user_prompt),
            options=settings.get_llm_options(),
            stream=True,
        )
        for chunk in stream:
            deel = chunk.get("message", {}).get("content", "")
            if deel:
                yield deel
    except Exception as exc:
        yield _ollama_error(model, exc)


# ── Google Gemini (cloud) ───────────────────────────────────────────────────────

def _gemini_params(system_prompt: str) -> tuple[str, dict]:
    """Vertaal de (Ollama-genoemde) settings naar (model, config-kwargs) voor Gemini."""
    s = settings.get_settings()
    model = s.get("gemini_model", "gemini-2.5-flash")
    config_kwargs = {
        "system_instruction": system_prompt,
        "temperature": s["temperature"],
        "top_p": s["top_p"],
        "top_k": s["top_k"],
        "seed": s["seed"],
    }
    # num_predict (-1 = onbeperkt bij Ollama) -> max_output_tokens (weglaten bij -1).
    if s["num_predict"] and s["num_predict"] > 0:
        config_kwargs["max_output_tokens"] = s["num_predict"]
    return model, config_kwargs


def _gemini_error(model: str, exc: Exception) -> str:
    logger.error("Gemini-fout: %s", exc)
    return (
        f"⚠️ Kon geen antwoord genereren via Gemini. Klopt de GEMINI_API_KEY en "
        f"is model '{model}' beschikbaar? (Fout: {exc})"
    )


# Let op: onderstaande functies GOOIEN een exception bij een fout (i.p.v. een
# ⚠️-string terug te geven), zodat generate()/generate_stream() kunnen besluiten
# om terug te vallen op lokaal Ollama.

def _generate_gemini(system_prompt: str, user_prompt: str) -> str:
    from google.genai import types

    model, config_kwargs = _gemini_params(system_prompt)
    client = _get_gemini_client()
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return (response.text or "").strip()


def _generate_gemini_stream(system_prompt: str, user_prompt: str) -> Iterator[str]:
    from google.genai import types

    model, config_kwargs = _gemini_params(system_prompt)
    client = _get_gemini_client()
    stream = client.models.generate_content_stream(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    for chunk in stream:
        if chunk.text:
            yield chunk.text
