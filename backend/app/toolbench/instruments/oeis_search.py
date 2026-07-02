"""``oeis.search`` — identify an integer sequence by its terms, pinned as citable evidence.

The first *retrieval* instrument: given terms like ``[1, 1, 2, 3, 5, 8]`` it queries the OEIS search
API and, on a genuine identification, reports the sequence's A-number (``A000045`` — Fibonacci) with
a short cited name/formula snippet. The result is wrapped in a
:class:`~app.toolbench.pinning.PinRecord`, so the ledger holds *solid* retrieval evidence: ``url`` +
``source_url`` + ``retrieved_at`` + ``raw_response_hash``, not a flimsy quote. OEIS's licence is
*cite, don't redistribute* — we store the pin, never a bulk copy.

Outcomes (the honesty rule): OEIS search returns *relevance-ranked* sequences that merely
**contain** the query terms, not only sequences *identified by* them — so the raw top hit is a
candidate, not a proof. We report ``result`` (identified) **only** when the queried terms occur as a
contiguous run in the top hit's own terms (``data``) — an actual identification of a sequence with
those consecutive terms; ``match_count`` (how many sequences OEIS matched) rides along so the ledger
is honest about ambiguity. A top hit that does *not* contain the run (OEIS's fuzzy/relevance
fallback) and a successful query with no match are both ``undecided`` — escalate, never a confident
(possibly-wrong) A-number. A *failed* fetch (network / non-2xx) is a
:class:`~app.toolbench.retrieval.RetrievalError`: the instrument did not run, so the write path
mints nothing. Because it hits the network and stamps a real-time ``retrieved_at``, ``run`` is
``async`` and returns an awaitable (the write path awaits it).
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
        max_length=64,
        description="The leading terms of an integer sequence, e.g. [1, 1, 2, 3, 5, 8]. "
        "At least three, to make the lookup meaningful (at most 64).",
    )


class OeisSearchOutput(BaseModel):
    found: bool  # did OEIS *identify* a sequence (the queried terms occur in the top hit)?
    match_count: int = 0  # how many sequences OEIS matched — the ambiguity signal (0 when none)
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


def _match_count(parsed: Any, match: dict[str, Any] | None) -> int:
    """How many sequences OEIS reported matching (its ``count``), for the ambiguity signal."""
    count = parsed.get("count") if isinstance(parsed, dict) else None
    if isinstance(count, int) and count >= 0:
        return count
    results = parsed.get("results") if isinstance(parsed, dict) else None
    return len(results) if isinstance(results, list) else (1 if match is not None else 0)


def _terms_are_run_of(terms: list[int], match: dict[str, Any]) -> bool:
    """Whether ``terms`` occur as a *contiguous run* in the matched sequence's own terms (``data``).

    OEIS ``data`` is the sequence's actual leading terms as a comma-separated string. A genuine
    identification means our query is a consecutive slice of that sequence (it may start after a
    leading offset term — e.g. Fibonacci's ``data`` opens with a ``0`` before ``1,1,2,3,5,8``). A
    hit whose ``data`` does not contain the run is a fuzzy/relevance candidate, not an
    identification; absent or unparseable ``data`` is treated as unconfirmed (never assumed).
    """
    data = match.get("data")
    if not isinstance(data, str) or not terms:
        return False
    try:
        seq = [int(tok) for tok in data.split(",") if tok.strip()]
    except ValueError:
        return False
    n = len(terms)
    return n <= len(seq) and any(seq[i : i + n] == terms for i in range(len(seq) - n + 1))


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
        # A genuine identification (not just OEIS's top relevance hit): the match exists, carries an
        # A-number, and actually contains the queried terms as consecutive terms. Anything else —
        # a fuzzy hit lacking the run, or no hit — is undecided, never a confident claim.
        identified = (
            match is not None
            and identifier is not None
            and _terms_are_run_of(inputs.terms, match)
        )
        pin = build_pin_record(
            provider=_PROVIDER,
            # Cite the sequence page when identified, else the search that was run...
            url=f"https://oeis.org/{identifier}" if identified else _query_url(inputs.terms),
            # ...but always record the search URL as the source whose response we hashed, so the pin
            # is reproducible: a verifier fetches source_url (not the citation url) to recheck it.
            source_url=retrieval.url,
            retrieved_at=retrieval.retrieved_at,
            raw_response=retrieval.raw_response,
            license_note=_LICENSE_NOTE,
            # Only stamp the A-number / cited snippets on a confirmed identification — an
            # unconfirmed candidate leaves identifier None (like the no-match branch).
            identifier=identifier if identified else None,
            terms=inputs.terms,
            name=match.get("name") if identified else None,
            formula=_first_formula(match) if identified else None,
        )

        output = OeisSearchOutput(
            found=identified, match_count=_match_count(retrieval.parsed, match), pin=pin
        )
        return InstrumentResult(
            output=output.model_dump(mode="json"),
            # Identified → a result; a fuzzy candidate or clean no-match is undecided (escalate).
            status=ResultStatus.RESULT if identified else ResultStatus.UNDECIDED,
            artifact_kind="pinned_source",
            source_type=_PROVIDER,
        )


OEIS_SEARCH = OeisSearch()
