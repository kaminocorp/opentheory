"""Production instruments — importing this package **registers** them.

``app.toolbench.__init__`` imports this module, so the production
:data:`app.toolbench.registry.registry` is populated the moment anything under ``app.toolbench``
is imported — exactly what the conformance auto-coverage test (parametrized over
``registry.all()`` at collection) and the catalog/run endpoints need. Registration runs once
(module import is cached); the registry itself rejects a duplicate or a non-conforming object,
so a broken instrument can never enter the catalog.
"""

from app.toolbench.instruments.arxiv_lookup import ARXIV_LOOKUP
from app.toolbench.instruments.calc_eval import CALC_EVAL
from app.toolbench.instruments.counterexample_search import COUNTEREXAMPLE_SEARCH
from app.toolbench.instruments.crossref_lookup import CROSSREF_LOOKUP
from app.toolbench.instruments.expr_compare import EXPR_COMPARE
from app.toolbench.instruments.geometry_measure import COORDINATE_MEASURE
from app.toolbench.instruments.lean_prove import LEAN_PROVE
from app.toolbench.instruments.oeis_search import OEIS_SEARCH
from app.toolbench.instruments.openalex_lookup import OPENALEX_LOOKUP
from app.toolbench.instruments.plot_function import PLOT_FUNCTION
from app.toolbench.instruments.plot_points import PLOT_POINTS
from app.toolbench.instruments.table_create import TABLE_CREATE
from app.toolbench.instruments.table_derive_column import TABLE_DERIVE_COLUMN
from app.toolbench.instruments.table_render import TABLE_RENDER
from app.toolbench.instruments.z3_prove import Z3_PROVE
from app.toolbench.instruments.z3_satisfy import Z3_SATISFY
from app.toolbench.registry import registry

# The production instrument set, in the order they are registered (registry sorts by name on read).
INSTRUMENTS = (
    ARXIV_LOOKUP,
    CALC_EVAL,
    COUNTEREXAMPLE_SEARCH,
    CROSSREF_LOOKUP,
    EXPR_COMPARE,
    COORDINATE_MEASURE,
    LEAN_PROVE,
    OEIS_SEARCH,
    OPENALEX_LOOKUP,
    PLOT_FUNCTION,
    PLOT_POINTS,
    TABLE_CREATE,
    TABLE_DERIVE_COLUMN,
    TABLE_RENDER,
    Z3_PROVE,
    Z3_SATISFY,
)

for _instrument in INSTRUMENTS:
    registry.register(_instrument)

__all__ = [
    "ARXIV_LOOKUP",
    "CALC_EVAL",
    "COUNTEREXAMPLE_SEARCH",
    "COORDINATE_MEASURE",
    "CROSSREF_LOOKUP",
    "EXPR_COMPARE",
    "LEAN_PROVE",
    "OEIS_SEARCH",
    "OPENALEX_LOOKUP",
    "PLOT_FUNCTION",
    "PLOT_POINTS",
    "TABLE_CREATE",
    "TABLE_DERIVE_COLUMN",
    "TABLE_RENDER",
    "Z3_PROVE",
    "Z3_SATISFY",
    "INSTRUMENTS",
]
