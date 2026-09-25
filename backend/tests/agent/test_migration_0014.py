"""Migration 0014 structural checks (DB-free), mirroring ``test_migration_0013.py``.

``0014`` is written but **unapplied anywhere** — it runs against the live database as a deploy
step — which makes the cheapest possible regression (a broken revision chain, so ``alembic upgrade
head`` stops at ``0013``) also the most expensive to discover. These checks are the DB-free half;
the real up/down round-trip stays a manual gate.

The migration file name starts with a digit, so it is loaded by path rather than imported.
"""

import importlib.util
import re
from pathlib import Path

from app.models.agent_run import AgentRun

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0014_agent_run_grounding_yield.py"
_REVISION = "0014_agent_run_grounding_yield"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0014", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0013_agent_runs"


def test_it_is_revised_by_0015() -> None:
    """0015 is the next head; 0014 must stay a single-parent link, not a second head."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION in down_revisions


def test_the_column_the_model_declares_is_the_column_the_migration_adds() -> None:
    """Model and migration must agree on the column, or every trace read fails after deploy."""
    source = _MIGRATION_PATH.read_text()
    assert "grounding_yield" in AgentRun.__table__.columns
    assert '"grounding_yield"' in source
    # NOT NULL + a '{}' server default is what lets existing rows read as *unmeasured* with no
    # backfill — see ``AgentRunSummary._empty_measure_is_no_measure``, which maps ``{}`` → ``None``
    # so an unmeasured pass can never be rendered as a measure of zero.
    assert "nullable=False" in source
    assert "'{}'" in source
