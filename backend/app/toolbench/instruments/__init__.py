"""The Tier-0 in-process instruments (Phase 4) — SymPy-backed, pure-Python, no I/O.

Importing this package **registers** the three instruments into the production
:data:`app.toolbench.registry.registry`. ``app.toolbench.__init__`` imports it, so the production
registry is populated the moment anything under ``app.toolbench`` is imported — exactly what the
conformance auto-coverage test (parametrized over ``registry.all()`` at collection) and Phase 6's
catalog/run endpoints need. Registration runs once (module import is cached); the registry itself
rejects a duplicate or a non-conforming object, so a broken instrument can never enter the catalog.
"""

from app.toolbench.instruments.calc_eval import CALC_EVAL
from app.toolbench.instruments.expr_compare import EXPR_COMPARE
from app.toolbench.instruments.geometry_measure import COORDINATE_MEASURE
from app.toolbench.instruments.oeis_search import OEIS_SEARCH
from app.toolbench.registry import registry

# The production instrument set, in the order they are registered (registry sorts by name on read).
INSTRUMENTS = (CALC_EVAL, EXPR_COMPARE, COORDINATE_MEASURE, OEIS_SEARCH)

for _instrument in INSTRUMENTS:
    registry.register(_instrument)

__all__ = ["CALC_EVAL", "COORDINATE_MEASURE", "EXPR_COMPARE", "OEIS_SEARCH", "INSTRUMENTS"]
