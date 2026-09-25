"""0.17.0 — Tier-1 literature pin instruments: Crossref, arXiv, OpenAlex.

Pure in-process, **no live network**: ``RetrievalClient`` is exercised through an
``httpx.MockTransport`` and the instruments through fake fetchers returning canned JSON / Atom.
This covers everything except the ledger write (DB-backed, in ``test_instruments_write_path.py``).

Honesty: a match pins DOI / versioned arXiv id / OpenAlex id with ``retrieved_at`` +
``raw_response_hash`` (``result``); a successful empty match is ``undecided`` (never a fake paper);
a failed fetch raises ``RetrievalError`` (mint nothing). The raw body is hashed, not stored.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.instruments._literature import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
)
from app.toolbench.instruments.arxiv_lookup import ArxivLookup
from app.toolbench.instruments.crossref_lookup import CrossrefLookup
from app.toolbench.instruments.openalex_lookup import OpenAlexLookup
from app.toolbench.pinning import raw_response_hash
from app.toolbench.retrieval import Retrieval, RetrievalClient, RetrievalError

_RETRIEVED = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)

_CROSSREF_WORK = {
    "status": "ok",
    "message-type": "work",
    "message": {
        "DOI": "10.1038/nature14539",
        "title": ["Deep learning"],
        "author": [
            {"given": "Yann", "family": "LeCun"},
            {"given": "Yoshua", "family": "Bengio"},
            {"given": "Geoffrey", "family": "Hinton"},
        ],
        "issued": {"date-parts": [[2015, 5, 28]]},
        "container-title": ["Nature"],
    },
}
_CROSSREF_WORK_RAW = json.dumps(_CROSSREF_WORK)
_CROSSREF_SEARCH_RAW = json.dumps(
    {
        "status": "ok",
        "message-type": "work-list",
        "message": {"total-results": 3, "items": [_CROSSREF_WORK["message"]]},
    }
)
_CROSSREF_EMPTY_SEARCH_RAW = json.dumps(
    {"status": "ok", "message-type": "work-list", "message": {"total-results": 0, "items": []}}
)
_CROSSREF_404_RAW = json.dumps({"status": "error", "message-type": "validation-failure"})

_ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <published>2017-06-12T00:00:00Z</published>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>
"""
_ARXIV_EMPTY_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query: search_query=id_list=0000.00000</title>
</feed>
"""

_OPENALEX_WORK = {
    "id": "https://openalex.org/W2963682871",
    "doi": "https://doi.org/10.1038/nature14539",
    "display_name": "Deep learning",
    "publication_year": 2015,
    "authorships": [
        {"author": {"display_name": "Yann LeCun"}},
        {"author": {"display_name": "Yoshua Bengio"}},
    ],
}
_OPENALEX_WORK_RAW = json.dumps(_OPENALEX_WORK)
_OPENALEX_SEARCH_RAW = json.dumps({"meta": {"count": 2}, "results": [_OPENALEX_WORK]})
_OPENALEX_EMPTY_RAW = json.dumps({"meta": {"count": 0}, "results": []})


class _JsonFetcher:
    def __init__(self, raw: str, *, status_code: int = 200) -> None:
        self._raw = raw
        self._status = status_code

    async def get_json(self, url: str) -> Retrieval:
        return Retrieval(
            url=url,
            retrieved_at=_RETRIEVED,
            raw_response=self._raw,
            parsed=json.loads(self._raw) if self._raw else None,
            status_code=self._status,
        )


class _TextFetcher:
    def __init__(self, raw: str, *, status_code: int = 200) -> None:
        self._raw = raw
        self._status = status_code

    async def get_text(self, url: str) -> Retrieval:
        return Retrieval(
            url=url,
            retrieved_at=_RETRIEVED,
            raw_response=self._raw,
            parsed=None,
            status_code=self._status,
        )


class _BoomJson:
    async def get_json(self, url: str) -> Retrieval:
        raise RetrievalError("network down")


class _BoomText:
    async def get_text(self, url: str) -> Retrieval:
        raise RetrievalError("network down")


def _mock_client(handler: Any) -> RetrievalClient:
    return RetrievalClient(transport=httpx.MockTransport(handler))


# --- identifier normalization --------------------------------------------------------------------


def test_normalize_doi_accepts_wrappers() -> None:
    assert normalize_doi("10.1038/nature14539") == "10.1038/nature14539"
    assert normalize_doi("https://doi.org/10.1038/nature14539") == "10.1038/nature14539"
    assert normalize_doi("doi:10.1038/nature14539") == "10.1038/nature14539"
    assert normalize_doi("not-a-doi") is None


def test_normalize_arxiv_id_prefers_versioned() -> None:
    assert normalize_arxiv_id("1706.03762v7") == "1706.03762v7"
    assert normalize_arxiv_id("arxiv:1706.03762") == "1706.03762"
    assert normalize_arxiv_id("https://arxiv.org/abs/hep-th/9901001v1") == "hep-th/9901001v1"
    assert normalize_arxiv_id("not an id") is None


def test_normalize_openalex_id() -> None:
    assert normalize_openalex_id("W2963682871") == "W2963682871"
    assert normalize_openalex_id("https://openalex.org/W2963682871") == "W2963682871"
    assert normalize_openalex_id("10.1038/nature14539") is None


# --- retrieval client: 404 is empty, not a failed fetch ------------------------------------------


async def test_retrieval_client_404_is_a_successful_empty_match() -> None:
    client = _mock_client(lambda req: httpx.Response(404, text=_CROSSREF_404_RAW))
    retrieval = await client.get_json("https://api.crossref.org/works/10.0/missing")
    assert retrieval.status_code == 404
    assert retrieval.parsed["status"] == "error"


async def test_retrieval_client_503_is_still_a_retrieval_error() -> None:
    client = _mock_client(lambda req: httpx.Response(503, text="unavailable"))
    with pytest.raises(RetrievalError):
        await client.get_json("https://api.crossref.org/works/10.0/x")


async def test_retrieval_client_get_text_returns_raw_atom() -> None:
    client = _mock_client(lambda req: httpx.Response(200, text=_ARXIV_ATOM))
    retrieval = await client.get_text("https://export.arxiv.org/api/query?id_list=1706.03762v7")
    assert retrieval.parsed is None
    assert "Attention Is All You Need" in retrieval.raw_response


async def test_retrieval_client_sends_user_agent_and_strips_secret_params_from_url() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"id": "https://openalex.org/W1", "display_name": "x"})

    client = RetrievalClient(
        transport=httpx.MockTransport(handler), params={"api_key": "secret-key"}
    )
    retrieval = await client.get_json("https://api.openalex.org/works/W1")
    assert retrieval.url == "https://api.openalex.org/works/W1"  # pin records the public URL
    assert "secret-key" not in retrieval.url
    assert "api_key=secret-key" in seen["url"]
    assert seen["ua"] and "OpenTheory" in seen["ua"]


# --- crossref.lookup -----------------------------------------------------------------------------


def test_crossref_lookup_conforms_structurally() -> None:
    assert check_conformance(CrossrefLookup(_JsonFetcher(_CROSSREF_WORK_RAW))) == []


async def test_crossref_lookup_pins_a_doi() -> None:
    result = await CrossrefLookup(_JsonFetcher(_CROSSREF_WORK_RAW)).run(
        CrossrefLookup.InputModel(doi="https://doi.org/10.1038/nature14539"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "pinned_source"
    assert result.source_type == "crossref"
    CrossrefLookup.OutputModel.model_validate(result.output)
    pin = result.output["pin"]
    assert result.output["found"] is True
    assert result.output["match_count"] == 1
    assert pin["identifier"] == "10.1038/nature14539"
    assert pin["url"] == "https://doi.org/10.1038/nature14539"
    assert pin["source_url"].startswith("https://api.crossref.org/works/")
    assert pin["raw_response_hash"] == raw_response_hash(_CROSSREF_WORK_RAW)
    assert "LeCun" in (pin["formula"] or "")
    assert "Nature" in (pin["formula"] or "")
    assert _CROSSREF_WORK_RAW not in json.dumps(result.output)


async def test_crossref_bibliographic_search_pins_the_top_hit_with_match_count() -> None:
    result = await CrossrefLookup(_JsonFetcher(_CROSSREF_SEARCH_RAW)).run(
        CrossrefLookup.InputModel(query="Deep learning LeCun 2015"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["found"] is True
    assert result.output["match_count"] == 3
    assert result.output["pin"]["identifier"] == "10.1038/nature14539"


async def test_crossref_unknown_doi_is_undecided() -> None:
    result = await CrossrefLookup(_JsonFetcher(_CROSSREF_404_RAW, status_code=404)).run(
        CrossrefLookup.InputModel(doi="10.0000/does-not-exist"), {}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False
    assert result.output["pin"]["identifier"] is None
    assert result.output["pin"]["raw_response_hash"]


async def test_crossref_empty_search_is_undecided() -> None:
    result = await CrossrefLookup(_JsonFetcher(_CROSSREF_EMPTY_SEARCH_RAW)).run(
        CrossrefLookup.InputModel(query="zzzz-no-such-paper-zzzz"), {}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False
    assert result.output["match_count"] == 0


async def test_crossref_propagates_a_fetch_failure() -> None:
    with pytest.raises(RetrievalError):
        await CrossrefLookup(_BoomJson()).run(
            CrossrefLookup.InputModel(doi="10.1038/nature14539"), {}
        )


def test_crossref_requires_doi_or_query() -> None:
    with pytest.raises(ValidationError):
        CrossrefLookup.InputModel.model_validate({})
    with pytest.raises(ValidationError):
        CrossrefLookup.InputModel.model_validate({"doi": "not-a-doi"})


# --- arxiv.lookup --------------------------------------------------------------------------------


def test_arxiv_lookup_conforms_structurally() -> None:
    assert check_conformance(ArxivLookup(_TextFetcher(_ARXIV_ATOM))) == []


async def test_arxiv_lookup_pins_the_version_the_api_returned() -> None:
    # Caller omitted vN; the Atom id carries v7 — that version is the pin.
    result = await ArxivLookup(_TextFetcher(_ARXIV_ATOM)).run(
        ArxivLookup.InputModel(arxiv_id="1706.03762"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.source_type == "arxiv"
    ArxivLookup.OutputModel.model_validate(result.output)
    pin = result.output["pin"]
    assert result.output["found"] is True
    assert pin["identifier"] == "1706.03762v7"
    assert pin["url"] == "https://arxiv.org/abs/1706.03762v7"
    assert pin["source_url"].startswith("https://export.arxiv.org/api/query")
    assert pin["raw_response_hash"] == raw_response_hash(_ARXIV_ATOM)
    assert "Vaswani" in (pin["formula"] or "")
    assert _ARXIV_ATOM not in json.dumps(result.output)


async def test_arxiv_empty_feed_is_undecided() -> None:
    result = await ArxivLookup(_TextFetcher(_ARXIV_EMPTY_ATOM)).run(
        ArxivLookup.InputModel(arxiv_id="0000.00000v1"), {}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False
    assert result.output["pin"]["identifier"] is None


async def test_arxiv_propagates_a_fetch_failure() -> None:
    with pytest.raises(RetrievalError):
        await ArxivLookup(_BoomText()).run(ArxivLookup.InputModel(arxiv_id="1706.03762v7"), {})


def test_arxiv_rejects_an_implausible_id() -> None:
    with pytest.raises(ValidationError):
        ArxivLookup.InputModel.model_validate({"arxiv_id": "not-an-arxiv-id"})


# --- openalex.lookup -----------------------------------------------------------------------------


def test_openalex_lookup_conforms_structurally() -> None:
    assert check_conformance(OpenAlexLookup(_JsonFetcher(_OPENALEX_WORK_RAW))) == []


async def test_openalex_lookup_pins_a_work_without_requiring_a_key() -> None:
    result = await OpenAlexLookup(_JsonFetcher(_OPENALEX_WORK_RAW)).run(
        OpenAlexLookup.InputModel(doi="10.1038/nature14539"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.source_type == "openalex"
    OpenAlexLookup.OutputModel.model_validate(result.output)
    pin = result.output["pin"]
    assert result.output["found"] is True
    assert pin["identifier"] == "W2963682871"
    assert pin["url"] == "https://doi.org/10.1038/nature14539"  # cite the DOI when we have one
    assert pin["source_url"].startswith("https://api.openalex.org/works/")
    assert "api_key" not in pin["source_url"]
    assert pin["raw_response_hash"] == raw_response_hash(_OPENALEX_WORK_RAW)
    assert _OPENALEX_WORK_RAW not in json.dumps(result.output)


async def test_openalex_search_empty_is_undecided() -> None:
    result = await OpenAlexLookup(_JsonFetcher(_OPENALEX_EMPTY_RAW)).run(
        OpenAlexLookup.InputModel(query="zzzz-no-such-work"), {}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False
    assert result.output["match_count"] == 0


async def test_openalex_search_pins_top_hit() -> None:
    result = await OpenAlexLookup(_JsonFetcher(_OPENALEX_SEARCH_RAW)).run(
        OpenAlexLookup.InputModel(query="Deep learning"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["match_count"] == 2
    assert result.output["pin"]["identifier"] == "W2963682871"


async def test_openalex_404_is_undecided() -> None:
    result = await OpenAlexLookup(_JsonFetcher("{}", status_code=404)).run(
        OpenAlexLookup.InputModel(openalex_id="W0"), {}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False


async def test_openalex_propagates_a_fetch_failure() -> None:
    with pytest.raises(RetrievalError):
        await OpenAlexLookup(_BoomJson()).run(
            OpenAlexLookup.InputModel(doi="10.1038/nature14539"), {}
        )


def test_openalex_requires_a_locator() -> None:
    with pytest.raises(ValidationError):
        OpenAlexLookup.InputModel.model_validate({})
