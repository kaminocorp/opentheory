"""Migration 0019 structural checks (DB-free), mirroring ``test_migration_0018.py``."""

import importlib.util
import re
from pathlib import Path

from app.models.agent_run import AgentRun
from app.models.orchestration_run import OrchestrationRun

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0019_concurrent_subpasses.py"
_REVISION = "0019_concurrent_subpasses"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0019", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0018_research_campaigns"


def test_it_is_revised_by_0020() -> None:
    """0020 (live OpenRouter rates) revises 0019; a second head is a deploy footgun."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION in down_revisions


def test_the_columns_the_models_declare_are_the_columns_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert "concurrency" in OrchestrationRun.__table__.columns
    assert "cancel_requested" in OrchestrationRun.__table__.columns
    assert "reserved_amount" in AgentRun.__table__.columns
    assert "concurrency" in source
    assert "cancel_requested" in source
    assert "reserved_amount" in source
    assert "orchestration_runs" in source
    assert "agent_runs" in source
