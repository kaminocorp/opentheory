"""Migration 0017 structural checks (DB-free), mirroring ``test_migration_0016.py``."""

import importlib.util
import re
from pathlib import Path

from app.models.enums import OrchestrationRunStatus
from app.models.orchestration_run import OrchestrationRun

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0017_orchestration_runs.py"
_REVISION = "0017_orchestration_runs"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0017", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0016_research_git_merge_tag"


def test_it_is_revised_by_0018() -> None:
    """0018 (campaigns) revises 0017; 0017 must stay a single-parent link."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION in down_revisions


def test_the_table_the_model_declares_is_the_table_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert "orchestration_runs" in OrchestrationRun.__table__.name
    assert '"orchestration_runs"' in source
    for column in (
        "project_id",
        "triggered_by_actor_id",
        "role",
        "status",
        "decisions",
        "stop_reason",
        "passes_commissioned",
        "passes_completed",
        "passes_failed",
        "passes_skipped",
        "budget_available_start",
        "budget_available_end",
        "max_passes",
    ):
        assert column in OrchestrationRun.__table__.columns
        assert column in source


def test_status_labels_match_the_enum() -> None:
    mod = _load_migration()
    assert set(mod._STATUS_LABELS) == {member.name for member in OrchestrationRunStatus}
