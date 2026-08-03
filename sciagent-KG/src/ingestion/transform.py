import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

from src.text_utils import normalize_name


def _clean_text(value: Any) -> str | None:
    """Return a stripped string, treating blank values as missing."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _stable_id(prefix: str, value: str) -> str:
    """Create an id that remains stable when the same record is loaded again."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _version_number(label: str, fallback: int) -> int:
    match = re.fullmatch(r"v(\d+)", label, flags=re.IGNORECASE)
    return int(match.group(1)) if match else fallback


def _created_at(value: Any) -> str | None:
    raw_value = _clean_text(value)
    if raw_value is None:
        return None
    try:
        parsed = parsedate_to_datetime(raw_value)
        return parsed.isoformat()
    except (TypeError, ValueError, OverflowError):
        # Preserve ISO-8601 timestamps if the source format changes.
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None


def transform(record: dict[str, Any]) -> dict[str, Any]:
    """Transform one arXiv JSONL record into parameters for the UPSERT query."""
    arxiv_id = str(record["id"]).strip()

    authors = []
    for position, author in enumerate(record.get("authors_parsed") or [], start=1):
        if not author:
            continue
        family_name = _clean_text(author[0]) or ""
        given_names = _clean_text(author[1] if len(author) > 1 else None) or ""
        suffix = _clean_text(author[2] if len(author) > 2 else None)
        display_name = " ".join(
            part for part in (given_names, family_name, suffix) if part
        )
        normalized_name = normalize_name(display_name)
        authors.append(
            {
                # The source has no ORCID/author key; this deterministic name-based
                # id makes repeated loads idempotent, though names can still collide.
                "author_id": _stable_id("author", normalized_name),
                "display_name": display_name,
                "position": position,
                "family_name": family_name,
                "given_names": given_names,
                "suffix": suffix,
                "normalized_name": normalized_name,
            }
        )

    categories = [
        {"code": code, "position": position, "primary": position == 1}
        for position, code in enumerate(
            (_clean_text(record.get("categories")) or "").split(), start=1
        )
    ]

    versions = []
    for position, version in enumerate(record.get("versions") or [], start=1):
        label = _clean_text(version.get("version")) or f"v{position}"
        versions.append(
            {
                "version_id": f"{arxiv_id}-{label}",
                "version_number": _version_number(label, position),
                "label": label,
                "created_at": _created_at(version.get("created")),
            }
        )

    submitter_name = _clean_text(record.get("submitter"))
    submitter = None
    if submitter_name:
        normalized_submitter = normalize_name(submitter_name)
        submitter = {
            "submitter_id": _stable_id("submitter", normalized_submitter),
            "name": submitter_name,
            "normalized_name": normalized_submitter,
        }

    journal_reference = _clean_text(record.get("journal-ref"))
    journal = None
    if journal_reference:
        normalized_journal = normalize_name(journal_reference)
        journal = {
            "journal_id": _stable_id("journal", normalized_journal),
            "name": journal_reference,
            "normalized_name": normalized_journal,
            "journal_reference_raw": journal_reference,
        }

    report_number = _clean_text(record.get("report-no"))
    report = {"report_number": report_number} if report_number else None

    return {
        "arxiv_id": arxiv_id,
        "title": _clean_text(record.get("title")),
        "abstract": _clean_text(record.get("abstract")),
        "comments": _clean_text(record.get("comments")),
        "doi": _clean_text(record.get("doi")),
        "license": _clean_text(record.get("license")),
        "update_date": _clean_text(record.get("update_date")),
        "source": "arXiv",
        "first_submitted_at": versions[0]["created_at"] if versions else None,
        "latest_version": versions[-1]["label"] if versions else None,
        "version_count": len(versions),
        "authors": authors,
        "categories": categories,
        "versions": versions,
        "submitter": submitter,
        "journal": journal,
        "report": report,
    }
