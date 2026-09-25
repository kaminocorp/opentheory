# Deploying OpenTheory

This is the runbook for the first live deploy: **backend → Fly.io**, **frontend → Vercel**,
pointing at the **existing live Supabase database**. It assumes the scaffolding in this repo
(`backend/Dockerfile`, `backend/fly.toml`, `backend/.dockerignore`).

> ⚠️ **No authentication yet.** `X-Dev-Actor-Id` is not a credential — it just claims "act as
> actor X". A publicly reachable backend is therefore fully open: anyone with the URL can read
> and write to the database it points at. That's an accepted trade-off for this preview (real
> auth lands in `0.6.0`). Don't put anything sensitive in the live DB until then.

## Topology

```
Browser ──> Vercel (Next.js frontend)
                │  NEXT_PUBLIC_API_BASE_URL = https://<fly-app>.fly.dev/api/v1
                ▼
            Fly.io (FastAPI backend)
                │  app runtime  -> Supabase TRANSACTION pooler (:6543, asyncpg)
                │  migrations   -> Supabase DIRECT connection  (:5432)
                ▼
            Supabase Postgres (already live)
```

## Prerequisites

- `flyctl` installed and logged in: `fly auth login`
- Vercel CLI installed and logged in: `vercel login` (or use the dashboard)
- Your local `backend/.env` already has working `DATABASE_URL` (and ideally
  `MIGRATION_DATABASE_URL`) values — these were proven against the live DB in `0.4.6`. You'll
  copy those exact values into Fly secrets, so you don't have to re-derive the connection strings.

---

## Part A — Backend → Fly.io

Run from `backend/`.

1. **Create the app** (don't deploy yet — secrets aren't set):

   ```bash
   cd backend
   fly launch --no-deploy
   ```

   When prompted, keep the existing `fly.toml`. Note the app name it assigns (or set your own);
   make sure the `app = "..."` line in `fly.toml` matches. Pick a region near your Supabase DB.

2. **Set secrets** (these are encrypted and injected at runtime; never commit them). Copy the
   `DATABASE_URL` / `MIGRATION_DATABASE_URL` values straight from your local `backend/.env`:

   ```bash
   fly secrets set \
     DATABASE_URL='postgresql+asyncpg://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:6543/postgres?ssl=require' \
     MIGRATION_DATABASE_URL='postgresql+asyncpg://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres?ssl=require' \
     BACKEND_CORS_ORIGINS='https://example.vercel.app' \
     TOOLBENCH_MEMORY_LIMIT_MB=256 \
     TOOLBENCH_MAX_CONCURRENT_RUNS=2
   ```

   - `DATABASE_URL` → the **transaction pooler** (port `6543`). The app disables asyncpg's
     statement cache (`app/db/session.py`) so this is pooler-safe.
   - `MIGRATION_DATABASE_URL` → the **direct** connection (port `5432`). Alembic uses it for DDL.
   - `BACKEND_CORS_ORIGINS` → put a placeholder for now; you'll set the real Vercel URL in Part C.
   - Keep the scheme `postgresql+asyncpg://` and the `?ssl=require` suffix on both.

3. **Deploy:**

   ```bash
   fly deploy
   ```

   On deploy, the `release_command` (`alembic upgrade head`) runs first in a temporary machine.
   Since the live DB is already at head (`0003`), this is a no-op confirming connectivity. If a
   later phase adds a migration, this is where it applies.

4. **Smoke-test** the live backend:

   ```bash
   curl https://<fly-app>.fly.dev/api/v1/health      # -> {"status":"ok"} (or similar)
   curl https://<fly-app>.fly.dev/api/v1/projects    # -> your projects (or [])
   ```

---

## Part B — Frontend → Vercel

The frontend lives in `frontend/`, so Vercel must treat that as the project root.

**Dashboard path (recommended for the first time):**

1. Import the Git repo at <https://vercel.com/new>.
2. Set **Root Directory** to `frontend`. Framework preset auto-detects as **Next.js**.
3. Add an environment variable:
   - `NEXT_PUBLIC_API_BASE_URL` = `https://<fly-app>.fly.dev/api/v1`
4. Deploy. Note the resulting URL (e.g. `https://opentheory.vercel.app`).

**CLI path (alternative):**

```bash
cd frontend
vercel link                       # set root dir to this folder when asked
vercel env add NEXT_PUBLIC_API_BASE_URL production   # paste https://<fly-app>.fly.dev/api/v1
vercel --prod
```

> `NEXT_PUBLIC_` vars are baked in at **build** time, so changing the API URL later requires a
> redeploy of the frontend, not just an env edit.

---

## Part C — Wire CORS (close the loop)

Now that you know the real Vercel URL, point the backend's CORS at it (no trailing slash):

```bash
cd backend
fly secrets set BACKEND_CORS_ORIGINS='https://opentheory.vercel.app'
```

Setting a secret restarts the backend. Then open the Vercel URL in a browser, pick/create a
dev actor (top-right), and exercise the flow: create a project → thread → claim → checkpoint,
record a validation, fork a branch. If the browser console shows a CORS error, the origin in
`BACKEND_CORS_ORIGINS` doesn't exactly match the site's origin (scheme + host, no trailing slash).

---

## Toolbench execution caps (`0.11.x`)

The backend runs SymPy instruments in killable subprocesses on the `shared-cpu-1x` / `512mb` Fly
machine. Set these secrets alongside the DB URLs (tune after observing `resource_used` logs in
`0.11.5`):

| Secret | Suggested prod value | Role |
|---|---|---|
| `TOOLBENCH_MEMORY_LIMIT_MB` | `256` | Child `RLIMIT_AS` ceiling (Linux) |
| `TOOLBENCH_MAX_CONCURRENT_RUNS` | `2` | Semaphore on instrument runs |
| `TOOLBENCH_WALL_TIMEOUT_S` | `30` (default) | Wall-clock kill for sync + async runs |

Leave `TOOLBENCH_SUBPROCESS_SANDBOX_ENABLED=true` in production. Local dev defaults
`TOOLBENCH_MEMORY_LIMIT_MB=0` because `RLIMIT_AS` is unreliable on macOS.

## Lean 4 (optional, `0.23.0`)

`lean.prove` is registered whether or not Lean is installed. **Do not install Lean
in CI** — the suite stays green on the missing-toolchain path
(`undecided` / `unavailable`). Other instruments do not depend on it.

**What CI runs:** banned-construct / no-theorem / timeout / crash / unavailable
unit tests, plus a fake-binary "proved" path. Tests that invoke a real `lean`
binary are `@pytest.mark.skipif` and stay skipped.

**What production needs for a real Grade A proof:** the `lean` binary on the
Fly machine PATH (elan wrapper is fine). Prelude / `Init` only unless the
Mathlib image path below is enabled.

Exact install path — rebuild the backend image with the optional Dockerfile
arg (do not put this in the default CI image):

```bash
cd backend
fly deploy --build-arg INSTALL_LEAN=1 --build-arg LEAN_TOOLCHAIN=leanprover/lean4:v4.14.0
```

That runs the official [elan](https://github.com/leanprover/elan) installer
inside the image, pins `leanprover/lean4:v4.14.0`, and prepends
`/root/.elan/bin` to `PATH`. Confirm on the machine:

```bash
fly ssh console -C 'lean --version'
```

Without that rebuild, `lean.prove` still appears in the catalog and still
lands attributed checkpoints: a missing binary is recorded as
`undecided` / `unavailable`, never as a proof. Keep
`TOOLBENCH_LEAN_TIMEOUT_MS` (default 8000) strictly below
`TOOLBENCH_WALL_TIMEOUT_S` so a slow typecheck is citable undecided rather
than a sandbox kill that mints nothing.

v1 (`0.23.0`) does **not** ship a Mathlib oleans cache or a `lake` project.
A snippet that `import`s anything without the Mathlib opt-in is rejected
before `lean` runs.

## Mathlib / lake (optional, `0.26.0`)

`lean.prove` `mathlib=true` needs a pre-built lake project with a Mathlib
oleans cache. **Do not install Mathlib in CI.** Missing cache is
`undecided` / `mathlib_unavailable`, never Grade A.

**What CI runs:** allow-list / banned-construct / missing-cache / fake-`lake`
prove-fail-timeout tests. Tests that invoke a real Mathlib cache are
`@pytest.mark.skipif`.

**What production needs for a Mathlib Grade A proof:** `lean` + `lake` on
PATH and `/opt/opentheory/lean-mathlib/.lake/packages/mathlib` present.
Rebuild with both optional args (Mathlib requires Lean):

```bash
cd backend
fly deploy --build-arg INSTALL_LEAN=1 --build-arg INSTALL_MATHLIB=1 \
  --build-arg LEAN_TOOLCHAIN=leanprover/lean4:v4.14.0 \
  --build-arg MATHLIB_REV=v4.14.0
```

That pins the toolchain, `lake update`s Mathlib at `MATHLIB_REV`, pulls the
community oleans cache (`lake exe cache get`), and `lake build`s the
scaffold at `backend/lean-mathlib/`. The image is **several GB** — do not
turn this on for the default CI image. Confirm:

```bash
fly ssh console -C 'lean --version'
fly ssh console -C 'lake --version'
fly ssh console -C 'test -d /opt/opentheory/lean-mathlib/.lake/packages/mathlib && echo mathlib-ok'
```

Runtime checks are `lake --offline env lean` on an overlay of that project.
`lake` must not fetch at check time. Keep
`TOOLBENCH_LEAN_MATHLIB_TIMEOUT_MS` (default 20000) strictly below
`TOOLBENCH_WALL_TIMEOUT_S` so a slow import is citable undecided rather
than a sandbox kill that mints nothing.

If the Mathlib rebuild is skipped, `mathlib=true` still records an
attributed checkpoint: `undecided` / `mathlib_unavailable`. Prelude
`lean.prove` is unchanged.

## Agent loop prod light-up (`0.12.x` / Phase 1 autonomy)

The thin agent loop is **complete in the codebase and ships dark**. Lighting it up
in production is exactly two settings — **both required**; either one alone leaves
the loop unusable. **Do not invent a second key or a second flag.** A completed
pass's checkpoints stand without a human gate (`0.17.0`); the loop still will not
run in production until both of these are set.

1. Set the OpenRouter key as a Fly **secret** (never `fly.toml [env]`, never the
   frontend, never a committed `.env`):

   ```bash
   cd backend
   fly secrets set OPENROUTER_API_KEY='…'
   ```

2. Flip the dark-launch flag:

   ```bash
   fly secrets set AGENT_LOOP_ENABLED=true
   ```

| State | What operators see |
| --- | --- |
| `AGENT_LOOP_ENABLED` unset / `false` (the default) | Every agent-run, orchestration, **and** campaign route `404`s, before auth |
| Flag `true`, no `OPENROUTER_API_KEY` | A commissioned pass fails cleanly (`422`/`503`), never a `500` |
| Flag `true` **and** the key set | The loop is live |

Leave `AGENT_LOOP_ENABLED=false` until you intend to take live agent traffic. Local
dev copies the same pair from `backend/.env.example`. Per-pass **safety** caps
(`AGENT_PASS_MAX_RUNS`, `AGENT_PASS_MAX_REPLANS`, `AGENT_PASS_MAX_BATCH_RUNS`,
`AGENT_PASS_MAX_TOKENS`) already bound blast radius — they are not budget. Full
project-budget metering shipped in `0.19.0` (historical `0.12.5`) and is **not**
required to flip the loop on — an unfunded project simply refuses to start a
pass (`available = 0`). The 0.22.0 project orchestrator (`Run research`) uses
the same flag and the same pot; `ORCHESTRATION_MAX_PASSES` (default 4) caps
how many sub-passes one commission may start, and `ORCHESTRATION_CONCURRENCY`
(default 2; `1` is sequential) caps how many of those run at once. Concurrent
passes reserve a slice of `available` before they start so they cannot oversell
the pot. The 0.25.0 / 0.32.0 continuous campaign (`Start` on Overview) reuses
that flag and that pot; `CAMPAIGN_MAX_CYCLES` (default 8),
`CAMPAIGN_CYCLE_CONCURRENCY` (default 1; `1` is sequential, hard-capped at 4),
and `CAMPAIGN_ERROR_BUDGET` (default 3) are safety caps, not a second
dark-launch switch. Concurrent cycle starts reuse the same reservation lock
as concurrent sub-passes so they cannot oversell.

### Live OpenRouter price metering (`0.28.0`)

Agent-pass `ComputeDebit` rows prefer the model's **live** OpenRouter prompt /
completion prices (`GET /models`) over the blended
`AGENT_TOKEN_RATE_USD_PER_1K` default. A missing key, a timed-out catalog, a
failed fetch, or a model the catalog does not list falls back to that blended
rate (or a catalog `usd_per_1k` override) and **records the fallback on the
debit** — metering is never skipped, and a fallback is never labelled as a live
price.

These are ops knobs, not a second dark-launch flag. The same
`OPENROUTER_API_KEY` is reused; do not invent a second key.

| Env | Default | Role |
|---|---|---|
| `OPENROUTER_LIVE_PRICES` | `true` | Off = always use the blended fallback (still meters) |
| `OPENROUTER_PRICE_CACHE_TTL_S` | `3600` | Process-local catalog cache. One `GET /models` per TTL. |
| `OPENROUTER_PRICE_TIMEOUT_S` | `2` | Hard cap on one catalog fetch. Keep tiny vs `AGENT_LLM_TIMEOUT_S` so a slow `/models` cannot stall a pass. |
| `AGENT_TOKEN_RATE_USD_PER_1K` | `0.005` | Blended fallback when live prices are unavailable. |

The cache is **in-process** (not Redis). A new Fly machine starts empty and
refreshes on the first pass. A refresh that fails after a successful fetch
keeps the stale catalog (still a live price, just older) rather than flipping
every subsequent debit to the blended default. Set
`OPENROUTER_LIVE_PRICES=false` only if `/models` is unhealthy and you want a
deterministic blended rate.

## Operating notes

- **Always-warm:** `fly.toml` sets `min_machines_running = 1`, so one machine stays running and
  there is no scale-to-zero cold start on the first request after idle. (It was `0`; the boot added
  several seconds on top of DB latency.) Set it back to `0` only to trade that latency for a cheaper
  idle preview.
- **Co-location:** the backend runs in `sin` (Singapore), the **same region as the Supabase DB**, so
  each DB round-trip is LAN-local (~1–5ms) rather than a ~230ms cross-Pacific hop. This is the single
  biggest latency lever — keep them co-located (see "Relocating the backend region" below).
- **Logs:** `fly logs` (backend) and the Vercel dashboard → Deployments → Logs (frontend).
- **Redeploys:** `fly deploy` (backend) re-runs migrations via the release command; Vercel
  redeploys on every push to the connected branch.
- **Custom domain:** add later via `fly certs` and Vercel's Domains tab; remember to update
  `NEXT_PUBLIC_API_BASE_URL` and `BACKEND_CORS_ORIGINS` if hostnames change.

## Relocating the backend region

The backend must sit in the **same region as the Supabase DB**. A request makes several DB
round-trips (pre-ping, begin, query, commit, and a fresh TLS+SCRAM handshake when the pooled
connection has dropped), so a distant DB multiplies that RTT per request — running in `iad` against
a Singapore DB made a 2-row `GET /projects` take ~2s while DB-free `/health` was ~0.5s. The DB is in
`ap-southeast-1` (Singapore), so the backend runs in Fly's `sin`.

> **Secrets are safe across this move.** Fly secrets are stored at the **app** level and injected
> into every machine, so destroying and rebuilding a *machine* preserves them — there is nothing to
> re-enter. The only thing that wipes them is destroying the **app** (`fly apps destroy`), and there
> is no `fly secrets export` (values are write-only) — the live values exist only in your local
> `backend/.env` and the Supabase dashboard. **Do not `fly apps destroy`.**

`fly.toml` already pins `primary_region = "sin"`. To re-home the running machine, from `backend/`:

```bash
# 0) See what you have. The machine carries the region; the app carries the secrets.
fly status
fly secrets list                       # names only (DATABASE_URL etc.) — confirms they're app-level
fly machine list                       # note the machine ID currently in iad

# 1) Destroy the iad machine. Removes the *machine*, not the app — secrets stay set.
fly machine destroy <iad-machine-id> --force

# 2) Deploy. With zero machines, Fly provisions a fresh one in primary_region (sin) and runs the
#    release_command (alembic upgrade head, a no-op when already at head) against the direct DB URL.
fly deploy

# 3) Verify region, warmth, and latency.
fly status                             # REGION = sin, STATE = started, checks passing
curl -s -o /dev/null -w 'projects ttfb=%{time_starttransfer}s\n' \
  https://opentheory-backend.fly.dev/api/v1/projects   # expect ~0.4-0.6s (was ~2s), close to /health
```

No Vercel change is needed — the `opentheory-backend.fly.dev` hostname is unchanged, so
`NEXT_PUBLIC_API_BASE_URL` and `BACKEND_CORS_ORIGINS` stay as-is.

> **Zero-downtime alternative.** `fly machine clone <iad-id> --region sin` brings up a sin machine
> (same image + app secrets) before you `fly machine destroy <iad-id>`; then `fly deploy` rolls the
> new image onto it. The destroy→deploy path above is simpler and ships the new image directly, at
> the cost of a brief gap (acceptable for a preview, and the machine was scale-to-zero anyway).

## Troubleshooting

- **Release/migration step can't reach the DB (IPv6/timeout).** The Supabase *direct* host is
  IPv6-only on some plans. Fly supports IPv6 egress, but if the release command can't connect,
  point `MIGRATION_DATABASE_URL` at the Supabase **session pooler** instead (port `5432` on the
  `...pooler.supabase.com` host) — it's also a stable, non-transaction connection suitable for DDL.
- **`prepared statement already exists` errors at runtime.** Means the app is hitting the pooler
  without the statement cache disabled — confirm `DATABASE_URL` is the pooler URL and that
  `app/db/session.py`'s `statement_cache_size=0` is in effect.
- **Preflight/CORS failures.** Origins must match exactly and carry no trailing slash; the app
  already strips trailing slashes defensively (`app/main.py`), but the value you set should be clean.
