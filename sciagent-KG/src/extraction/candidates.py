"""Stage A: fast, cheap candidate-phrase extraction with spaCy.

Runs on CPU across the whole corpus before the LLM ever sees a paper -- its
job isn't to be correct, it's to narrow down what the (expensive) LLM stage
has to look for, by handing it a shortlist of noun phrases instead of raw
text to hunt through blind.
"""

import spacy
from spacy.language import Language

DEFAULT_SPACY_MODEL = "en_core_web_sm"
MIN_CHUNK_TOKENS = 2
MAX_CHUNK_TOKENS = 6
MAX_CANDIDATES = 25

_model_cache: dict[str, Language] = {}


def load_model(model_name: str = DEFAULT_SPACY_MODEL) -> Language:
    if model_name not in _model_cache:
        _model_cache[model_name] = spacy.load(model_name)
    return _model_cache[model_name]


def extract_candidates(text: str, nlp: Language) -> list[str]:
    """Noun-chunk candidate phrases, deduplicated case-insensitively, in
    order of first appearance, capped at MAX_CANDIDATES."""
    doc = nlp(text)
    seen: set[str] = set()
    candidates: list[str] = []

    for chunk in doc.noun_chunks:
        content_tokens = [t for t in chunk if not t.is_stop and not t.is_punct]
        if not (MIN_CHUNK_TOKENS <= len(content_tokens) <= MAX_CHUNK_TOKENS):
            continue

        phrase = chunk.text.strip()
        key = phrase.lower()
        if not phrase or key in seen:
            continue

        seen.add(key)
        candidates.append(phrase)
        if len(candidates) >= MAX_CANDIDATES:
            break

    return candidates
