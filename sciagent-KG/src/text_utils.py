import re
import unicodedata


def normalize_name(value: str) -> str:
    """Lowercase, accent-strip, punctuation-strip form used for matching names
    (authors, submitters, journals) regardless of formatting differences."""
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.sub(r"[^\w\s-]", "", normalized, flags=re.UNICODE).split())
