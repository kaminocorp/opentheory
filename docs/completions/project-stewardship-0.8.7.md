# Project Stewardship — `0.8.7` Collaborators + Invitation Inbox — Completion

> Implements the **collaborators + invitation inbox** release of
> `docs/executing/project-stewardship-and-collaboration.md` (ask **(C)**) via the `0.8.3` task block
> of `docs/executing/project-stewardship-implementation-plan.md` (tasks **T3.1–T3.10**). An
> owner/admin invites an **existing** account by `@username` or email; the invitee accepts (becoming
> an `admin` member) or declines from a top-right bell inbox. This is the **final** slice of the
> three-release stewardship line (ownership → `@username` → collaboration).

**Status:** complete pending live verification. Backend `ruff` clean and the DB-free suite green
(**55 passed / 65 → 75 skipped**); frontend `typecheck` / `lint` / `build` all green (7 routes).
Model↔migration parity verified by compiling the `project_invitations` DDL against the Postgres
dialect, and `alembic heads` confirms a single linear head. **Not run here:** the 10 new DB-backed
tests against a real Postgres, and the in-browser invite/accept pass — both need the deployed
Supabase (or an explicitly-greenlit throwaway DB), so they are the post-deploy live check
(consistent with the no-local-DB policy).

**Version + migration — two deliberate renumbers.** The plan calls this `0.8.3`, but the repo's
`0.8.2`/`0.8.4` (hardening), `0.8.5` (jingle), and `0.8.6` (hardening) took those slots, so the
feature lands as **`0.8.7`** (same renumber pattern as `@username`: plan-`0.8.2` → repo-`0.8.3`).
Likewise the plan's *migration* `0009` was already consumed by `0.8.4`'s
`0009_account_email_index`, so the invitations migration is **`0010_project_invitations`**, chained
onto it. Both confirmed with @phil. The release entry is in `docs/changelog.md`; this doc is the
implementation-scoped detail.

---

## Scope of change

**New files**
- `backend/app/models/project_invitation.py` — the `ProjectInvitation` model.
- `backend/app/schemas/invitation.py` — `InvitationCreate` + `InvitationRead`.
- `backend/app/services/invitations.py` — the invite/accept/decline/revoke/list service.
- `backend/app/api/routes/invitations.py` — the six routes (root-mounted, full paths).
- `backend/alembic/versions/0010_project_invitations.py` — additive migration.
- `backend/tests/test_invitations.py` — 3 DB-free auth-gates + 10 DB-backed flow tests.
- `frontend/src/components/shell/invitation-inbox.tsx` — the bell + dropdown inbox.

**Modified**
- `backend/app/models/enums.py` (+`InvitationStatus`), `models/project.py` (+`invitations`
  relationship), `models/__init__.py` (export), `api/router.py` (register the router).
- `frontend/src/types/research.ts` (+invitation types), `lib/api.ts` (+six client fns),
  `lib/query-keys.ts` (+`myInvitations`/`projectInvitations`),
  `components/shell/app-shell.tsx` (mount the bell), `components/workspace/collaborators-panel.tsx`
  (invite form + pending list + revoke).

---

## Design guardrail (load-bearing): an invitation is governance, not credit

Carried straight from the line: an invitation, like the `ProjectMember` it produces, is **access
control** — never intellectual credit. By construction:

- It lives in its **own** table (`project_invitations`) — never on `Contribution` / `Validation` /
  `FundingAllocation`.
- **Accepting an invite records no `Contribution`.** Only *creating* a project does (`0.8.1`). The
  accept flow *composes* with `ProjectMember` and mints nothing on the credit ledger. (A DB-backed
  test asserts the project's only contribution after an accept is the original `create_project`.)
- Keyed on the **`Account`** (the principal, `0.7.0`), the same grain as ownership/membership/funding
  attribution — so a future agent actor owned by an admin account inherits the same edit capability
  through the same API, no parallel model.

---

## What landed, where, and why

### 1. `InvitationStatus` enum + `ProjectInvitation` model (T3.1)

`InvitationStatus` (`PENDING`/`ACCEPTED`/`DECLINED`/`REVOKED`), mapped to the named PG enum
`invitation_status`. `ProjectInvitation` ties `invitee_account_id` → `accounts` (`CASCADE`) and
`project_id` → `projects` (`CASCADE`), with `role` (reuses the `project_role` enum, default `ADMIN`),
`status` (default `PENDING`), and a nullable `invited_by_account_id` (`SET NULL`, provenance — like
`ProjectMember.invited_by_account_id`).

The load-bearing constraint is **`UniqueConstraint(project_id, invitee_account_id)`**
(`uq_project_invitation`): one invitation row per (project, invitee). This is what makes "re-invite
after decline" an *upsert* (reset the existing row to `PENDING`) rather than a second row — declared
on the model **and** mirrored in the migration so `Base.metadata.create_all` (tests) builds exactly
what Alembic installs. Like `ProjectMember`, it is a mutable governance row, deliberately **not**
registered in `models/append_only.py`.

### 2. Schemas (T3.2)

`InvitationCreate { identifier: str; role: ProjectRole = ADMIN }` — `identifier` is the free-text
`@username`-or-email. `InvitationRead` carries the **project title** (so the inbox renders without a
second fetch) and **privacy-safe `AccountSummary`** for both the invitee and inviter (id +
display_name + public `@username`, never email/roles) — safe to serve to an invitee who is not a
member yet. It is composed explicitly in the service (title + summaries are a join, not one ORM
attribute).

### 3. Service — the two authorization grains (T3.3)

`services/invitations.py` is split by *who* is authorized:

- **Project-side** (`invite` / `list_for_project` / `revoke`) composes with the route's
  `ensure_can_manage` (owner/admin; admins may invite further admins — Decision), inheriting its
  `FOR UPDATE` project lock. `invite` resolves via `resolve_account_by_identifier` (`404` if
  unknown) and rejects self / already-member / already-pending with `409`; re-inviting a
  declined/revoked user resets the same row to `PENDING`.
- **Invitee-side** (`my_pending` / `accept` / `decline`) is keyed on the invitation's
  `invitee_account_id` — a caller may act only on an invitation addressed to **their own** account
  (`403` otherwise). There is no membership check, because accepting is *how* a non-member becomes a
  member: `accept` inserts the `ProjectMember` (guarded against a duplicate by `uq_project_member`)
  and flips `status` to `ACCEPTED` in one transaction. `accept`/`decline` are idempotent on their
  terminal state and `409` on a non-pending row; `my_pending` returns `[]` for an account-less actor.

Reads use `selectinload` (constant follow-up queries, not N+1) and, with the app's
`expire_on_commit=False`, the loaded relationships survive the later `commit` so the read model is
built without a post-commit lazy-load (which would raise under async).

### 4. Routes (T3.4)

`api/routes/invitations.py`, root-mounted with full paths (like threads/funding): `POST`/`GET
/projects/{id}/invitations` + `DELETE /projects/{id}/invitations/{inv_id}` (owner/admin, `204` on
revoke like member-removal); `GET /me/invitations` + `POST /invitations/{inv_id}/accept|decline`
(invitee). Registered in `api/router.py`.

### 5. Migration `0010_project_invitations` (T3.5)

Additive, `down_revision="0009_account_email_index"`: creates the `invitation_status` enum +
`project_invitations` table (FKs, per-FK indexes, `uq_project_invitation`), reusing the existing
`project_role` enum (`create_type=False`). No backfill. `downgrade()` drops the table + enum. Mirrors
`0007`'s enum/index idiom; ships with the backend code.

### 6. Frontend (T3.6 / T3.7 / T3.8)

- **Types/client/keys** — `InvitationStatus` / `ProjectInvitation` / `InvitationCreate`; six client
  fns; `myInvitations` + `projectInvitations(id)` keys.
- **`invitation-inbox.tsx`** — a header **bell + count badge** (`getMyInvitations`, `enabled` only
  when signed in) with a dropdown of pending invites (project title, inviter `@handle`, role) and
  **Accept** / **Decline** (per-row pending via `useMutation.variables`). Accepting invalidates the
  inbox **and** that project's member list, so the badge and the workspace's `canManage` gate update
  together. Mounted before `<AuthMenu/>`; self-hides when signed out.
- **`collaborators-panel.tsx`** — owner/admin gets an invite-by-`@username`-or-email field + the
  project's pending invitations with a **Revoke** control; `404`/`409` surface inline. The pending
  fetch is gated on the manage capability (the read `403`s for non-managers).

---

## Tests (T3.9)

- **DB-free** (`tests/test_invitations.py`, always run): the three invitation write/inbox endpoints
  reject an unauthenticated request at the `ActingActor` dependency before any DB access (the
  `auth_dev_header_enabled=False` posture via `dbfree_client`).
- **DB-backed** (skip without `TEST_DATABASE_URL`): invite by `@username` **and** email → `PENDING`
  (PII-safe shape asserted); unknown identifier → `404`; self / already-member / already-pending →
  `409`; `GET /me/invitations` caller-scoped; accept mints the admin membership (and that admin can
  then `PATCH` the project) **with no `Contribution`**; admin-invites-admin; decline → no membership;
  re-invite after decline resets the **same** row; non-invitee accept/decline → `403`; revoke →
  `204` (then accept → `409`); non-member invite/list → `403`.

## Verification commands

```bash
cd backend && uv run ruff check . && uv run pytest          # 55 passed / 75 skipped (no DB)
cd frontend && npm run typecheck && npm run lint && npm run build   # all green, 7 routes
```

Model↔migration parity + single head (no DB needed):

```bash
cd backend && uv run python -c "from sqlalchemy.schema import CreateTable; \
from sqlalchemy.dialects import postgresql; from app.models.project_invitation import ProjectInvitation as P; \
ddl=str(CreateTable(P.__table__).compile(dialect=postgresql.dialect())); \
assert 'uq_project_invitation' in ddl and 'invitation_status' in ddl"
cd backend && uv run alembic heads   # -> 0010_project_invitations (head)  [single]
```

## Follow-ups (not this slice)

- **Live (manual):** after `fly deploy` (+ Vercel redeploy), invite a second test account by handle
  and by email, see the bell, accept, and confirm the new admin can edit the project; optionally run
  the DB-backed suite against a throwaway Postgres for a dedicated verification pass.
- **Out of scope (proposal §7):** inviting someone **not yet signed up** (email invite to a stranger)
  — today's flow is existing-users-only. `accounts.email` is still not uniqueness-enforced, so email
  resolution treats a rare multi-match as the most-recent account; a `lower(email)` unique constraint
  would make email findability unambiguous if wanted.
- **Stewardship line complete:** ownership (`0.8.1`) → `@username` (`0.8.3`) → collaboration
  (`0.8.7`). No further planned slices in this line.
