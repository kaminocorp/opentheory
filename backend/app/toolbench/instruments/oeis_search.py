"""``oeis.search`` — identify an integer sequence by its terms, pinned as citable evidence.

The first *retrieval* instrument: given terms like ``[1, 1, 2, 3, 5, 8]`` it queries the OEIS search
API and, on a match, reports the sequence's A-number (``A000045`` — Fibonacci) with a short cited
name/formula snippet. The result is wrapped in a :class:`~app.toolbench.pinning.PinRecord`, so the
ledger holds *solid* retrieval evidence: ``url`` + ``retrieved_at`` + ``raw_response_hash``, not a
flimsy quote. OEIS's licence is *cite, don't redistribute* — we store the pin, never a bulk copy.

Outcomes: a match → ``result`` (identified); a successful query with no match → ``undecided`` (OEIS
could not identify it — escalate, never a false "unknown sequence" claim). A *failed* fetch (network
/ non-2xx) is a :class:`~app.toolbench.retrieval.RetrievalError`: the instrument did not run, so the
write path mints nothing. Because it hits the network and stamps a real-time ``retrieved_at``,
``run`` is ``async`` and returns an awaitable (the write path awaits it).
"""

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.pinning import PinRecord, build_pin_record
from app.toolbench.retrieval import Fetcher, RetrievalClient

_PROVIDER = "oeis"
_SEARCH_ENDPOINT = "https://oeis.org/search"
_LICENSE_NOTE = (
    "OEIS data is licensed by The OEIS Foundation (CC BY-NC 3.0); cited by A-number, not "
    "redistributed. See https://oeis.org/wiki/The_OEIS_End-User_License_Agreement"
)


class OeisSearchInput(BaseModel):
    terms: list[int] = Field(
        min_length=3,
        description="The leading terms of an integer sequence, e.g. [1, 1, 2, 3, 5, 8]. "
        "At least three, to make the lookup meaningful.",
    )


class OeisSearchOutput(BaseModel):
    found: bool  # did OEIS identify a matching sequence?
    pin: PinRecord  # the citable retrieval record (present whether or not a match was found)


def _query_url(terms: list[int]) -> str:
    query = ",".join(str(t) for t in terms)
    return f"{_SEARCH_ENDPOINT}?q={query}&fmt=json"


def _top_match(parsed: Any) -> dict[str, Any] | None:
    """The first OEIS result, or ``None`` when nothing matched (``results: null`` / empty list)."""
    results = parsed.get("results") if isinstance(parsed, dict) else None
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0]
    return None


def _a_number(match: dict[str, Any]) -> str | None:
    number = match.get("number")
    return f"A{number:06d}" if isinstance(number, int) else None


def _first_formula(match: dict[str, Any]) -> str | None:
    formula = match.get("formula")
    if isinstance(formula, list) and formula and isinstance(formula[0], str):
        return formula[0]
    return formula if isinstance(formula, str) else None


class OeisSearch:
    """Identify an integer sequence via the OEIS search API, pinned (see module docstring)."""

    name = "oeis.search"
    namespace = "oeis"
    version = "0.1.0"
    engine = "oeis"
    # OEIS has no library version; reproducibility is anchored by the pin (retrieved_at +
    # raw_response_hash) in the output, not by this. It labels the API surface queried.
    engine_version = "search-api"
    description = (
        "Identify an integer sequence by its leading terms via the OEIS search API; returns the "
        "A-number pinned as a citable record (url, retrieved_at, raw_response_hash)."
    )
    InputModel = OeisSearchInput
    OutputModel = OeisSearchOutput

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        # Defaults to a shared HTTP client (with its own query cache); tests inject a fake fetcher.
        self._fetcher: Fetcher = fetcher or RetrievalClient()

    async def run(self, inputs: OeisSearchInput, assumptions: dict[str, Any]) -> InstrumentResult:
        retrieval = await self._fetcher.get_json(_query_url(inputs.terms))
        match = _top_match(retrieval.parsed)

        identifier = _a_number(match) if match is not None else None
        found = identifier is not None
        pin = build_pin_record(
            provider=_PROVIDER,
            # Cite the sequence page when identified, else the search that was run.
            url=f"https://oeis.org/{identifier}" if found else _query_url(inputs.terms),
            retrieved_at=retrieval.retrieved_at,
            raw_response=retrieval.raw_response,
            license_note=_LICENSE_NOTE,
            identifier=identifier,
            terms=inputs.terms,
            name=match.get("name") if match is not None else None,
            formula=_first_formula(match) if match is not None else None,
        )

        output = OeisSearchOutput(found=found, pin=pin)
        return InstrumentResult(
            output=output.model_dump(mode="json"),
            # Identified → a result; a clean "no match" is undecided (escalate), not a false claim.
            status=ResultStatus.RESULT if found else ResultStatus.UNDECIDED,
            artifact_kind="pinned_source",
            source_type=_PROVIDER,
        )


OEIS_SEARCH = OeisSearch()
