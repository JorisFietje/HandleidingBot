"""Embeddings: het laden van het semantische model en het scoren van secties.

Het embedding-model (sentence-transformers) wordt lazy geladen — pas bij de eerste
aanroep — zodat het importeren van dit package goedkoop blijft. `_compute_embeddings`
vult elke `Section` met een genormaliseerde vector; `_cosine_scores` berekent de
cosine-similariteit van een vraagvector tegen een lijst secties.

Berekende vectoren worden gecachet op schijf (embeddings_cache.npz). De cache is een
afbeelding van een tekst-hash → vector. Bij een herstart worden ongewijzigde secties
uit de cache geladen en alleen nieuwe/gewijzigde secties opnieuw geëncodeerd, wat de
opstarttijd flink verkort. De cache hoort bij één embedding-model; verandert het
model, dan wordt de cache genegeerd en opnieuw opgebouwd.
"""

import os
import hashlib
import logging

import numpy as np

from .model import Section

logger = logging.getLogger(__name__)

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "embeddings_cache.npz")

# ── Embeddings model (lazy geladen) ───────────────────────────────────────────
_model = None

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Laden van embedding model...")
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model geladen.")
    return _model


def _text_hash(tekst: str) -> str:
    return hashlib.sha1(tekst.encode("utf-8")).hexdigest()


def _normaliseer(vecs: np.ndarray) -> np.ndarray:
    """Normaliseer rij-vectoren zodat cosine-similariteit een dot-product wordt."""
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.maximum(norms, 1e-10)


def _laad_cache() -> dict[str, np.ndarray]:
    """Lees de schijf-cache. Geeft {tekst_hash: vector} terug, of leeg bij een ander
    model of een onleesbaar/ontbrekend bestand."""
    if not os.path.exists(_CACHE_PATH):
        return {}
    try:
        data = np.load(_CACHE_PATH, allow_pickle=True)
        if str(data["model"]) != _MODEL_NAME:
            logger.info("Embedding-cache hoort bij een ander model; wordt opnieuw opgebouwd.")
            return {}
        keys = data["keys"]
        vecs = data["vecs"]
        return {str(k): vecs[i] for i, k in enumerate(keys)}
    except Exception as e:
        logger.warning("Kon embeddings-cache niet lezen: %s", e)
        return {}


def _schrijf_cache(cache: dict[str, np.ndarray]) -> None:
    if not cache:
        return
    try:
        keys = np.array(list(cache.keys()))
        vecs = np.stack(list(cache.values()))
        np.savez(_CACHE_PATH, model=np.array(_MODEL_NAME), keys=keys, vecs=vecs)
    except Exception as e:
        logger.warning("Kon embeddings-cache niet schrijven: %s", e)


def _compute_embeddings(handleidingen: dict[str, list[Section]]) -> None:
    alle_secties = [s for secties in handleidingen.values() for s in secties]
    if not alle_secties:
        return

    teksten = [f"{s.title}\n{s.content}" for s in alle_secties]
    hashes  = [_text_hash(t) for t in teksten]

    cache = _laad_cache()

    # Bepaal welke secties opnieuw geëncodeerd moeten worden (cache-misses).
    ontbreekt_idx = [i for i, h in enumerate(hashes) if h not in cache]
    if ontbreekt_idx:
        model = _get_model()
        nieuwe = model.encode(
            [teksten[i] for i in ontbreekt_idx],
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        nieuwe = _normaliseer(nieuwe)
        for j, i in enumerate(ontbreekt_idx):
            cache[hashes[i]] = nieuwe[j]
        logger.info(
            "Embeddings: %d nieuw berekend, %d uit cache.",
            len(ontbreekt_idx), len(alle_secties) - len(ontbreekt_idx),
        )
    else:
        logger.info("Embeddings: alle %d secties uit cache.", len(alle_secties))

    for section, h in zip(alle_secties, hashes):
        section._embedding = cache[h]

    # Schrijf de (mogelijk uitgebreide) cache terug. We bewaren alleen wat nu in
    # gebruik is, zodat verwijderde handleidingen niet eindeloos blijven hangen.
    _schrijf_cache({h: cache[h] for h in hashes})


def _cosine_scores(
    vraag_vec: np.ndarray,
    secties: list[Section],
) -> list[float]:
    matrix = np.stack([s._embedding for s in secties])
    return (matrix @ vraag_vec).tolist()
