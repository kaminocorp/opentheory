"""``source.pin`` — the reusable Tier-1 pattern: turn an external retrieval into a citable record.

A retrieval is only trustworthy evidence if it is *pinned*: the record must carry enough to say
exactly what was seen, when, and from where — because the source is mutable and may say something
different tomorrow. So the pin is ``url`` + ``retrieved_at`` + the identifying answer + a
``raw_response_hash`` (a fingerprint of the exact bytes retrieved). That hash is the honesty anchor:
it proves what was retrieved **without redistributing it** (OEIS's licence is *cite, don't
redistribute* — we store the pin, never a bulk copy).

This is a primitive, not a registry instrument: ``oeis.search`` (and every future external source)
builds its output through :func:`build_pin_record`, so the pin shape is identical everywhere. A
standalone ``source.pin`` instrument that pins an arbitrary user-supplied URL is a later add.
"""

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field


class PinRecord(BaseModel):
    """A citable record of one external retrieval (see module docstring).

    ``identifier`` is *the pin* — the stable handle the source assigns (OEIS's A-number). ``terms``
    is what was queried. ``formula`` / ``name`` are short cited snippets (citation, not bulk copy).
    ``raw_response_hash`` fingerprints the exact response so the record reproduces what was seen.
    """

    provider: str = Field(min_length=1)  # e.g. "oeis"
    identifier: str | None = None  # the pin, e.g. "A000045" (None if the source found no match)
    url: str = Field(min_length=1)  # the citable link
    retrieved_at: str = Field(min_length=1)  # ISO-8601, captured at fetch time
    terms: list[int] = Field(default_factory=list)  # the query, echoed for the record
    name: str | None = None  # short cited title/description snippet
    formula: str | None = None  # short cited formula snippet
    license_note: str = Field(min_length=1)  # the source's licence / usage note
    raw_response_hash: str = Field(min_length=1)  # sha256 of the exact retrieved bytes


def raw_response_hash(raw_response: str) -> str:
    """sha256 of the exact retrieved text — the fingerprint that proves *what* was retrieved."""
    return hashlib.sha256(raw_response.encode("utf-8")).hexdigest()


def build_pin_record(
    *,
    provider: str,
    url: str,
    retrieved_at: datetime,
    raw_response: str,
    license_note: str,
    identifier: str | None = None,
    terms: list[int] | None = None,
    name: str | None = None,
    formula: str | None = None,
) -> PinRecord:
    """Assemble a :class:`PinRecord` from a retrieval, hashing the raw response for the pin."""
    return PinRecord(
        provider=provider,
        identifier=identifier,
        url=url,
        retrieved_at=retrieved_at.isoformat(),
        terms=terms or [],
        name=name,
        formula=formula,
        license_note=license_note,
        raw_response_hash=raw_response_hash(raw_response),
    )
