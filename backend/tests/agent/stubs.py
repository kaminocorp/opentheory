"""Shared test doubles for the agent loop (0.12.1+).

``StubLlm`` implements the :class:`~app.agent.llm.LlmClient` protocol with a canned response (or a
raised exception), so the *real* planner runs with no network. The ``make_thread`` / ``make_claim``
builders construct unsaved ORM instances (no session needed) for the pure planner tests. Reused by
the Phase 3 orchestrator tests.
"""

from uuid import UUID, uuid4

from app.agent.llm import LlmResponse
from app.models.claim import Claim
from app.models.enums import ClaimKind, ClaimStatus, ThreadStage, ThreadStatus
from app.models.thread import Thread


class StubLlm:
    """A canned ``LlmClient``: ``content`` is the model's text, or an ``Exception`` to raise."""

    def __init__(self, content: str | Exception, *, tokens_used: int = 100) -> None:
        self._content = content
        self._tokens_used = tokens_used
        self.calls: list[dict] = []

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        response_format: dict | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        self.calls.append({"model": model, "messages": messages})
        if isinstance(self._content, Exception):
            raise self._content
        return LlmResponse(text=self._content, tokens_used=self._tokens_used, model=model)


def make_thread(
    *,
    question: str = "Is the corner exactly 5 across a right angle?",
    stage: ThreadStage = ThreadStage.EXECUTE,
) -> Thread:
    """An unsaved ``Thread`` for the pure planner (only its readable fields matter)."""
    return Thread(title="Corner", question=question, stage=stage, status=ThreadStatus.OPEN)


def make_claim(
    *,
    claim_id: UUID | None = None,
    statement: str = "d == a + b",
    kind: ClaimKind = ClaimKind.HYPOTHESIS,
    status: ClaimStatus = ClaimStatus.PROPOSED,
) -> Claim:
    """An unsaved ``Claim`` with an explicit id (the DB default only fires on flush)."""
    return Claim(id=claim_id or uuid4(), kind=kind, status=status, statement=statement)
