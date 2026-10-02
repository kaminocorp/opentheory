"""``source.pin`` — pin a bibliographic source through the existing literature providers.

A claim should cite a real paper or work, not a model paraphrase. This instrument is the
unified entry: one locator (DOI / arXiv id / OpenAlex ``W…`` id / bibliographic query) plus
an optional provider. It **delegates** to the shipped ``crossref.lookup`` / ``arxiv.lookup`` /
``openalex.lookup`` fetchers — no second HTTP path, no invented citation.

Auto-route (``provider=auto``, the default):

- OpenAlex work id → OpenAlex
- arXiv id → arXiv export API
- DOI → Crossref identity lookup
- anything else → Crossref bibliographic query (public, no key)

Forced ``provider=arxiv`` requires a plausible arXiv id (that API is identity-only).
Forced ``provider=openalex`` accepts a ``W…`` id, a DOI, or a search query.
Forced ``provider=crossref`` accepts a DOI or a bibliographic query.

Outcomes: a confirmed work is ``result``; a successful empty match is ``undecided`` —
never a fake paper. A failed fetch (``RetrievalError``) means the instrument did not
run, so the write path mints nothing. ``run`` is ``async``. Network I/O is the same
timeout-bounded ``RetrievalClient`` the lookups already use; tests inject fakes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._literature import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
)
from app.toolbench.instruments.arxiv_lookup import ArxivLookup, ArxivLookupInput
from app.toolbench.instruments.crossref_lookup import CrossrefLookup, CrossrefLookupInput
from app.toolbench.instruments.openalex_lookup import OpenAlexLookup, OpenAlexLookupInput
from app.toolbench.pinning import PinRecord

ProviderName = Literal["crossref", "arxiv", "openalex"]
ProviderChoice = Literal["auto", "crossref", "arxiv", "openalex"]


class SourcePinInput(BaseModel):
    locator: str = Field(
        min_length=1,
        max_length=512,
        description=(
            "A DOI, arXiv id (prefer vN), OpenAlex W… id, or a bibliographic query. "
            "Wrappers (doi:, arxiv:, https://doi.org/…, https://arxiv.org/abs/…) are accepted."
        ),
    )
    provider: ProviderChoice = Field(
        default="auto",
        description=(
            "Which catalog to ask. `auto` routes by identifier shape; a free-text query "
            "goes to Crossref (public, no key). `arxiv` requires an arXiv id."
        ),
    )

    @field_validator("locator")
    @classmethod
    def _strip_locator(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("locator must not be empty")
        return text

    @model_validator(mode="after")
    def _arxiv_needs_an_id(self) -> SourcePinInput:
        if self.provider == "arxiv" and normalize_arxiv_id(self.locator) is None:
            raise ValueError(
                "provider=arxiv requires an arXiv id (e.g. 1706.03762v7); "
                "bibliographic queries go to Crossref or OpenAlex"
            )
        return self


class SourcePinOutput(BaseModel):
    found: bool
    provider: ProviderName
    match_count: int = 0
    pin: PinRecord


def resolve_source_pin_route(
    locator: str, provider: ProviderChoice
) -> tuple[ProviderName, dict[str, str]]:
    """Map a locator + provider choice onto one existing lookup's inputs.

    Raises ``ValueError`` when the choice cannot be served honestly (empty locator, or
    ``provider=arxiv`` with something that is not an arXiv id). Callers must not invent
    a citation to paper over that.
    """
    text = locator.strip()
    if not text:
        raise ValueError("locator must not be empty")

    if provider == "arxiv":
        arxiv_id = normalize_arxiv_id(text)
        if arxiv_id is None:
            raise ValueError(
                "provider=arxiv requires an arXiv id (e.g. 1706.03762v7); "
                "bibliographic queries go to Crossref or OpenAlex"
            )
        return "arxiv", {"arxiv_id": arxiv_id}

    if provider == "openalex":
        oid = normalize_openalex_id(text)
        if oid:
            return "openalex", {"openalex_id": oid}
        doi = normalize_doi(text)
        if doi:
            return "openalex", {"doi": doi}
        return "openalex", {"query": text}

    if provider == "crossref":
        doi = normalize_doi(text)
        if doi:
            return "crossref", {"doi": doi}
        return "crossref", {"query": text}

    oid = normalize_openalex_id(text)
    if oid:
        return "openalex", {"openalex_id": oid}
    arxiv_id = normalize_arxiv_id(text)
    if arxiv_id:
        return "arxiv", {"arxiv_id": arxiv_id}
    doi = normalize_doi(text)
    if doi:
        return "crossref", {"doi": doi}
    return "crossref", {"query": text}


class SourcePin:
    """Pin a bibliographic source via Crossref / arXiv / OpenAlex (see module docstring)."""

    name = "source.pin"
    namespace = "source"
    version = "0.1.0"
    engine = "source.pin"
    engine_version = "literature-delegates"
    description = (
        "Pin a scholarly work by DOI, arXiv id, OpenAlex id, or bibliographic query. "
        "Routes to Crossref, arXiv, or OpenAlex and returns the existing source.pin "
        "record (url, source_url, retrieved_at, raw_response_hash). Never invents a "
        "citation. A successful empty match is undecided; a failed fetch mints nothing."
    )
    InputModel = SourcePinInput
    OutputModel = SourcePinOutput

    def __init__(
        self,
        *,
        crossref: CrossrefLookup | None = None,
        arxiv: ArxivLookup | None = None,
        openalex: OpenAlexLookup | None = None,
    ) -> None:
        self._crossref = crossref or CrossrefLookup()
        self._arxiv = arxiv or ArxivLookup()
        self._openalex = openalex or OpenAlexLookup()

    async def run(self, inputs: SourcePinInput, assumptions: dict[str, Any]) -> InstrumentResult:
        provider, inner_inputs = resolve_source_pin_route(inputs.locator, inputs.provider)
        if provider == "crossref":
            inner = await self._crossref.run(
                CrossrefLookupInput.model_validate(inner_inputs), assumptions
            )
        elif provider == "arxiv":
            inner = await self._arxiv.run(
                ArxivLookupInput.model_validate(inner_inputs), assumptions
            )
        else:
            inner = await self._openalex.run(
                OpenAlexLookupInput.model_validate(inner_inputs), assumptions
            )

        found = bool(inner.output.get("found"))
        match_count = inner.output.get("match_count")
        if not isinstance(match_count, int):
            match_count = 1 if found else 0
        output = SourcePinOutput(
            found=found,
            provider=provider,
            match_count=match_count,
            pin=PinRecord.model_validate(inner.output["pin"]),
        )
        return InstrumentResult(
            output=output.model_dump(mode="json"),
            status=ResultStatus.RESULT if found else ResultStatus.UNDECIDED,
            artifact_kind="pinned_source",
            source_type=inner.source_type or provider,
        )


SOURCE_PIN = SourcePin()
