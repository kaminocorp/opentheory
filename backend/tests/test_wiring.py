"""DB-free checks that the 0.3.1/0.3.2 routes are wired and shaped correctly.

These run without a database and verify the OpenAPI surface: the new paths exist, the
write endpoints declare the X-Dev-Actor-Id header, and the append-only checkpoint
endpoints expose no update/delete methods.
"""

from app.main import create_app

WRITE_PATHS = [
    "/api/v1/projects/{project_id}/threads",
    "/api/v1/threads/{thread_id}/claims",
    "/api/v1/claims/{claim_id}/evidence",
    "/api/v1/projects/{project_id}/checkpoints",
]

# Checkpoints and their refs are append-only: no endpoint may mutate them.
APPEND_ONLY_PATHS = [
    "/api/v1/projects/{project_id}/checkpoints",
    "/api/v1/checkpoints/{checkpoint_id}",
]


def _openapi_paths() -> dict:
    return create_app().openapi()["paths"]


def test_new_paths_exist() -> None:
    paths = _openapi_paths()
    assert "post" in paths["/api/v1/actors"]
    assert "get" in paths["/api/v1/actors"]
    assert "get" in paths["/api/v1/projects/{project_id}/threads"]
    assert "get" in paths["/api/v1/threads/{thread_id}"]
    assert "get" in paths["/api/v1/claims/{claim_id}"]
    assert "get" in paths["/api/v1/projects/{project_id}/checkpoints"]
    assert "get" in paths["/api/v1/checkpoints/{checkpoint_id}"]
    assert "get" in paths["/api/v1/projects/{project_id}/overview"]
    for path in WRITE_PATHS:
        assert "post" in paths[path], f"missing POST for {path}"


def test_checkpoints_expose_no_mutation_methods() -> None:
    # Append-only at the API surface: GET/POST only, never PUT/PATCH/DELETE.
    paths = _openapi_paths()
    for path in APPEND_ONLY_PATHS:
        methods = set(paths[path])
        assert methods <= {"get", "post"}, f"{path} exposes mutation methods: {methods}"


def test_write_endpoints_require_dev_actor_header() -> None:
    paths = _openapi_paths()
    for path in WRITE_PATHS:
        params = paths[path]["post"].get("parameters", [])
        header_names = {p["name"].lower() for p in params if p["in"] == "header"}
        assert "x-dev-actor-id" in header_names, f"{path} POST missing dev actor header"


def test_actor_create_is_open() -> None:
    # Creating an actor must NOT require an acting actor (bootstrap path).
    paths = _openapi_paths()
    params = paths["/api/v1/actors"]["post"].get("parameters", [])
    header_names = {p["name"].lower() for p in params if p["in"] == "header"}
    assert "x-dev-actor-id" not in header_names
