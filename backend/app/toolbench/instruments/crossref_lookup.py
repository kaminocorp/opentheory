"""``crossref.lookup`` — DOI / bibliographic lookup via the Crossref REST API, pinned.

Given a DOI (or a bibliographic query string) it fetches Crossref work metadata and, on a genuine
hit, pins the DOI as citable evidence: ``url`` (``https://doi.org/…``) + ``source_url`` (the
works endpoint actually hashed) + ``retrieved_at`` + ``raw_response_hash``. Snippets only
(title / authors / year / container) — never a full-text copy.

Outcomes (the honesty rule): a confirmed work with a DOI is ``result``; a successful lookup that
found nothing (HTTP 404, or a bibliographic search with no items) is ``undecided`` — escalate,
never a fake paper. A *failed* fetch (network / non-2xx other than 404) is a
:class:`~app.toolbench.retrieval.RetrievalError`: the instrument did not run, so the write path
mints nothing. ``run`` is ``async``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._literature import (
    citation_line,
    crossref_bibliographic_url,
    crossref_works_url,
    doi_citation_url,
    first_string,
    format_authors,
    literature_pin,
    normalize_doi,
    year_from_date_parts,
)
from app.toolbench.pinning import PinRecord
from app.toolbench.retrieval import Fetcher, RetrievalClient

_PROVIDER = "crossref"
_LICENSE_NOTE = (
    "Crossref work metadata is used for citation; pinned by DOI, not redistributed as full text. "
    "See https://www.crossref.org/documentation/retrieve-metadata/rest-api/"
)


class CrossrefLookupInput(BaseModel):
    doi: str | None = Field(
        default=None,
        max_length=256,
        description="A DOI, bare or wrapped (10.1038/…, https://doi.org/…, doi:…). "
        "Preferred when known — this is an identity lookup, not a search.",
    )
    query: str | None = Field(
        default=None,
        max_length=512,
        description="A bibliographic query (title / author / year) used only when `doi` is absent. "
        "The top hit is a candidate; result is reported only when that hit carries a DOI.",
    )

    @model_validator(mode="after")
    def _doi_or_query(self) -> CrossrefLookupInput:
        doi = self.doi.strip() if isinstance(self.doi, str) else None
        query = self.query.strip() if isinstance(self.query, str) else None
        if doi:
            if normalize_doi(doi) is None:
                raise ValueError("doi must look like 10.xxxx/suffix (optionally wrapped)")
            self.doi = doi
            self.query = None
            return self
        if query:
            self.doi = None
            self.query = query
            return self
        raise ValueError("provide a DOI or a bibliographic query")


class CrossrefLookupOutput(BaseModel):
    found: bool
    match_count: int = 0
    pin: PinRecord


def _authors_from_crossref(work: dict[str, Any]) -> str | None:
    authors = work.get("author")
    if not isinstance(authors, list):
        return None
    names: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        family = author.get("family")
        given = author.get("given")
        if isinstance(family, str) and family.strip():
            names.append(
                f"{family.strip()}, {given.strip()}" if isinstance(given, str) and given.strip()
                else family.strip()
            )
        elif isinstance(given, str) and given.strip():
            names.append(given.strip())
    return format_authors(names)


def _work_from_payload(parsed: Any, *, search: bool) -> tuple[dict[str, Any] | None, int]:
    """Return (top work, match_count). Crossref wraps a work in ``message``."""
    if not isinstance(parsed, dict):
        return None, 0
    message = parsed.get("message")
    if not isinstance(message, dict):
        return None, 0
    if search:
        total = message.get("total-results")
        items = message.get("items")
        count = total if isinstance(total, int) and total >= 0 else (
            len(items) if isinstance(items, list) else 0
        )
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0], count
        return None, count
    # Single-work payload (DOI lookup). A 404 error body has no DOI.
    if first_string(message.get("DOI")):
        return message, 1
    return None, 0


class CrossrefLookup:
    """Look up a work via the Crossref REST API and pin the DOI (see module docstring)."""

    name = "crossref.lookup"
    namespace = "crossref"
    version = "0.1.0"
    engine = "crossref"
    engine_version = "works-api"
    description = (
        "Look up a scholarly work by DOI or bibliographic query via the Crossref REST API; "
        "returns the DOI pinned as a citable record (url, retrieved_at, raw_response_hash). "
        "Metadata snippets only — never full text."
    )
    InputModel = CrossrefLookupInput
    OutputModel = CrossrefLookupOutput

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self._fetcher: Fetcher = fetcher or RetrievalClient()

    async def run(
        self, inputs: CrossrefLookupInput, assumptions: dict[str, Any]
    ) -> InstrumentResult:
        doi = normalize_doi(inputs.doi) if inputs.doi else None
        search = doi is None
        url = crossref_works_url(doi) if doi else crossref_bibliographic_url(inputs.query or "")
        retrieval = await self._fetcher.get_json(url)
        if retrieval.status_code == 404:
            work, match_count = None, 0
        else:
            work, match_count = _work_from_payload(retrieval.parsed, search=search)

        identifier = normalize_doi(first_string(work.get("DOI")) or "") if work else None
        found = work is not None and identifier is not None
        pin = literature_pin(
            provider=_PROVIDER,
            retrieval=retrieval,
            license_note=_LICENSE_NOTE,
            identifier=identifier if found else None,
            citation_url=doi_citation_url(identifier) if found and identifier else None,
            title=first_string(work.get("title")) if found and work else None,
            citation=citation_line(
                authors=_authors_from_crossref(work) if work else None,
                year=year_from_date_parts(work.get("issued")) if work else None,
                container=first_string(work.get("container-title")) if work else None,
            )
            if found
            else None,
        )
        output = CrossrefLookupOutput(found=found, match_count=match_count, pin=pin)
        return InstrumentResult(
            output=output.model_dump(mode="json"),
            status=ResultStatus.RESULT if found else ResultStatus.UNDECIDED,
            artifact_kind="pinned_source",
            source_type=_PROVIDER,
        )


CROSSREF_LOOKUP = CrossrefLookup()
