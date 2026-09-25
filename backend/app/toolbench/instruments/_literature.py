"""Shared helpers for Tier-1 literature pin instruments (Crossref / arXiv / OpenAlex).

Normalizes identifiers, formats short citation snippets, and assembles a :class:`PinRecord`
the same way ``oeis.search`` does — ``url`` (human citation) vs ``source_url`` (hashed
response). Snippets only; never a bulk copy of licensed full text.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.toolbench.pinning import PinRecord, build_pin_record
from app.toolbench.retrieval import Retrieval

# Crossref / DataCite DOI shape: 10.<registrant>/<suffix>. We accept a bare DOI or a
# doi.org / dx.doi.org / ``doi:`` wrapper and reject everything else at the input boundary.
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_DOI_PREFIX_RE = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
    re.IGNORECASE,
)

# New-style arXiv (YYMM.NNNNN or YYMM.NNNNN) plus optional ``vN``; old-style archive/YYMMNNN.
_ARXIV_NEW_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
_ARXIV_OLD_RE = re.compile(r"^([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$")
_ARXIV_PREFIX_RE = re.compile(
    r"^(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:\s*)",
    re.IGNORECASE,
)

_OPENALEX_WORK_RE = re.compile(r"^W\d+$", re.IGNORECASE)
_OPENALEX_URL_RE = re.compile(
    r"^https?://(?:www\.)?openalex\.org/(W\d+)$",
    re.IGNORECASE,
)


def normalize_doi(raw: str) -> str | None:
    """Strip wrappers → a bare ``10.…`` DOI, or ``None`` if the token is not a DOI."""
    text = _DOI_PREFIX_RE.sub("", raw.strip())
    return text if _DOI_RE.match(text) else None


def normalize_arxiv_id(raw: str) -> str | None:
    """Strip wrappers → a bare arXiv id (version kept if supplied), or ``None`` if implausible."""
    text = _ARXIV_PREFIX_RE.sub("", raw.strip())
    if text.lower().endswith(".pdf"):
        text = text[: -len(".pdf")]
    if _ARXIV_NEW_RE.match(text) or _ARXIV_OLD_RE.match(text):
        return text
    return None


def normalize_openalex_id(raw: str) -> str | None:
    """Strip wrappers → a bare ``W…`` OpenAlex work id, or ``None``."""
    text = raw.strip()
    match = _OPENALEX_URL_RE.match(text)
    if match:
        return match.group(1).upper()
    if _OPENALEX_WORK_RE.match(text):
        return text.upper()
    return None


def doi_citation_url(doi: str) -> str:
    return f"https://doi.org/{doi}"


def arxiv_citation_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}"


def openalex_citation_url(work_id: str) -> str:
    return f"https://openalex.org/{work_id}"


def crossref_works_url(doi: str) -> str:
    return f"https://api.crossref.org/works/{quote(doi, safe='/')}"


def crossref_bibliographic_url(query: str) -> str:
    return f"https://api.crossref.org/works?query.bibliographic={quote(query)}&rows=5"


def arxiv_query_url(arxiv_id: str) -> str:
    return f"https://export.arxiv.org/api/query?id_list={quote(arxiv_id, safe='/')}"


def openalex_work_url(*, doi: str | None = None, openalex_id: str | None = None) -> str:
    if openalex_id:
        return f"https://api.openalex.org/works/{openalex_id}"
    if doi:
        # Official identity form — avoids nesting a doi.org URL in the path.
        return f"https://api.openalex.org/works/doi:{quote(doi, safe='/')}"
    raise ValueError("openalex_work_url needs a DOI or an OpenAlex id")


def openalex_search_url(query: str) -> str:
    return f"https://api.openalex.org/works?search={quote(query)}&per_page=5"


def first_string(value: Any) -> str | None:
    """Crossref titles/containers arrive as a list of strings; take the first non-blank."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def snippet(text: str | None, *, limit: int = 240) -> str | None:
    """A short cited snippet — citation, not a bulk copy."""
    if not text:
        return None
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def format_authors(names: list[str], *, limit: int = 4) -> str | None:
    cleaned = [n.strip() for n in names if isinstance(n, str) and n.strip()]
    if not cleaned:
        return None
    if len(cleaned) > limit:
        return ", ".join(cleaned[:limit]) + " et al."
    return ", ".join(cleaned)


def citation_line(*, authors: str | None, year: str | None, container: str | None) -> str | None:
    """One-line bibliographic snippet for ``PinRecord.formula`` (the cited-snippet slot)."""
    parts: list[str] = []
    if authors:
        parts.append(authors)
    if year:
        parts.append(f"({year})" if authors else year)
    if container:
        parts.append(container)
    return snippet(" ".join(parts)) if parts else None


def year_from_date_parts(issued: Any) -> str | None:
    """Crossref ``issued.date-parts`` → a 4-digit year string, or ``None``."""
    if not isinstance(issued, dict):
        return None
    parts = issued.get("date-parts")
    if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
        year = parts[0][0]
        if isinstance(year, int) and 1000 <= year <= 3000:
            return str(year)
    return None


def literature_pin(
    *,
    provider: str,
    retrieval: Retrieval,
    license_note: str,
    identifier: str | None,
    citation_url: str | None,
    title: str | None,
    citation: str | None,
) -> PinRecord:
    """Assemble a literature :class:`PinRecord` (identified → cite the work; else the lookup)."""
    return build_pin_record(
        provider=provider,
        url=citation_url if identifier and citation_url else retrieval.url,
        source_url=retrieval.url,
        retrieved_at=retrieval.retrieved_at,
        raw_response=retrieval.raw_response,
        license_note=license_note,
        identifier=identifier,
        name=snippet(title) if identifier else None,
        formula=citation if identifier else None,
    )
