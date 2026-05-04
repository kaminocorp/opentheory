# OpenTheory Frontend

Next.js frontend for the OpenTheory research platform.

## Local Setup

```bash
npm install
cp .env.example .env.local
npm run dev
```

The app expects the FastAPI backend at `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000/api/v1`.

## Checks

```bash
npm run typecheck
npm run lint
npm run build
```

