"""Lazy, fail-soft spaCy model loading."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

SPACY_MODEL = "en_core_web_sm"


@lru_cache
def get_nlp() -> Any | None:
    """Return the spaCy pipeline (NER only), or None if the model is not installed."""
    try:
        import spacy

        nlp = spacy.load(SPACY_MODEL, disable=["parser", "lemmatizer", "tagger", "attribute_ruler"])
        logger.info("Loaded spaCy model %s (pipes: %s)", SPACY_MODEL, nlp.pipe_names)
        return nlp
    except (ImportError, OSError) as exc:
        logger.warning("spaCy model %s unavailable (%s); NER features disabled. "
                       "Install with: python -m spacy download %s", SPACY_MODEL, exc, SPACY_MODEL)
        return None
