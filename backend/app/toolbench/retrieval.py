"""The outbound HTTP + cache layer for retrieval instruments (Phase 5).

A retrieval instrument (``oeis.search``, ``crossref.lookup``, …) is one whose output is **not** a
pure function of its inputs: it fetches an external source and stamps a real-time ``retrieved_at``.
This module isolates that impurity behind a small :class:`RetrievalClient` so the instruments stay
declarative and the network I/O is trivially mockable.

Determinism contract (the plan's Phase 5 note): re-running does *not* return identical bytes — the
guarantee is that the recorded pin (``retrieved_at`` + ``raw_response_hash``, built in
``toolbench/pinning.py``) *reproduces what was retrieved*. The in-process cache reflects that: a
cache hit returns the earlier :class:`Retrieval` verbatim, including its original ``retrieved_at``.

No code execution, no new infra — it runs in the FastAPI process. Tests inject an
``httpx.MockTransport`` (or a fake fetcher) so CI never touches the live network.

A **404** is a successful empty match (the source said "nothing here"), not a fetch failure — the
instrument records ``undecided``. Network errors, timeouts, and other non-2xx statuses remain
:class:`RetrievalError` (mint nothing).
"""

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx

from app.core.config import settings


class RetrievalError(Exception):
    """The fetch did not succeed (network error, unexpected non-2xx, unparseable body).

    Raised out of :meth:`RetrievalClient.get_json` / :meth:`RetrievalClient.get_text`; a retrieval
    instrument lets it propagate, so the write path treats it as "the instrument did not run"
    (mint nothing, 4xx) — never a recorded result. A *successful* retrieval that simply found
    nothing — including an HTTP 404 — is a normal result, not this error.
    """


@dataclass(frozen=True)
class Retrieval:
    """One successful fetch: what was retrieved, from where, and when.

    ``raw_response`` is the exact response text — hashed (never redistributed wholesale) by the
    pinning primitive. ``parsed`` is the decoded JSON when the body was JSON, else ``None`` (Atom
    / XML instruments parse ``raw_response`` themselves). ``retrieved_at`` is captured at fetch
    time. ``status_code`` is the HTTP status; 404 is a successful empty match.
    """

    url: str
    retrieved_at: datetime
    raw_response: str
    parsed: Any
    status_code: int = 200


class Fetcher(Protocol):
    """The method a JSON retrieval instrument depends on — so tests inject a fake trivially."""

    async def get_json(self, url: str) -> Retrieval: ...


class TextFetcher(Protocol):
    """The method an XML/text retrieval instrument depends on (arXiv Atom)."""

    async def get_text(self, url: str) -> Retrieval: ...


def polite_user_agent() -> str:
    """User-Agent for outbound retrieval. Includes mailto when configured (Crossref polite pool)."""
    mailto = (settings.toolbench_retrieval_mailto or "").strip()
    base = "OpenTheory/0.18 (https://github.com/kaminocorp/opentheory)"
    return f"{base}; mailto:{mailto}" if mailto else base


class RetrievalClient:
    """An async fetcher with a small LRU-ish query cache (keyed by URL).

    ``transport`` is an injection seam: tests pass an ``httpx.MockTransport`` to exercise the real
    parse/hash/cache path with a canned response and no network. ``cache_size`` bounds the cache;
    the least-recently-used entry is evicted past the cap.

    ``headers`` are sent on every request (User-Agent, optional API key). ``params`` are extra
    query parameters applied at request time (e.g. OpenAlex ``api_key``) and are **not** written
    into :attr:`Retrieval.url` — the pin records the public URL, never a secret.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        cache_size: int = 128,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> None:
        self._timeout = timeout
        self._transport = transport
        self._cache: OrderedDict[str, Retrieval] = OrderedDict()
        self._cache_size = cache_size
        self._headers = dict(headers) if headers else {}
        self._params = dict(params) if params else {}

    async def get_json(self, url: str) -> Retrieval:
        """Fetch ``url``, decode JSON → :class:`Retrieval` (served from cache on a repeat query)."""
        return await self._get(url, accept="application/json", parse="json")

    async def get_text(self, url: str) -> Retrieval:
        """Fetch ``url`` as text (Atom/XML). ``parsed`` is ``None``; hash ``raw_response``."""
        return await self._get(url, accept="application/atom+xml, application/xml", parse="text")

    async def _get(
        self, url: str, *, accept: str, parse: Literal["json", "text"]
    ) -> Retrieval:
        cached = self._cache.get(url)
        if cached is not None:
            self._cache.move_to_end(url)  # LRU touch
            return cached

        headers = {"User-Agent": polite_user_agent(), "Accept": accept, **self._headers}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(url, headers=headers, params=self._params or None)
                # 404 is "the source said nothing is here" — a successful empty match, not a
                # failed fetch. Anything else non-2xx (5xx, 401, 429, …) is RetrievalError.
                if response.status_code != 404:
                    response.raise_for_status()
                raw = response.text
                parsed: Any = None
                if parse == "json" and raw:
                    try:
                        parsed = response.json()
                    except Exception:
                        # A 404 with a non-JSON body is still a successful empty match.
                        if response.status_code != 404:
                            raise
        except Exception as exc:  # noqa: BLE001 — any fetch/parse failure is one "could not retrieve"
            raise RetrievalError(f"could not retrieve {url}: {exc}") from exc

        retrieval = Retrieval(
            url=url,
            retrieved_at=datetime.now(UTC),
            raw_response=raw,
            parsed=parsed,
            status_code=response.status_code,
        )
        self._remember(url, retrieval)
        return retrieval

    def _remember(self, url: str, retrieval: Retrieval) -> None:
        self._cache[url] = retrieval
        self._cache.move_to_end(url)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)  # evict the least-recently-used
