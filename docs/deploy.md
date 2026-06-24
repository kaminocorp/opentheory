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
     BACKEND_CORS_ORIGINS='https://example.vercel.app'
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

## Operating notes

- **Scale-to-zero:** `fly.toml` sets `min_machines_running = 0`, so the backend sleeps when idle
  and cold-starts (~1–2s) on the next request. Cheap for a preview. Set it to `1` if you want it
  always warm.
- **Logs:** `fly logs` (backend) and the Vercel dashboard → Deployments → Logs (frontend).
- **Redeploys:** `fly deploy` (backend) re-runs migrations via the release command; Vercel
  redeploys on every push to the connected branch.
- **Custom domain:** add later via `fly certs` and Vercel's Domains tab; remember to update
  `NEXT_PUBLIC_API_BASE_URL` and `BACKEND_CORS_ORIGINS` if hostnames change.

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
