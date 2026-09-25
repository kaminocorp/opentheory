"""``openalex.lookup`` — DOI / OpenAlex-id / bibliographic lookup, pinned.

Given a DOI, an OpenAlex work id (``W…``), or a search query it fetches the OpenAlex works
API and, on a genuine hit, pins the work id (and DOI when present) as citable evidence.
Snippets only — never a full-text copy.

**Key posture (2026).** OpenAlex retired the polite-pool ``mailto`` on 2026-02-13; a free API
key is the real quota. This instrument does **not** hard-require ``OPENALEX_API_KEY``: without
one it still calls the public demo pool (tiny daily budget, fine for a human lookup; not for
an agent loop). Tests inject a :class:`~app.toolbench.retrieval.Fetcher` and never need a key.
A 401/403/409 from a spent demo pool is a :class:`~app.toolbench.retrieval.RetrievalError`
(mint nothing), not a fake no-match.

Outcomes: a confirmed work is ``result``; a successful empty match (404 / empty search) is
``undecided``. ``run`` is ``async``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._literature import (
    citation_line,
    doi_citation_url,
    format_authors,
    literature_pin,
    normalize_doi,
    normalize_openalex_id,
    openalex_citation_url,
    openalex_search_url,
    openalex_work_url,
    snippet,
)
from app.toolbench.pinning import PinRecord
from app.toolbench.retrieval import Fetcher, RetrievalClient

_PROVIDER = "openalex"
_LICENSE_NOTE = (
    "OpenAlex work metadata is CC0; pinned by OpenAlex id / DOI, not redistributed as full text. "
    "See https://docs.openalex.org/"
)


class OpenAlexLookupInput(BaseModel):
    doi: str | None = Field(
        default=None,
        max_length=256,
        description="A DOI (bare or wrapped). Preferred identity lookup when known.",
    )
    openalex_id: str | None = Field(
        default=None,
        max_length=64,
        description="An OpenAlex work id (W2741809807) or openalex.org URL.",
    )
    query: str | None = Field(
        default=None,
        max_length=512,
        description="A search query used only when neither `doi` nor `openalex_id` is set. "
        "The top hit is a candidate; result is reported only when that hit has an id.",
    )

    @model_validator(mode="after")
    def _one_locator(self) -> OpenAlexLookupInput:
        doi_raw = self.doi.strip() if isinstance(self.doi, str) else None
        oid_raw = self.openalex_id.strip() if isinstance(self.openalex_id, str) else None
        query = self.query.strip() if isinstance(self.query, str) else None
        if oid_raw:
            if normalize_openalex_id(oid_raw) is None:
                raise ValueError("openalex_id must look like W1234567890")
            self.openalex_id = oid_raw
            self.doi = None
            self.query = None
            return self
        if doi_raw:
            if normalize_doi(doi_raw) is None:
                raise ValueError("doi must look like 10.xxxx/suffix (optionally wrapped)")
            self.doi = doi_raw
            self.openalex_id = None
            self.query = None
            return self
        if query:
            self.doi = None
            self.openalex_id = None
            self.query = query
            return self
        raise ValueError("provide a DOI, an OpenAlex work id, or a search query")


class OpenAlexLookupOutput(BaseModel):
    found: bool
    match_count: int = 0
    pin: PinRecord


def _authors_from_openalex(work: dict[str, Any]) -> str | None:
    authorships = work.get("authorships")
    if not isinstance(authorships, list):
        return None
    names: list[str] = []
    for row in authorships:
        if not isinstance(row, dict):
            continue
        author = row.get("author")
        if isinstance(author, dict):
            display = author.get("display_name")
            if isinstance(display, str) and display.strip():
                names.append(display.strip())
    return format_authors(names)


def _work_id(work: dict[str, Any]) -> str | None:
    raw = work.get("id")
    if isinstance(raw, str):
        return normalize_openalex_id(raw)
    return None


def _work_from_payload(parsed: Any, *, search: bool) -> tuple[dict[str, Any] | None, int]:
    if not isinstance(parsed, dict):
        return None, 0
    if search:
        meta = parsed.get("meta")
        results = parsed.get("results")
        count = 0
        if isinstance(meta, dict) and isinstance(meta.get("count"), int):
            count = meta["count"]
        elif isinstance(results, list):
            count = len(results)
        if isinstance(results, list) and results and isinstance(results[0], dict):
            return results[0], count
        return None, count
    if _work_id(parsed) or (isinstance(parsed.get("doi"), str) and parsed.get("doi")):
        return parsed, 1
    return None, 0


def _default_fetcher() -> RetrievalClient:
    key = (settings.openalex_api_key or "").strip()
    # The key rides as a request param only — never in Retrieval.url / the pin's source_url.
    return RetrievalClient(params={"api_key": key} if key else None)


class OpenAlexLookup:
    """Look up a work via the OpenAlex works API and pin the id (see module docstring)."""

    name = "openalex.lookup"
    namespace = "openalex"
    version = "0.1.0"
    engine = "openalex"
    engine_version = "works-api"
    description = (
        "Look up a scholarly work by DOI, OpenAlex id, or search via the OpenAlex works API; "
        "returns the work id / DOI pinned as a citable record. Optional OPENALEX_API_KEY "
        "(recommended in production as of 2026); degrades to the public demo pool when absent. "
        "Metadata snippets only — never full text."
    )
    InputModel = OpenAlexLookupInput
    OutputModel = OpenAlexLookupOutput

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self._fetcher: Fetcher = fetcher or _default_fetcher()

    async def run(
        self, inputs: OpenAlexLookupInput, assumptions: dict[str, Any]
    ) -> InstrumentResult:
        oid = normalize_openalex_id(inputs.openalex_id) if inputs.openalex_id else None
        doi = normalize_doi(inputs.doi) if inputs.doi else None
        search = oid is None and doi is None
        url = (
            openalex_search_url(inputs.query or "")
            if search
            else openalex_work_url(doi=doi, openalex_id=oid)
        )
        retrieval = await self._fetcher.get_json(url)
        if retrieval.status_code == 404:
            work, match_count = None, 0
        else:
            work, match_count = _work_from_payload(retrieval.parsed, search=search)

        identifier = _work_id(work) if work else None
        work_doi = normalize_doi(str(work.get("doi") or "")) if work else None
        found = work is not None and identifier is not None
        # Cite the DOI when we have one (immutable-id pin); otherwise the OpenAlex page.
        citation_url = (
            doi_citation_url(work_doi) if found and work_doi
            else (openalex_citation_url(identifier) if found and identifier else None)
        )
        year = work.get("publication_year") if work else None
        pin = literature_pin(
            provider=_PROVIDER,
            retrieval=retrieval,
            license_note=_LICENSE_NOTE,
            identifier=identifier if found else None,
            citation_url=citation_url,
            title=snippet(work.get("display_name") if work else None),
            citation=citation_line(
                authors=_authors_from_openalex(work) if work else None,
                year=str(year) if isinstance(year, int) else None,
                container=None,
            )
            if found
            else None,
        )
        output = OpenAlexLookupOutput(found=found, match_count=match_count, pin=pin)
        return InstrumentResult(
            output=output.model_dump(mode="json"),
            status=ResultStatus.RESULT if found else ResultStatus.UNDECIDED,
            artifact_kind="pinned_source",
            source_type=_PROVIDER,
        )


OPENALEX_LOOKUP = OpenAlexLookup()
