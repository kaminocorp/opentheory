# 0.37.0 — GitHub Actions CI with Postgres

**Goal.** Close assessment R1 P2-5: make the contribution contract
(`ruff` + `pytest` + `typecheck` + `lint` + `test` + `build`) run on
every pull request and on push to `main`, with a throwaway Postgres so
the DB-gated suite actually runs instead of skipping.

**Shape.** One workflow, two parallel jobs. Infra only. **No schema, no
migration, no application code.** Sits on shipped `0.36.0` (`71a8929`)
and the R1 assessment (`375733a`, #22). Does not claim `0.36.1` /
`0.36.2`. Does not merge other PRs.

## What landed

- **`.github/workflows/ci.yml`.** `pull_request` + `push` to `main`.
  `contents: read`. Concurrency cancels stale runs on the same ref.
- **Backend job.** `uv sync --frozen --group dev`, `ruff check .`
  (fails the job), `alembic upgrade head` against empty Postgres
  (proves revisions apply), then `pytest` with
  `TEST_DATABASE_URL=postgresql+asyncpg://…` so fixtures do not skip.
  Postgres 16 service container. Python 3.12 via `astral-sh/setup-uv`
  with cache.
- **Frontend job.** Node 22, `npm ci`, `typecheck`, `lint`, `test`,
  `build`. npm cache on `frontend/package-lock.json`.
- **Honest skips stay honest.** Lean / Mathlib are not installed.
  `INSTALL_LEAN` / `INSTALL_MATHLIB` stay unset. Tests that need a
  `lean` binary or a Mathlib cache continue to skip. No secrets.
- **First-run test rot (tests only).** Write-path stubs named
  `calc.eval` / `expr.compare` were looked up in the sandbox child as
  the real instruments. They now register as `test.write*`. The
  geometry write-path assertion strips `*_latex` companions.

The pytest fixtures still `DROP SCHEMA public CASCADE` and
`Base.metadata.create_all` — they do not consume the Alembic-migrated
schema. The upgrade step is a separate honesty check.

## What did not change

- Ledger writes still go only through `create_checkpoint`.
- Append-only guards, membership, and claim create are untouched.
- Funder / contributor / validator stay separate tables.
- No Alembic revision — `0021_concurrent_campaign_cycles` stays the
  head on `main`.
- Unmerged assessment remediation (`0.36.1` / `0.36.2`, #23 / #25) is
  not this branch and is not claimed as shipped.

## Caveats (honest)

- Real-`lean` / Mathlib Grade-A paths stay skipped in CI. That is
  deliberate; missing toolchain is `undecided`, not a fake pass.
- Literature-pin instruments that hit the live network stay mocked or
  skip as the existing tests already do. No API keys in CI.
- A first workflow commit cannot show a green run until GitHub Actions
  picks up the file on this PR. Fix-forward if the first run reveals a
  config bug.
- Local default `pytest` without `TEST_DATABASE_URL` still skips. CI
  is now the gate that does not.

## Verification

Recorded after the local agent-VM run (see the PR).
