"""Migration 0013 structural checks (DB-free).

A true up/down round-trip needs Postgres and is a documented manual gate (see the completion doc);
these DB-free checks catch the cheap regressions: a broken revision chain, or the migration's enum
labels drifting from the ``AgentRunStatus`` model. The migration file name starts with a digit, so
it is loaded by path rather than imported as a module.
"""

import importlib.util
from pathlib import Path

from app.models.enums import AgentRunStatus

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0013_agent_runs.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0013", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == "0013_agent_runs"
    assert mod.down_revision == "0012_toolbench_provenance"


def test_enum_labels_match_the_model() -> None:
    mod = _load_migration()
    # The DB uses StrEnum member names as labels (uppercase) — the migration lists exactly those.
    assert set(mod._AGENT_RUN_STATUS_LABELS) == {status.name for status in AgentRunStatus}
