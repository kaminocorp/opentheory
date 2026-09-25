"""Migration 0015 structural checks (DB-free), mirroring ``test_migration_0014.py``."""

import importlib.util
import re
from pathlib import Path

from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitKind

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0015_compute_debits.py"
_REVISION = "0015_compute_debits"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0015", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0014_agent_run_grounding_yield"


def test_it_is_the_only_head() -> None:
    """Nothing revises 0015 — a second head makes ``alembic upgrade head`` ambiguous on deploy."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION not in down_revisions


def test_the_table_the_model_declares_is_the_table_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert "compute_debits" in ComputeDebit.__table__.name
    assert '"compute_debits"' in source
    for column in (
        "project_id",
        "agent_run_id",
        "tokens_used",
        "amount",
        "currency",
        "model",
        "rate_per_1k",
        "kind",
    ):
        assert column in ComputeDebit.__table__.columns
        assert column in source
    assert "uq_compute_debits_one_per_agent_run" in source
    assert "Numeric(12, 6)" in source


def test_kind_labels_match_the_enum() -> None:
    mod = _load_migration()
    assert set(mod._KIND_LABELS) == {member.name for member in ComputeDebitKind}
