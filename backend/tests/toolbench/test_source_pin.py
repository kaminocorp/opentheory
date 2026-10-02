"""0.45.0 — ``source.pin``: unified bibliographic pin on the existing literature seam.

Pure in-process, **no live network**. Delegates to the shipped Crossref / arXiv / OpenAlex
instruments through injected fake fetchers (same pattern as ``test_literature_pins.py``).
A match pins the provider's identifier; a successful empty match is ``undecided``; a
failed fetch raises ``RetrievalError`` (mint nothing). Never invents a citation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.instruments.arxiv_lookup import ArxivLookup
from app.toolbench.instruments.crossref_lookup import CrossrefLookup
from app.toolbench.instruments.openalex_lookup import OpenAlexLookup
from app.toolbench.instruments import SOURCE_PIN
from app.toolbench.instruments.source_pin import SourcePin, resolve_source_pin_route
from app.toolbench.pinning import raw_response_hash
from app.toolbench.registry import registry
from app.toolbench.retrieval import Retrieval, RetrievalError

_RETRIEVED = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

_CROSSREF_WORK_RAW = json.dumps(
    {
        "status": "ok",
        "message-type": "work",
        "message": {
            "DOI": "10.1038/nature14539",
            "title": ["Deep learning"],
            "author": [{"given": "Yann", "family": "LeCun"}],
            "issued": {"date-parts": [[2015, 5, 28]]},
            "container-title": ["Nature"],
        },
    }
)
_CROSSREF_SEARCH_RAW = json.dumps(
    {
        "status": "ok",
        "message-type": "work-list",
        "message": {
            "total-results": 3,
            "items": [json.loads(_CROSSREF_WORK_RAW)["message"]],
        },
    }
)
_CROSSREF_EMPTY_RAW = json.dumps(
    {"status": "ok", "message-type": "work-list", "message": {"total-results": 0, "items": []}}
)
_ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <published>2017-06-12T00:00:00Z</published>
    <author><name>Ashish Vaswani</name></author>
  </entry>
</feed>
"""
_ARXIV_EMPTY_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query: search_query=id_list=0000.00000</title>
</feed>
"""
_OPENALEX_WORK_RAW = json.dumps(
    {
        "id": "https://openalex.org/W2963682871",
        "doi": "https://doi.org/10.1038/nature14539",
        "display_name": "Deep learning",
        "publication_year": 2015,
        "authorships": [{"author": {"display_name": "Yann LeCun"}}],
    }
)


class _JsonFetcher:
    def __init__(self, raw: str, *, status_code: int = 200) -> None:
        self._raw = raw
        self._status = status_code
        self.urls: list[str] = []

    async def get_json(self, url: str) -> Retrieval:
        self.urls.append(url)
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
        self.urls: list[str] = []

    async def get_text(self, url: str) -> Retrieval:
        self.urls.append(url)
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


def _pin(
    *,
    crossref: _JsonFetcher | _BoomJson | None = None,
    arxiv: _TextFetcher | None = None,
    openalex: _JsonFetcher | None = None,
) -> SourcePin:
    return SourcePin(
        crossref=CrossrefLookup(crossref or _JsonFetcher(_CROSSREF_WORK_RAW)),
        arxiv=ArxivLookup(arxiv or _TextFetcher(_ARXIV_ATOM)),
        openalex=OpenAlexLookup(openalex or _JsonFetcher(_OPENALEX_WORK_RAW)),
    )


# --- routing -------------------------------------------------------------------------------------


def test_auto_routes_doi_arxiv_id_openalex_id_and_query() -> None:
    assert resolve_source_pin_route("https://doi.org/10.1038/nature14539", "auto") == (
        "crossref",
        {"doi": "10.1038/nature14539"},
    )
    assert resolve_source_pin_route("1706.03762v7", "auto") == (
        "arxiv",
        {"arxiv_id": "1706.03762v7"},
    )
    assert resolve_source_pin_route("https://openalex.org/W2963682871", "auto") == (
        "openalex",
        {"openalex_id": "W2963682871"},
    )
    assert resolve_source_pin_route("Deep learning LeCun 2015", "auto") == (
        "crossref",
        {"query": "Deep learning LeCun 2015"},
    )


def test_forced_providers() -> None:
    assert resolve_source_pin_route("10.1038/nature14539", "openalex") == (
        "openalex",
        {"doi": "10.1038/nature14539"},
    )
    assert resolve_source_pin_route("Deep learning", "openalex") == (
        "openalex",
        {"query": "Deep learning"},
    )
    assert resolve_source_pin_route("arxiv:1706.03762", "arxiv") == (
        "arxiv",
        {"arxiv_id": "1706.03762"},
    )
    with pytest.raises(ValueError, match="arXiv id"):
        resolve_source_pin_route("Deep learning LeCun 2015", "arxiv")


def test_input_rejects_arxiv_provider_without_an_id() -> None:
    with pytest.raises(ValidationError):
        SourcePin.InputModel.model_validate(
            {"locator": "Deep learning", "provider": "arxiv"}
        )
    with pytest.raises(ValidationError):
        SourcePin.InputModel.model_validate({"locator": "   "})


# --- instrument ----------------------------------------------------------------------------------


def test_source_pin_is_registered_and_conforms() -> None:
    assert registry.get("source.pin") is SOURCE_PIN
    assert check_conformance(_pin()) == []


async def test_auto_doi_pins_via_crossref() -> None:
    crossref = _JsonFetcher(_CROSSREF_WORK_RAW)
    result = await _pin(crossref=crossref).run(
        SourcePin.InputModel(locator="https://doi.org/10.1038/nature14539"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "pinned_source"
    assert result.source_type == "crossref"
    SourcePin.OutputModel.model_validate(result.output)
    assert result.output["found"] is True
    assert result.output["provider"] == "crossref"
    pin = result.output["pin"]
    assert pin["identifier"] == "10.1038/nature14539"
    assert pin["url"] == "https://doi.org/10.1038/nature14539"
    assert pin["source_url"].startswith("https://api.crossref.org/works/")
    assert pin["raw_response_hash"] == raw_response_hash(_CROSSREF_WORK_RAW)
    assert _CROSSREF_WORK_RAW not in json.dumps(result.output)
    assert crossref.urls and "api.crossref.org" in crossref.urls[0]


async def test_auto_arxiv_id_pins_via_arxiv() -> None:
    arxiv = _TextFetcher(_ARXIV_ATOM)
    result = await _pin(arxiv=arxiv).run(SourcePin.InputModel(locator="1706.03762v7"), {})
    assert result.status is ResultStatus.RESULT
    assert result.source_type == "arxiv"
    assert result.output["provider"] == "arxiv"
    assert result.output["pin"]["identifier"] == "1706.03762v7"
    assert result.output["pin"]["url"] == "https://arxiv.org/abs/1706.03762v7"
    assert arxiv.urls and "export.arxiv.org" in arxiv.urls[0]


async def test_auto_openalex_id_pins_via_openalex() -> None:
    openalex = _JsonFetcher(_OPENALEX_WORK_RAW)
    result = await _pin(openalex=openalex).run(
        SourcePin.InputModel(locator="W2963682871"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.source_type == "openalex"
    assert result.output["provider"] == "openalex"
    assert result.output["pin"]["identifier"] == "W2963682871"
    assert openalex.urls and "api.openalex.org" in openalex.urls[0]


async def test_bibliographic_query_goes_to_crossref() -> None:
    crossref = _JsonFetcher(_CROSSREF_SEARCH_RAW)
    result = await _pin(crossref=crossref).run(
        SourcePin.InputModel(locator="Deep learning LeCun 2015"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["provider"] == "crossref"
    assert result.output["match_count"] == 3
    assert result.output["pin"]["identifier"] == "10.1038/nature14539"
    assert "query.bibliographic" in crossref.urls[0]


async def test_forced_openalex_on_a_doi() -> None:
    openalex = _JsonFetcher(_OPENALEX_WORK_RAW)
    result = await _pin(openalex=openalex).run(
        SourcePin.InputModel(locator="10.1038/nature14539", provider="openalex"), {}
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["provider"] == "openalex"
    assert result.output["pin"]["identifier"] == "W2963682871"
    assert "api.openalex.org" in openalex.urls[0]


async def test_empty_match_is_undecided_never_a_fake_paper() -> None:
    result = await _pin(crossref=_JsonFetcher(_CROSSREF_EMPTY_RAW)).run(
        SourcePin.InputModel(locator="zzzz-no-such-paper-zzzz"), {}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False
    assert result.output["pin"]["identifier"] is None
    assert result.output["pin"]["raw_response_hash"]


async def test_arxiv_empty_feed_is_undecided() -> None:
    result = await _pin(arxiv=_TextFetcher(_ARXIV_EMPTY_ATOM)).run(
        SourcePin.InputModel(locator="0000.00000v1"), {}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["found"] is False
    assert result.output["provider"] == "arxiv"


async def test_fetch_failure_propagates_and_mints_nothing() -> None:
    with pytest.raises(RetrievalError):
        await _pin(crossref=_BoomJson()).run(
            SourcePin.InputModel(locator="10.1038/nature14539"), {}
        )
