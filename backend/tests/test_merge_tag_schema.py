"""DB-free schema / OpenAPI gates for merge + tag (0.21.0)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.main import create_app
from app.models.append_only import _block_mutation
from app.models.tag import Tag
from app.schemas.merge import MergeCreate
from app.schemas.tag import TagCreate


def test_resolved_merge_requires_rationale() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        MergeCreate(source_branch_ids=[uuid4()], resolution="resolved")


def test_clean_merge_allows_empty_rationale() -> None:
    payload = MergeCreate(source_branch_ids=[uuid4()], resolution="clean")
    assert payload.rationale is None


def test_blank_tag_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TagCreate(checkpoint_id=uuid4(), name="   ", kind="milestone")


def test_tag_is_in_the_append_only_set() -> None:
    assert event.contains(Tag, "before_update", _block_mutation)
    assert event.contains(Tag, "before_delete", _block_mutation)


def _openapi_paths() -> dict:
    return create_app().openapi()["paths"]


def test_merge_and_tag_paths_exist() -> None:
    paths = _openapi_paths()
    assert "post" in paths["/api/v1/projects/{project_id}/merges"]
    assert "post" in paths["/api/v1/projects/{project_id}/tags"]
    assert "get" in paths["/api/v1/projects/{project_id}/tags"]
    assert "get" in paths["/api/v1/tags/{tag_id}"]


def test_tags_expose_no_mutation_methods() -> None:
    paths = _openapi_paths()
    for path in (
        "/api/v1/projects/{project_id}/tags",
        "/api/v1/tags/{tag_id}",
    ):
        methods = set(paths[path])
        assert methods <= {"get", "post"}, f"{path} exposes mutation methods: {methods}"


def test_merge_and_tag_writes_require_dev_actor_header() -> None:
    paths = _openapi_paths()
    for path in (
        "/api/v1/projects/{project_id}/merges",
        "/api/v1/projects/{project_id}/tags",
    ):
        params = paths[path]["post"].get("parameters", [])
        header_names = {p["name"].lower() for p in params if p["in"] == "header"}
        assert "x-dev-actor-id" in header_names, f"{path} POST missing dev actor header"
