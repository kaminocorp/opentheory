"""Migration 0016 structural checks (DB-free), mirroring ``test_migration_0015.py``."""

import importlib.util
import re
from pathlib import Path

from app.models.enums import TagKind
from app.models.tag import Tag

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0016_research_git_merge_tag.py"
_REVISION = "0016_research_git_merge_tag"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0016", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == "0015_compute_debits"


def test_it_is_revised_by_0017() -> None:
    """0017 (orchestrator) revises 0016; 0016 must stay a single-parent link."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION in down_revisions


def test_the_table_the_model_declares_is_the_table_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert Tag.__table__.name == "tags"
    assert '"tags"' in source
    for column in ("project_id", "checkpoint_id", "author_id", "name", "kind", "notes"):
        assert column in Tag.__table__.columns
        assert column in source
    assert "uq_tags_project_name" in source


def test_kind_labels_match_the_enum() -> None:
    mod = _load_migration()
    assert set(mod._KIND_LABELS) == {member.name for member in TagKind}
