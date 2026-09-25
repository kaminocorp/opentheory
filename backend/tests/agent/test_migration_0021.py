"""Migration 0021 structural checks (DB-free), mirroring ``test_migration_0020.py``."""

import importlib.util
import re
from pathlib import Path

from app.models.research_campaign import ResearchCampaign

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0021_concurrent_campaign_cycles.py"
_REVISION = "0021_concurrent_campaign_cycles"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0021", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0020_compute_debit_live_rates"


def test_it_is_the_only_head() -> None:
    """Nothing revises 0021 — a second head makes ``alembic upgrade head`` ambiguous on deploy."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION not in down_revisions


def test_the_column_the_model_declares_is_the_column_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert "concurrency" in ResearchCampaign.__table__.columns
    assert "concurrency" in source
    assert "research_campaigns" in source
    assert 'server_default="1"' in source
