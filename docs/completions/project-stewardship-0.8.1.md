# Project Stewardship — `0.8.1` Ownership + Self-Edit — Completion

> Implements Release `0.8.1` of `docs/executing/project-stewardship-and-collaboration.md`
> (proposal) via `docs/executing/project-stewardship-implementation-plan.md` (the `0.8.1` task
> block). Delivers asks **(A)** edit title, **(B)** edit question/description, and **(D)** a deep
> optional rich-text **background** — gated behind the platform's **first project-level
> authorization** (`project_members`). Asks **(C)** (invitations, `@username`, the bell inbox) are
> the later `0.8.2`/`0.8.3` slices and are **not** in this release.

**Status:** complete pending live verification. Backend `ruff` clean and the DB-free suite green
(**20 passed / 56 skipped**); frontend `typecheck` / `lint` / `build` all green (6/6 routes).
Model↔migration parity verified by compiling the model DDL against the Postgres dialect. **Not run
here:** the seven new DB-backed tests against a real Postgres, and the in-browser owner-edit pass —
both need the deployed Supabase (or an explicitly-greenlit throwaway DB), so they are the
post-deploy live check (consistent with the no-local-DB policy).

**Version:** ships as **`0.8.1`** (first slice of the `0.8.0` line), above `0.7.3`. The release
entry is in `docs/changelog.md`; this doc is the implementation-scoped detail.

---

## Scope of change

**New files**
- `backend/app/models/project_member.py` — the `ProjectMember` model.
- `backend/app/services/project_members.py` — membership/authorization service.
- `backend/alembic/versions/0007_project_stewardship.py` — additive migration.
- `backend/tests/test_project_members.py` — DB-backed stewardship tests.
- `frontend/src/components/workspace/markdown.tsx` — light read-path Markdown renderer.
- `frontend/src/components/workspace/rich-text-editor.tsx` — lazy TipTap → Markdown editor.
- `frontend/src/components/workspace/project-edit-form.tsx` — the metadata edit form.
- `frontend/src/components/workspace/collaborators-panel.tsx` — member list + owner controls.

**Modified**
- `backend/app/models/enums.py` (+`ProjectRole`), `models/project.py` (+`background`, `members`),
  `models/__init__.py` (export), `schemas/project.py` (+`background`, `ProjectUpdate`,
  `MemberRoleUpdate`, `ProjectMemberRead`), `services/projects.py` (+`create_project`),
  `services/contributions.py` (+`ACTION_CREATE_PROJECT`), `api/routes/projects.py` (create via
  service + `PATCH` + member routes), `tests/test_projects.py` (+DB-free `PATCH` 401 gate).
- `frontend/src/types/project.ts`, `types/research.ts`, `lib/api.ts`, `lib/query-keys.ts`,
  `components/workspace/project-workspace.tsx`, `package.json` (TipTap + markdown deps).

*(Not part of this work: the `0.7.3` backend co-location changes — `core/auth.py`, `main.py`,
`fly.toml`, `deploy.md` — landed in parallel during the same working tree.)*

---

## Design guardrail (load-bearing): admin ≠ a credit role

`docs/primitives.md` makes "funder finances / contributor produces / validator assesses — never
conflated" a rule about **intellectual credit and provenance**. **Project membership is none of
those — it is access control / governance.** So, by construction:

- Membership lives in its **own** table (`project_members`) — never on `Contribution` /
  `Validation` / `FundingAllocation`.
- Editing project metadata records **no** contribution. Only *creating* a project does
  (`create_project`) — that is intellectual origination, not governance.
- Keyed on the **`Account`** (the principal), like funding attribution and the future `username`/
  invitations — so an agent actor owned by an admin account later inherits the same edit capability
  through the *same* API, no parallel model.

---

## What landed, where, and why

### 1. `ProjectRole` enum + `ProjectMember` model

`ProjectRole` (`models/enums.py`): `OWNER` / `ADMIN`, mapped to the named PG enum `project_role`.
`ProjectMember` (`models/project_member.py`, table `project_members`) ties `account_id` → `accounts`
(`CASCADE`) and `project_id` → `projects` (`CASCADE`), carries `role` and a nullable
`invited_by_account_id` (`SET NULL`, provenance). Two constraints, **declared on the model and
mirrored in the migration** so `Base.metadata.create_all` (test harness) builds exactly what Alembic
installs:

- `UniqueConstraint(project_id, account_id, name="uq_project_member")` — one membership per
  principal per project.
- partial unique `Index("uq_project_one_owner", "project_id", unique=True,
  postgresql_where="role = 'OWNER'")` — at most one owner. The predicate uses the **uppercase**
  enum label (`'OWNER'`), this DB's StrEnum-member-name convention.

`ProjectMember` is a mutable governance row (a role change is an in-place edit) — like `Account` and
`Branch.status`, it is deliberately **not** registered in `models/append_only.py`.

### 2. `Project.background` + schemas

`projects.background` `Text` `NULL` (Markdown serialized to plaintext — see the proposal §4.7 for
why TEXT over JSONB: embeddable / FTS-able / diffable / editor-agnostic). Exposed on `ProjectBase`
(so it inherits to `ProjectRead`/`ProjectOverview` and is settable at create) with a 50k-char soft
cap. New schemas: `ProjectUpdate` (every field optional, applied with `exclude_unset`; **no `slug`**
— it is immutable), `MemberRoleUpdate` (`{ role }`), and `ProjectMemberRead` (privacy-safe:
`AccountSummary` + role + created_at, **never** email/roles).

### 3. `create_project` — ownership + contribution, atomically

Extracted from the route into `services/projects.py::create_project(db, payload, actor)`. In one
transaction: insert the project → `flush` to assign its pk → add the `OWNER` `ProjectMember`
(account = the creator's account, `invited_by` = self) → `record_contribution(action=
"create_project", target_type="project", target_id=project.id, actor=actor)` → single `commit`.
Mirrors the funding/checkpoint chokepoint discipline (the helper `add`s without committing), so the
project, its owner, and its creation record are atomic.

**Decision taken (a deliberate divergence from the plan's stated default — see below):**
account-less actors (dev `X-Dev-Actor-Id` / `system`) create an **ownerless** project with **no**
contribution, rather than being rejected with `400`.

### 4. Membership/authorization service

`services/project_members.py`:
- `ensure_can_manage(db, project_id, actor, *, require_owner=False) -> Project` — the project-level
  analog of `require_internal`. `404` missing project, `403` if the actor's account is not a member
  (or not `OWNER` when `require_owner`), `403` for account-less actors. Returns the loaded project so
  the `PATCH` handler mutates without a second fetch.
- `list_members` — public, owner-first, `AccountSummary` only (one join, no N+1).
- `remove_member` — owner-only; refuses to remove the sole `OWNER` (`400`).
- `set_member_role` — owner-only; transferring `OWNER` demotes the prior owner to `ADMIN` in the
  same txn, and **`flush`es the demotion before promoting the target** — `uq_project_one_owner` is a
  plain (non-deferred) unique index, so Postgres checks it per statement; emitting the promotion
  first would briefly see two owners and raise.

### 5. Routes

`api/routes/projects.py`: `POST` now delegates to the service; `PATCH /projects/{id}` (owner/admin,
partial update, plain in-place mutation — **not** a ledger event, no checkpoint); public
`GET /projects/{id}/members`; owner-only `DELETE`/`PATCH /projects/{id}/members/{account_id}`.

### 6. Frontend

- **`markdown.tsx`** (read path) — `react-markdown` + `remark-gfm`, raw HTML **disabled** (safe by
  default), styled to the console tokens by hand (no typography plugin). Light, so public viewers
  pay nothing for the editor.
- **`rich-text-editor.tsx`** (edit path) — TipTap (`StarterKit` + `tiptap-markdown`),
  `immediatelyRender: false` for Next SSR, seeds from a Markdown string and emits Markdown via
  `getMarkdown()`. Lazy-loaded (`next/dynamic`, `ssr:false`) only when the edit form opens.
- **`project-edit-form.tsx`** — title / question / description / status + the background editor;
  invalidates `project` + `overview` on save. The status select offers only the four **backend**
  statuses (`draft`/`active`/`paused`/`archived`) — the frontend type also carries `"completed"`,
  which the backend enum lacks, so offering it would `422` (the plan's appendix nit, sidestepped).
- **`collaborators-panel.tsx`** — member list + role pills; owner-only role select (incl. "owner
  (transfer)") and remove. Shows `display_name` (becomes `@handle` in `0.8.2`).
- **`project-workspace.tsx`** — derives `canManageProject` from the member list (the backend still
  authorizes every write — the client check only decides whether to *show* affordances, the same
  pattern as `canWrite`), mounts the Edit toggle (owner/admin), the collapsible Background section,
  and the Collaborators panel.
- **`lib/api.ts`** — `updateProject` / `listProjectMembers` / `removeProjectMember` /
  `updateProjectMember`, a `patchInit` helper, and a `204`-tolerant `request` (DELETE has no body).

---

## The one decision I changed from the plan (and why)

The plan's **T1.4** floated two options for an account-less creator and stated a default:
> *"require `account_id` and `400` otherwise. … for dev-path tests we build an account."*

I implemented the **other** option — **account-less → ownerless project, no contribution** — for
two concrete reasons surfaced by the code:

1. **The `400` path would break ~6 DB-backed test files I can't run.** Almost every existing test
   creates projects with an **account-less** dev actor (`POST /actors {type:human}` with no
   `account_id`). Worse, the `uq_actors_one_human_per_account` partial index means one account owns
   at most **one** human actor, so helpers that build *two* humans ("Ada" + "Author") would each
   need their own account — a fragile rewrite across files that skip without a DB. The `400` choice
   also breaks `test_funding`'s `{"fund"}`-only contribution assertion (a `create_project`
   contribution would appear).
2. **It is production-equivalent.** Every real authenticated principal is provisioned *with* an
   account (`api/deps.py::_resolve_or_provision`), so real users always get owner + contribution.
   Account-less actors exist *only* on the dev `X-Dev-Actor-Id` path. So "account-less → ownerless"
   is dev-only behaviour that mirrors the already-accepted "legacy projects are ownerless until you
   add the owner row by hand in Supabase" situation.

Net effect: identical production behaviour to the plan's intent, zero churn to the existing suite,
and the new owner/contribution path is tested with account-backed actors. Documented in the
`create_project` docstring.

---

## Tests

- **DB-free** (`tests/test_projects.py`): `PATCH /projects/{id}` unauthenticated → `401` (rejected
  by `ActingActor` before any DB access, via `dbfree_client`).
- **DB-backed** (`tests/test_project_members.py`, skip without `TEST_DATABASE_URL`): create records
  owner + `create_project` contribution; account-less creator → ownerless, no contribution;
  `PATCH` authz matrix (owner ✓ / admin ✓ / non-member `403` / missing `404`); `background`
  round-trip + nullable + partial-update; member list omits PII; single-owner index rejects a second
  owner; owner-only remove + sole-owner protection + ownership transfer (demotion preserved).
  Acting users are built via the `internal_funder` fixture (`roles=()` → a plain account-backed
  user); admin memberships are inserted directly (the invite flow lands in `0.8.3`).

## Verification commands

```bash
cd backend && uv run ruff check . && uv run pytest          # 20 passed / 56 skipped (no DB)
cd frontend && npm run typecheck && npm run lint && npm run build   # all green, 6/6 routes
```

## Follow-ups (not this slice)

- **`0.8.2`** — `accounts.username` (auto-generated unique `@handle`, `PATCH /me`, exposed on
  `/me` + `AccountSummary`), `resolve_account_by_identifier`.
- **`0.8.3`** — `ProjectInvitation` + invite-by-handle/email, accept/decline, the bell inbox; the
  collaborators panel grows an invite form.
- **Live (manual):** add the owner `project_members` row to pre-existing projects in Supabase; run
  the DB-backed suite against a throwaway Postgres if a dedicated verification pass is wanted.
