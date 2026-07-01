"""Phase 5 — the retrieve+pin Tier-1 slice: pinning primitive, retrieval client, ``oeis.search``.

Pure in-process, **no live network**: the ``RetrievalClient`` is exercised through an
``httpx.MockTransport`` and ``oeis.search`` through a fake fetcher returning canned OEIS JSON. This
covers everything except the ledger write (DB-backed, in ``test_instruments_write_path.py``).

The load-bearing assertions: a match yields the A-number pinned with ``retrieved_at`` +
``raw_response_hash`` (``result``); a clean no-match is ``undecided`` (not a false claim); a failed
fetch raises ``RetrievalError`` (→ "did not run"); and the OEIS raw response is hashed, not stored.

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phase 5.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.instruments.oeis_search import OeisSearch
from app.toolbench.pinning import PinRecord, build_pin_record, raw_response_hash
from app.toolbench.retrieval import Retrieval, RetrievalClient, RetrievalError

# --- canned OEIS payloads (shape mirrors https://oeis.org/search?...&fmt=json) --------------------

_FIB_RAW = json.dumps(
    {
        "query": "1,1,2,3,5,8",
        "count": 1,
        "results": [
            {
                "number": 45,
                "name": "Fibonacci numbers: F(n) = F(n-1) + F(n-2).",
                "formula": ["F(n) = F(n-1) + F(n-2).", "a(n) = round(phi^n / sqrt(5))."],
                "data": "0,1,1,2,3,5,8,13,21",
            }
        ],
    }
)
_NO_MATCH_RAW = json.dumps({"query": "2,4,8,7,7,7", "count": 0, "results": None})


class _FakeFetcher:
    """A ``Fetcher`` returning a fixed raw response and a fixed ``retrieved_at`` (deterministic)."""

    def __init__(self, raw: str) -> None:
        self._raw = raw

    async def get_json(self, url: str) -> Retrieval:
        return Retrieval(
            url=url,
            retrieved_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
            raw_response=self._raw,
            parsed=json.loads(self._raw),
        )


def _mock_client(handler: Any) -> RetrievalClient:
    return RetrievalClient(transport=httpx.MockTransport(handler))


# --- the pinning primitive (source.pin pattern) --------------------------------------------------


def test_raw_response_hash_is_a_stable_sha256() -> None:
    h = raw_response_hash("abc")
    assert h == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert raw_response_hash("abc") == h
    assert raw_response_hash("abd") != h


def test_build_pin_record_captures_the_irreversible_facts() -> None:
    pin = build_pin_record(
        provider="oeis",
        url="https://oeis.org/A000045",
        retrieved_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        raw_response=_FIB_RAW,
        license_note="cite, don't redistribute",
        identifier="A000045",
        terms=[1, 1, 2, 3, 5, 8],
        name="Fibonacci numbers",
        formula="F(n) = F(n-1) + F(n-2).",
    )
    assert isinstance(pin, PinRecord)
    assert pin.identifier == "A000045"
    assert pin.retrieved_at == "2026-07-01T12:00:00+00:00"  # ISO-8601, captured
    assert pin.raw_response_hash == raw_response_hash(_FIB_RAW)  # fingerprint, not the bytes
    assert pin.terms == [1, 1, 2, 3, 5, 8]


# --- the retrieval client (real code path, mocked transport) --------------------------------------


async def test_retrieval_client_parses_and_hashes() -> None:
    client = _mock_client(
        lambda req: httpx.Response(200, text=_FIB_RAW, headers={"content-type": "application/json"})
    )
    retrieval = await client.get_json("https://oeis.org/search?q=1,1,2,3,5,8&fmt=json")
    assert retrieval.parsed["results"][0]["number"] == 45
    assert retrieval.raw_response == _FIB_RAW  # exact bytes available to hash


async def test_retrieval_client_caches_by_url() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=_FIB_RAW)

    client = _mock_client(handler)
    url = "https://oeis.org/search?q=1,1,2,3,5,8&fmt=json"
    first = await client.get_json(url)
    second = await client.get_json(url)
    assert first is second  # served from cache — the pin reproduces the *earlier* retrieval
    assert calls["n"] == 1  # only one network round-trip


async def test_retrieval_client_raises_on_non_2xx() -> None:
    client = _mock_client(lambda req: httpx.Response(503, text="unavailable"))
    with pytest.raises(RetrievalError):
        await client.get_json("https://oeis.org/search?q=x&fmt=json")


# --- oeis.search ----------------------------------------------------------------------------------


def test_oeis_search_conforms_structurally() -> None:
    # No example_inputs: an async retrieval instrument is structurally (not behaviourally) checked.
    assert check_conformance(OeisSearch(_FakeFetcher(_FIB_RAW))) == []


async def test_oeis_search_identifies_and_pins_fibonacci() -> None:
    result = await OeisSearch(_FakeFetcher(_FIB_RAW)).run(
        OeisSearch.InputModel(terms=[1, 1, 2, 3, 5, 8]), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "pinned_source"
    assert result.source_type == "oeis"  # marked as externally sourced, not "tool"
    OeisSearch.OutputModel.model_validate(result.output)  # output conforms

    pin = result.output["pin"]
    assert result.output["found"] is True
    assert pin["identifier"] == "A000045"  # the A-number is the pin
    assert pin["url"] == "https://oeis.org/A000045"  # cites the sequence page
    assert pin["raw_response_hash"] == raw_response_hash(_FIB_RAW)
    assert pin["retrieved_at"]  # captured
    assert "OEIS" in pin["license_note"] and "redistribut" in pin["license_note"]
    # the raw OEIS body is fingerprinted, never stored wholesale (cite, don't redistribute)
    assert _FIB_RAW not in json.dumps(result.output)


async def test_oeis_search_no_match_is_undecided() -> None:
    result = await OeisSearch(_FakeFetcher(_NO_MATCH_RAW)).run(
        OeisSearch.InputModel(terms=[2, 4, 8, 7, 7, 7]), {}
    )
    # A successful query that found nothing is undecided (escalate) — never a false negative claim.
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False
    assert result.output["pin"]["identifier"] is None
    assert result.output["pin"]["raw_response_hash"]  # still a citable retrieval record


async def test_oeis_search_propagates_a_fetch_failure() -> None:
    class _Boom:
        async def get_json(self, url: str) -> Retrieval:
            raise RetrievalError("network down")

    # A failed fetch means the instrument did not run — the write path turns this into a 4xx and
    # mints nothing; it must not be swallowed into a recorded result.
    with pytest.raises(RetrievalError):
        await OeisSearch(_Boom()).run(OeisSearch.InputModel(terms=[1, 2, 3]), {})


def test_oeis_search_requires_at_least_three_terms() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OeisSearch.InputModel.model_validate({"terms": [1, 1]})
