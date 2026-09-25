"""``arxiv.lookup`` — pin an arXiv e-print by id (prefer versioned ``vN``) via the arXiv Atom API.

Given an arXiv id it fetches the official export API (Atom XML — there is no JSON works
endpoint) and, on a genuine hit, pins the **versioned** id the API actually returned:
``url`` (``https://arxiv.org/abs/…vN``) + ``source_url`` (the export query hashed) +
``retrieved_at`` + ``raw_response_hash``. Title / authors / published date as snippets —
never the PDF.

Outcomes (the honesty rule): a feed with an entry is ``result``; a successful query with an
empty feed is ``undecided`` — escalate, never a fake e-print. A *failed* fetch (network /
non-2xx other than 404) is a :class:`~app.toolbench.retrieval.RetrievalError`: the instrument
did not run, so the write path mints nothing. ``run`` is ``async``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._literature import (
    arxiv_citation_url,
    arxiv_query_url,
    citation_line,
    format_authors,
    literature_pin,
    normalize_arxiv_id,
    snippet,
)
from app.toolbench.pinning import PinRecord
from app.toolbench.retrieval import RetrievalClient, TextFetcher

_PROVIDER = "arxiv"
_LICENSE_NOTE = (
    "arXiv metadata is used for citation; pinned by arXiv id (prefer vN), not redistributed "
    "as full text. See https://info.arxiv.org/help/api/tou.html"
)
_ATOM = "{http://www.w3.org/2005/Atom}"


class ArxivLookupInput(BaseModel):
    arxiv_id: str = Field(
        min_length=3,
        max_length=64,
        description=(
            "An arXiv id, preferably versioned (2301.07041v1). Bare, `arxiv:`-prefixed, or an "
            "abs/pdf URL are accepted. Unversioned ids pin whatever version the API returns."
        ),
    )

    @field_validator("arxiv_id")
    @classmethod
    def _plausible_id(cls, value: str) -> str:
        normalized = normalize_arxiv_id(value)
        if normalized is None:
            raise ValueError(
                "arxiv_id must look like 2301.07041v1 (or an old-style id such as hep-th/9901001v1)"
            )
        return normalized


class ArxivLookupOutput(BaseModel):
    found: bool
    pin: PinRecord


def _local_text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    text = element.text.strip()
    return text or None


def _entry_from_atom(raw: str) -> dict[str, Any] | None:
    """Parse the first Atom ``entry``, or ``None`` when the feed is empty / unparseable.

    Unparseable XML from a *successful* fetch is treated as no match rather than a crash — the
    pin still records the raw bytes so a verifier can see what arrived. A transport failure
    never reaches here.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    entry = root.find(f"{_ATOM}entry")
    if entry is None:
        return None
    authors = [
        name
        for author in entry.findall(f"{_ATOM}author")
        if (name := _local_text(author.find(f"{_ATOM}name")))
    ]
    published = _local_text(entry.find(f"{_ATOM}published"))
    year = published[:4] if published and published[:4].isdigit() else None
    atom_id = _local_text(entry.find(f"{_ATOM}id"))
    return {
        "atom_id": atom_id,
        "title": snippet(_local_text(entry.find(f"{_ATOM}title")), limit=400),
        "authors": authors,
        "year": year,
    }


def _versioned_id(atom_id: str | None, requested: str) -> str | None:
    """Prefer the version the API actually returned (the Atom id), falling back to the request."""
    if atom_id:
        # Typical: http://arxiv.org/abs/2301.07041v1
        normalized = normalize_arxiv_id(atom_id.rsplit("/", 1)[-1])
        if normalized:
            return normalized
    return normalize_arxiv_id(requested)


class ArxivLookup:
    """Look up an e-print via the arXiv export API and pin the versioned id."""

    name = "arxiv.lookup"
    namespace = "arxiv"
    version = "0.1.0"
    engine = "arxiv"
    engine_version = "export-api"
    description = (
        "Look up an arXiv e-print by id (prefer versioned vN) via the arXiv export API; "
        "returns the versioned id pinned as a citable record (url, retrieved_at, "
        "raw_response_hash). Metadata snippets only — never the PDF."
    )
    InputModel = ArxivLookupInput
    OutputModel = ArxivLookupOutput

    def __init__(self, fetcher: TextFetcher | None = None) -> None:
        self._fetcher: TextFetcher = fetcher or RetrievalClient()

    async def run(self, inputs: ArxivLookupInput, assumptions: dict[str, Any]) -> InstrumentResult:
        url = arxiv_query_url(inputs.arxiv_id)
        retrieval = await self._fetcher.get_text(url)
        entry = None if retrieval.status_code == 404 else _entry_from_atom(retrieval.raw_response)
        identifier = _versioned_id(entry.get("atom_id") if entry else None, inputs.arxiv_id)
        found = entry is not None and identifier is not None
        pin = literature_pin(
            provider=_PROVIDER,
            retrieval=retrieval,
            license_note=_LICENSE_NOTE,
            identifier=identifier if found else None,
            citation_url=arxiv_citation_url(identifier) if found and identifier else None,
            title=entry.get("title") if found and entry else None,
            citation=citation_line(
                authors=format_authors(entry.get("authors") or []) if entry else None,
                year=entry.get("year") if entry else None,
                container="arXiv",
            )
            if found
            else None,
        )
        output = ArxivLookupOutput(found=found, pin=pin)
        return InstrumentResult(
            output=output.model_dump(mode="json"),
            status=ResultStatus.RESULT if found else ResultStatus.UNDECIDED,
            artifact_kind="pinned_source",
            source_type=_PROVIDER,
        )


ARXIV_LOOKUP = ArxivLookup()
