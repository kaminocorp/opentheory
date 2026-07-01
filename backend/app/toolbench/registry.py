"""The instrument registry — a **code** registry, the single source of truth (plan Decision 3).

Instruments live in code and register themselves here; nothing persists them. A DB table would be a
second source of truth that drifts from the code that actually runs — exactly the
``core/openrouter_models.py`` → ``GET /agent-models/catalog`` pattern the catalog reuses.

The registry is a *class* with a module-level ``registry`` singleton (the production registry), so
tests can spin up throwaway :class:`InstrumentRegistry` instances without polluting it. In Phase 2
the production registry is deliberately **empty-but-valid**; Phase 4 registers the first real
instruments into it.
"""

from collections.abc import Iterator

from app.toolbench.adapter import Instrument


class InstrumentRegistry:
    """A name → :class:`Instrument` map that fail-fasts on a malformed or duplicate registration."""

    def __init__(self) -> None:
        self._items: dict[str, Instrument] = {}

    def register(self, instrument: Instrument) -> Instrument:
        """Register ``instrument`` (returns it, so it doubles as a decorator on a singleton).

        Rejects a missing/blank ``name``, an object that does not satisfy the :class:`Instrument`
        protocol, and a duplicate name — so a broken instrument can never enter the catalog.
        """
        name = getattr(instrument, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("instrument.name must be a non-empty string")
        if not isinstance(instrument, Instrument):
            raise TypeError(f"{name!r} does not satisfy the Instrument protocol")
        if name in self._items:
            raise ValueError(f"instrument {name!r} is already registered")
        self._items[name] = instrument
        return instrument

    def get(self, name: str) -> Instrument | None:
        return self._items.get(name)

    def all(self) -> list[Instrument]:
        """Every registered instrument, ordered by name (stable output for the catalog/tests)."""
        return [self._items[name] for name in sorted(self._items)]

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Instrument]:
        return iter(self.all())


# The production registry — empty in Phase 2; Phase 4 registers the first real instruments.
registry = InstrumentRegistry()
