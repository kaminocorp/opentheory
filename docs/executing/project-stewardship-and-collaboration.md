# Project Stewardship & Collaboration

> **Status:** proposal (review complete — ready for an implementation plan) · **Proposed release:** `0.8.0`
> · **Author:** drafted with Claude, reviewed by @phil
>
> Lets a project creator **own** their project, **edit** its title / question /
> description, attach a deep optional **background context** (rich text), and
> **invite already-registered users (by `@username`) as admins** who can edit it too —
> with an accept/decline invitation inbox. Adds a real unique **`@username`** to
> accounts, and introduces the platform's first *project-level authorization* — kept
> structurally separate from the funder / contributor / validator credit roles.

---

## 1. What this delivers (the ask)

On the project page, as the project creator I want to:

- **(A)** Change the project **title**.
- **(B)** Change the project **question** and **description** (the prose under the title).
- **(C)** **Invite already-registered users (by `@username`) as "admins"** so they can
  edit the project exactly as I can — they get an **invitation notification** and
  **accept/decline** it.
- **(D)** Add a deeper, optional **"Research Background / Context"** — a long-form,
  `nullable`, **rich-text** field to describe the research question in far more detail.

## 2. Decisions locked from review

| # | Decision |
|---|----------|
| Field model (D) | Four-tier text: `title` / `question` / `description` (all short) + new long-form `background`. Field named **`background`**. |
| Editable (B) | `title`, `question`, `description` all editable. **`slug` stays immutable.** |
| Ownership backfill | **No automated backfill** of project owners — existing projects (e.g. "Pythagoras Theorem") get their owner row added **by hand in Supabase**. |
| Admin invites | **Admins can invite** other admins (not owner-only). |
| Create = contribution | **Yes** — project creation records a `create_project` `Contribution`. |
| Invite identifier | **A real unique `@username`** (new `accounts.username` column, auto-generated + backfilled). When inviting, an existing user is **findable by `@username` or email**. |
| Rich-text editor | **TipTap** (WYSIWYG), serializing to/from Markdown. |
| Re-invite after decline | Allowed — re-inviting a declined user resets their invitation to `PENDING`. |
| Invite flow (C) | **Existing users only.** Invite by `@username` → invitee sees a pending invite in a top-right **notifications inbox** → **accept** (becomes admin) or **decline**. "Invite someone not yet signed up" is **out of scope** for now. |
| Background storage (D) | **Rich text serialized to Markdown, stored in a `TEXT` column** (not JSONB) — best for portability, diffing, and future agent full-text/embedding search. |
| Member visibility | Member list (handles + roles) is **public**. |

Still open → see **§7**.

## 3. Current state (why this is the shape it is)

Three facts from the code drive the design:

1. **The prose under the title is `project.question`, not `description`.** `Project` has
   *both* `question` (required `Text`) and `description` (nullable `Text`), but the create
   form collects only `title` + `question` + `slug`, so `description` is **always null**
   today. The four-tier hierarchy is already half-built.

2. **Projects have no owner, creator, or membership**, and `create_project`
   (`api/routes/projects.py`) records **no ownership and no `Contribution`** (a `# deferred`
   comment says so). So **(C) is "introduce project authorization,"** and that same
   authorization gates **(A)/(B)/(D)**.

3. **Identity/authorization is keyed to the `Account` (the principal).** Since `0.7.0`,
   `roles`, `email`, and funding attribution live on `Account`, and the account is
   **JIT-provisioned on first sign-in** (`api/deps.py::_resolve_or_provision`) from the
   Supabase JWT (`sub` / `email` / `name`). The new `username` and project membership both
   live at this principal grain. `Project` is **not** append-only guarded, so editing
   metadata in place is legitimate — a title fix is not a ledger event.

## 4. Design

### 4.0 Guardrail: admin ≠ a credit role

`docs/primitives.md` makes "funder finances / contributor produces / validator assesses —
never conflated" a load-bearing rule about **intellectual credit and provenance**.
**Project admin is none of those — it is access control / governance.** Membership grants
the *capability* to edit a project; it confers **no authorship, validation, or funding
credit**. So:

- Membership and invitations live in their **own** tables — never on `Contribution` /
  `Validation` / `FundingAllocation`.
- Editing project metadata records **no** `Contribution` (only *creating* a project does
  — that's intellectual origination).
- Agent-ready shape: later an *agent* actor owned by an admin account inherits the same
  edit capability via the same API — no parallel model.

### 4.1 Text-field model — (A), (B), (D)

| Field | Required | Shown as | Purpose |
|-------|----------|----------|---------|
| `title` | yes | H1 | the project name — **(A)** |
| `question` | yes | prominent paragraph | the tightly-scoped research question — **(B)** |
| `description` | no (nullable) | muted paragraph | short public summary / abstract — **(B)** |
| `background` *(new)* | no (nullable) | a new "Background / Context" section | the deep, long-form rich-text briefing — **(D)** |

- **(D) adds one column:** `projects.background` `Text`, `nullable=True`, storing
  **Markdown** (see §4.7). Generous soft cap (~20–50k chars) in the Pydantic schema; no
  hard DB cap.
- **(B):** the edit form carries `title` + `question` + `description`, so all three are
  editable and `description` finally becomes populatable (also addable at create time).

### 4.2 Account `@username` (new — public handle, prerequisite for invites)

A real, unique, public handle on the **principal**, distinct from `display_name`
(free-form, non-unique) and `email` (private). This is what you type to invite someone.

- **Column:** `accounts.username` `String(30)`, `nullable=False`, `unique=True`. Stored
  **lowercased**; validated against `^[a-z0-9_]{3,30}$` (X/Instagram-style). Case-
  insensitive uniqueness via lowercase-on-write (no `citext` needed). A small reserved set
  (`me`, `admin`, `system`, `accounts`, …) is rejected.
- **Auto-generated on first sign-in** (`_resolve_or_provision`): derive a base from the
  email local-part (else `display_name`, else `"user"`), slugify to the pattern, truncate,
  and resolve collisions with a numeric/short-random suffix — generating + inserting in the
  **same first-login transaction**, retrying on a unique-violation. So every account has a
  handle immediately; **no "choose a username" gate** blocks first use, and invite-by-handle
  works with zero setup. (Existing `external_id`-race retry is preserved; a username
  collision regenerates and retries.)
- **Editable later:** `PATCH /me` (owner-only, see §4.6) changes the handle, `409` on
  collision. Backend is cheap; a basic field in the identity menu is in scope, polish
  optional. → **§7-Q1**.
- **Backfill (migration `0008`):** existing accounts (your account) get a generated handle
  via a **hand-authored backfill** (like `0006`): add the column nullable → backfill unique
  handles → set `NOT NULL` + `UNIQUE`. Trivial at current row counts.
- **Exposure:** add `username` to `AccountRead` (`/me`) and to the public `AccountSummary`
  (it's a public handle, **not** PII — unlike email/roles, which stay off `AccountSummary`).

### 4.3 Project authorization & membership — foundation for (C)

**`ProjectRole`** — new `StrEnum` in `models/enums.py` → named PG enum `project_role`:

```
class ProjectRole(StrEnum):
    OWNER = "owner"   # exactly one per project; superset of admin
    ADMIN = "admin"   # can edit metadata + invite admins
```

**`ProjectMember`** — `models/project_member.py`, table `project_members` (`IdMixin` +
`TimestampMixin`), mirroring `models/links.py`:

- `project_id` → `projects.id` `ON DELETE CASCADE`, indexed
- `account_id` → `accounts.id` `ON DELETE CASCADE`, indexed *(the principal)*
- `role` → `Enum(ProjectRole, name="project_role")`
- `invited_by_account_id` → `accounts.id` `ON DELETE SET NULL`, nullable *(provenance)*
- `UniqueConstraint(project_id, account_id)` — one membership per principal per project
- **Partial unique index** `uq_project_one_owner ON project_members(project_id) WHERE role = 'OWNER'`
  — at most one owner. Declared on the model **and** the migration (so `create_all` matches
  Alembic — same discipline as `uq_actors_one_human_per_account`). Enum label uppercase
  (`'OWNER'`).
- Register in `models/__init__.py` `__all__`.

**Capability matrix:**

| Action | owner | admin | other signed-in | anon |
|--------|:-----:|:-----:|:---------------:|:----:|
| View project / ledger / member list (public) | ✓ | ✓ | ✓ | ✓ |
| Edit `title` / `question` / `description` / `background` / `status` | ✓ | ✓ | ✗ | ✗ |
| Invite an admin | ✓ | ✓ | ✗ | ✗ |
| Remove a member | ✓ | ✗ | ✗ | ✗ |
| Transfer ownership / change roles | ✓ | ✗ | ✗ | ✗ |
| Delete / archive project | ✓ | ✗ | ✗ | ✗ |

Unauthenticated edit → **401**; signed-in non-member → **403**; missing project → **404**.
Enforced in `services/project_members.py::ensure_can_manage(db, project_id, actor, *,
require_owner=False)` — the project-level analog of `require_internal`.

> **Ownerless projects:** with no automated backfill, existing projects have no owner until
> you add the row in Supabase, so `ensure_can_manage` will `403` on them until then. New
> projects always get an owner on create (§4.4).

### 4.4 Ownership + contribution on create

Extract the long-deferred `services/projects.py::create_project`. In **one transaction**:

1. Insert the `Project`.
2. Insert `ProjectMember(project, account=creator's account, role=OWNER, invited_by=self)`.
3. Record a `create_project` `Contribution` (`action="create_project"`,
   `target_type="project"`, `target_id=project.id`, attributed to the **acting actor** —
   the *act* is the actor's; ownership is the account's, mirroring the funding act-vs-money
   split). `Contribution.action` is a free string, so no enum change.

One commit, so a project can never exist without its owner + creation record.

### 4.5 Invitations — the (C) flow (existing users, by `@username`, accept/decline)

**`InvitationStatus`** — `StrEnum` → named PG enum `invitation_status`: `PENDING`,
`ACCEPTED`, `DECLINED`, `REVOKED`.

**`ProjectInvitation`** — `models/project_invitation.py`, table `project_invitations`:

- `project_id` → `projects.id` `ON DELETE CASCADE`, indexed
- `invitee_account_id` → `accounts.id` `ON DELETE CASCADE`, indexed
- `role` → `Enum(ProjectRole, name="project_role")` (default `ADMIN`)
- `status` → `Enum(InvitationStatus, name="invitation_status")` (default `PENDING`)
- `invited_by_account_id` → `accounts.id` `ON DELETE SET NULL`, nullable
- `UniqueConstraint(project_id, invitee_account_id)` — one row per pair (re-inviting a
  declined user resets it to `PENDING`, → §7-Q3).

**Flow (the invitee must already have an account):**

1. **Invite:** owner/admin `POST /projects/{id}/invitations { identifier, role }`. The
   `identifier` is a `@username` **or an email** — the backend resolves it case-insensitively
   to an **existing** `Account` (an email shape → match `accounts.email`, else match
   `accounts.username`). `404` if no such user; `409`/idempotent if already a member or
   already pending. Creates a `PENDING` invitation. (Caveat: `accounts.email` is not
   uniqueness-enforced, so a rare ambiguous email match → `409`.)
2. **Notify:** `GET /me/invitations` returns the caller's `PENDING` invitations (project
   title + inviter `AccountSummary`). Drives the top-right bell badge.
3. **Accept:** `POST /invitations/{id}/accept` (invitee only) → one txn: create
   `ProjectMember(role=invitation.role)` + mark `ACCEPTED`. **Membership is created only on
   accept** (explicit consent).
4. **Decline:** `POST /invitations/{id}/decline` (invitee only) → mark `DECLINED`.
5. **Revoke (owner/admin):** `DELETE /projects/{id}/invitations/{id}` → `REVOKED`.

**PII posture:** the inviter types a public handle they know; we never list accounts or
surface anyone's email. Invitation/member reads use `AccountSummary` (id + display_name +
username) only.

### 4.6 API surface

```
PATCH  /me                                     # owner-only: change own username (409 on collision)
PATCH  /projects/{id}                          # (A)(B)(D) + status; owner/admin; partial update
GET    /projects/{id}/members                  # public: [{ account: AccountSummary, role }]
DELETE /projects/{id}/members/{account_id}     # owner-only
PATCH  /projects/{id}/members/{account_id}     # owner-only: change role / transfer ownership

POST   /projects/{id}/invitations              # owner/admin: invite by { identifier (username|email), role }
GET    /projects/{id}/invitations              # owner/admin: this project's pending invites
DELETE /projects/{id}/invitations/{inv_id}     # owner/admin: revoke a pending invite

GET    /me/invitations                         # invitee inbox: my PENDING invitations
POST   /invitations/{inv_id}/accept            # invitee: accept → become admin
POST   /invitations/{inv_id}/decline           # invitee: decline
```

- **`ProjectUpdate` schema** — all fields **optional**; applied with
  `model_dump(exclude_unset=True)`. Editable: `title`, `question`, `description`,
  `background`, `status`. `slug` excluded (immutable). Plain in-place mutation; `updated_at`
  bumps; no checkpoint, no append-only guard.
- **`AccountUpdate` schema** (for `PATCH /me`) — `username` only for now (validated to the
  handle pattern).

### 4.7 `background` storage & rendering (rich text → Markdown → TEXT)

- **Store Markdown in `projects.background TEXT`** (not JSONB). Rationale (esp. future agent
  search): plaintext Markdown is embeddable, full-text-searchable (Postgres `to_tsvector` +
  GIN), greppable, diffable, and editor-agnostic — whereas rich-doc JSONB buries prose in
  structural nodes that are awkward to index and couple us to one editor. (A generated
  `tsvector` + GIN index is a clean *future* add.)
- **Editor:** **TipTap** (WYSIWYG) configured to **serialize to/from Markdown** (via its
  markdown extension) — rich editing UX, portable plaintext storage.
- **Render:** `react-markdown` (+ `remark-gfm`, sanitized) in the new "Background / Context"
  section.

### 4.8 Frontend

- **Types** (`types/project.ts`, `types/research.ts`): add `background` to `Project` /
  `ProjectOverview` / `ProjectCreate`; add `username` to `Account` / `Me` / `AccountSummary`;
  add `ProjectUpdate`, `AccountUpdate`, `ProjectMember`, `ProjectRole`, `ProjectInvitation`,
  `InvitationStatus`.
- **API client** (`lib/api.ts`): `updateProject`, `updateMe`, `listProjectMembers`,
  `removeProjectMember`, `updateProjectMember`, `inviteProjectMember`,
  `listProjectInvitations`, `revokeInvitation`, `getMyInvitations`, `acceptInvitation`,
  `declineInvitation`.
- **Capability gating (client-side):** derive `canManageProject` by matching `me.account.id`
  against the members list (server-side authz still enforces everything; the client check
  only decides whether to *show* affordances — same pattern as `canWrite`).
- **Edit form:** an "Edit" control in the workspace header (`project-workspace.tsx`), shown
  only when `canManageProject`, for title / question / description / background / status.
- **Background section:** a new collapsible "Background / Context" block rendering the
  Markdown.
- **Collaborators panel:** lists members (`@handle` + role pill); for owner/admin, an
  invite form accepting **`@username` or email** + pending-invites list + remove/role controls.
- **Invitation inbox (the notification UX):** a **bell icon in the app-shell header, next to
  the auth menu**, badge = count from `getMyInvitations()`. Dropdown lists each pending invite
  (project title, inviter, role) with **Accept / Decline**; accepting invalidates the members
  + invitations queries (and can route to the project). New
  `components/shell/invitation-inbox.tsx`.
- **Username:** show `@handle` in the identity menu; a simple "edit username" field
  (`PATCH /me`) with a collision error (polish-optional).

### 4.9 Migrations & plumbing

- **`0007_project_stewardship`** (additive) — Phase `0.8.1`: `projects.background`;
  `project_role` enum; `project_members` table (+ unique + partial owner index). No data
  backfill.
- **`0008_account_username`** (hand-authored backfill) — Phase `0.8.2`: add
  `accounts.username` nullable → backfill unique handles for existing accounts → `NOT NULL` +
  `UNIQUE`. Ship with the `_resolve_or_provision` generation change (old code that can't set
  username would otherwise insert NULLs).
- **`0009_project_invitations`** (additive) — Phase `0.8.3`: `invitation_status` enum;
  `project_invitations` table.
- Register new models in `models/__init__.py` `__all__`; declare the partial owner index on
  the model so `create_all` mirrors Alembic.

### 4.10 Tests

- **DB-backed** (gated on `TEST_DATABASE_URL`): owner row + `create_project` contribution on
  create; `PATCH` authz (owner ✓, admin ✓, non-member 403, anon 401); `background`
  round-trips/nullable; username auto-generated + unique on provision, collision suffixing,
  `PATCH /me` rename + 409; invite by handle **or email** → pending → accept creates admin /
  decline doesn't; invite unknown identifier → 404; duplicate member/owner constraints; member-list +
  invitation reads omit email; `/me/invitations` returns only the caller's pending.
- **DB-free**: `ProjectUpdate` / `AccountUpdate` validation (incl. handle pattern + reserved
  names); role/capability predicate; read schemas omit email.

## 5. Phasing (small, demoable releases — per repo convention)

- **`0.8.1` — Ownership + self-edit (unblocks you immediately).** `background`,
  `ProjectMember` + creator→owner + `create_project` contribution, `PATCH /projects/{id}` +
  authz, rich-text editor + background section + edit form. → **(A)(B)(D)** on your own
  projects. *(You add your owner row to existing projects in Supabase by hand.)*
- **`0.8.2` — Account `@username` (prerequisite for invites).** Column + auto-generation +
  backfill + `/me` exposure + `AccountSummary` + `PATCH /me` rename.
- **`0.8.3` — Collaborators + invitation inbox.** `ProjectInvitation` + invite-by-handle /
  accept / decline + `/me/invitations` + Collaborators panel + the top-right bell inbox. → **(C)**.

## 6. Alignment with the domain model

- **Human-first / agent-ready:** stewardship + handles are plain human capabilities now; an
  agent actor (owned by an admin account) later edits via the *same* API.
- **Credit stays clean:** membership/invitations are access control, separate from
  funder/contributor/validator credit (§4.0); only project *creation* is a contribution.
- **Append-only preserved:** `Project`/`Account` are deliberately mutable; nothing here
  touches the append-only ledger or the checkpoint chokepoint.
- **Principal grain:** `username`, membership, and invitations all key on `Account`,
  consistent with `0.7.0`.
- **Agent-searchable knowledge:** Markdown-in-TEXT keeps the deepest prose field
  (`background`) directly indexable for future agent FTS/embeddings.

---

## 7. Resolved (review complete)

All review questions are settled — nothing blocking the implementation plan:

- **Username:** auto-generated unique handle on first sign-in (`NOT NULL`); renameable via
  `PATCH /me` (409 on collision), with a simple edit field in `0.8.2`.
- **Findability:** when inviting, an existing user resolves by **`@username` or email**.
- **Editor:** **TipTap** (WYSIWYG → Markdown).
- **Re-invite after decline:** allowed; resets the invitation to `PENDING`.
- **Invite scope:** build the real existing-user invite + accept/decline + bell inbox in
  `0.8.3`; only the not-yet-registered / deferred-resolution case is out of scope.

**Minor caveat to carry into implementation:** `accounts.email` is **not** uniqueness-
enforced today, so email-based invite resolution treats a (rare) multi-match as `409`
ambiguous. If we'd rather guarantee email findability is unambiguous, a follow-up could add a
unique constraint on `lower(email)` — out of scope here.

## 8. Next artifact

A step-by-step **implementation plan** (the second doc, mirroring the
`account-owns-actor` → `account-owns-actor-implementation-plan` pattern), sequenced
`0.8.1 → 0.8.2 → 0.8.3`, with the exact model/schema/route/migration/test changes per phase.
