"""The outbound HTTP + cache layer for retrieval instruments (Phase 5).

A retrieval instrument (``oeis.search``) is the first whose output is **not** a pure function of its
inputs: it fetches an external source and stamps a real-time ``retrieved_at``. This module isolates
that impurity behind a small :class:`RetrievalClient` so the instruments stay declarative and the
network I/O is trivially mockable.

Determinism contract (the plan's Phase 5 note): re-running does *not* return identical bytes — the
guarantee is that the recorded pin (``retrieved_at`` + ``raw_response_hash``, built in
``toolbench/pinning.py``) *reproduces what was retrieved*. The in-process cache reflects that: a
cache hit returns the earlier :class:`Retrieval` verbatim, including its original ``retrieved_at``.

No code execution, no new infra — it runs in the FastAPI process. Tests inject an
``httpx.MockTransport`` (or a fake fetcher) so CI never touches the live network.
"""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx


class RetrievalError(Exception):
    """The fetch did not succeed (network error, non-2xx, unparseable body).

    Raised out of :meth:`RetrievalClient.get_json`; a retrieval instrument lets it propagate, so the
    write path treats it as "the instrument did not run" (mint nothing, 4xx) — never a recorded
    result. A *successful* retrieval that simply found nothing is a normal result, not this error.
    """


@dataclass(frozen=True)
class Retrieval:
    """One successful fetch: what was retrieved, from where, and when.

    ``raw_response`` is the exact response text — hashed (never redistributed wholesale) by the
    pinning primitive. ``parsed`` is the decoded JSON. ``retrieved_at`` is captured at fetch time.
    """

    url: str
    retrieved_at: datetime
    raw_response: str
    parsed: Any


class Fetcher(Protocol):
    """The single method a retrieval instrument depends on — so tests inject a fake trivially."""

    async def get_json(self, url: str) -> Retrieval: ...


class RetrievalClient:
    """An async JSON fetcher with a small LRU-ish query cache (keyed by URL).

    ``transport`` is an injection seam: tests pass an ``httpx.MockTransport`` to exercise the real
    parse/hash/cache path with a canned response and no network. ``cache_size`` bounds the cache;
    the least-recently-used entry is evicted past the cap.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        cache_size: int = 128,
    ) -> None:
        self._timeout = timeout
        self._transport = transport
        self._cache: OrderedDict[str, Retrieval] = OrderedDict()
        self._cache_size = cache_size

    async def get_json(self, url: str) -> Retrieval:
        """Fetch ``url``, decode JSON → :class:`Retrieval` (served from cache on a repeat query)."""
        cached = self._cache.get(url)
        if cached is not None:
            self._cache.move_to_end(url)  # LRU touch
            return cached

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                raw = response.text
                parsed = response.json()
        except Exception as exc:  # noqa: BLE001 — any fetch/parse failure is one "could not retrieve"
            raise RetrievalError(f"could not retrieve {url}: {exc}") from exc

        retrieval = Retrieval(
            url=url, retrieved_at=datetime.now(UTC), raw_response=raw, parsed=parsed
        )
        self._remember(url, retrieval)
        return retrieval

    def _remember(self, url: str, retrieval: Retrieval) -> None:
        self._cache[url] = retrieval
        self._cache.move_to_end(url)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)  # evict the least-recently-used
