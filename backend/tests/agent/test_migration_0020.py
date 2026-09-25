"""Migration 0020 structural checks (DB-free), mirroring ``test_migration_0019.py``."""

import importlib.util
import re
from pathlib import Path

from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitRateSource

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0020_compute_debit_live_rates.py"
_REVISION = "0020_compute_debit_live_rates"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0020", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0019_concurrent_subpasses"


def test_it_is_revised_by_0021() -> None:
    """0021 (concurrent campaign cycles) revises 0020; a second head is a deploy footgun."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION in down_revisions


def test_the_columns_the_model_declares_are_the_columns_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    for column in (
        "prompt_tokens",
        "completion_tokens",
        "prompt_rate_per_1k",
        "completion_rate_per_1k",
        "rate_source",
    ):
        assert column in ComputeDebit.__table__.columns
        assert column in source
    assert "compute_debit_rate_source" in source
    assert "BLENDED_FALLBACK" in source
    assert "Numeric(12, 6)" in source


def test_rate_source_labels_match_the_enum() -> None:
    mod = _load_migration()
    assert set(mod._RATE_SOURCE_LABELS) == {
        member.name for member in ComputeDebitRateSource
    }
