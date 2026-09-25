"""Migration 0018 structural checks (DB-free), mirroring ``test_migration_0017.py``."""

import importlib.util
import re
from pathlib import Path

from app.models.enums import ResearchCampaignStatus
from app.models.research_campaign import ResearchCampaign

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0018_research_campaigns.py"
_REVISION = "0018_research_campaigns"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0018", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0017_orchestration_runs"


def test_it_is_the_only_head() -> None:
    """Nothing revises 0018 — a second head makes ``alembic upgrade head`` ambiguous on deploy."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION not in down_revisions


def test_the_table_the_model_declares_is_the_table_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert "research_campaigns" in ResearchCampaign.__table__.name
    assert '"research_campaigns"' in source
    for column in (
        "project_id",
        "triggered_by_actor_id",
        "role",
        "status",
        "cycles",
        "stop_reason",
        "current_cycle",
        "cycles_completed",
        "consecutive_errors",
        "cancel_requested",
        "budget_available_start",
        "budget_available_end",
        "max_cycles",
        "error_budget",
    ):
        assert column in ResearchCampaign.__table__.columns
        assert column in source


def test_status_labels_match_the_enum() -> None:
    mod = _load_migration()
    assert set(mod._STATUS_LABELS) == {member.name for member in ResearchCampaignStatus}
