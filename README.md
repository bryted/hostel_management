# Hostel Management Platform

This repo now runs as a standard web application:
- `frontend/`: Next.js admin panel
- `backend/`: FastAPI application
- `app/`: shared SQLAlchemy models, services, scripts, and worker logic
- `worker/`: background jobs

The legacy Streamlit app has been retired.

## Local setup

### Prereqs
- Python 3.11+
- Node.js 20+
- PostgreSQL 14+

### Python setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

Create `.env` from `.env.example`, then run migrations:

```powershell
Copy-Item .env.example .env
alembic upgrade head
```

Session and login hardening settings now live in `.env` too:
- `SESSION_SECRET_KEY`
- `SESSION_MAX_AGE_SECONDS`
- `LOGIN_MAX_ATTEMPTS`
- `LOGIN_WINDOW_SECONDS`
- `LOGIN_LOCKOUT_SECONDS`

### Create the first admin user

```powershell
python -m app.scripts.create_admin --email admin@example.com --full-name "Admin User" --password "StrongPass1!"
```

### Frontend setup

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm install
```

## Run locally

### FastAPI

```powershell
uvicorn backend.hostel_api.main:app --reload --host 127.0.0.1 --port 8000
```

### Next.js

```powershell
cd frontend
npm run dev
```

Production-style frontend run:

```powershell
cd frontend
npm run build
npm run start
```

## Main routes

### Web app
- `/login`
- `/dashboard`
- `/onboarding`
- `/billing`
- `/invoices/:invoiceId`
- `/receipts/:receiptId`
- `/tenants`
- `/tenants/:tenantId`
- `/beds`
- `/allocations`
- `/inventory`
- `/reports`
- `/settings`

### API
- `/api/v1/auth/*`
- `/api/v1/dashboard/summary`
- `/api/v1/onboarding/queue`
- `/api/v1/billing/overview`
- `/api/v1/tenants`
- `/api/v1/tenants/:tenant_id/workspace`
- `/api/v1/beds`
- `/api/v1/allocations/overview`
- `/api/v1/reports/overview`
- `/api/v1/reports/finance-export.csv`
- `/api/v1/search`
- `/api/v1/settings/overview`
- `/api/v1/inventory/overview`
- `/api/v1/inventory/upload`

## Quality checks

```powershell
python -m compileall app backend worker
pytest -q tests
cd frontend
npm run typecheck
npm run build
```

## E2E browser tests

The Playwright suite runs against the live Next.js app.

Cashier flow with defaults:

```powershell
cd frontend
npx playwright install chromium
npm run test:e2e
```

Admin flow with explicit credentials:

```powershell
$env:E2E_ADMIN_USERNAME="admin@example.com"
$env:E2E_ADMIN_PASSWORD="StrongPass1!"
cd frontend
npm run test:e2e
```

The suite now covers:
- centered confirmation dialogs
- centered success and warning toasts
- billing overpayment blocking
- short-hold billing warnings
- duplicate-reference warn-only payment flow

CI automation for the same stack lives in [.github/workflows/e2e.yml](c:/Projects/hostel%20management/.github/workflows/e2e.yml).

## Healthcheck

```powershell
python -m app.scripts.healthcheck
```

## Worker jobs

Expire stale reservations:

```powershell
python -m worker.expire_reservations --limit 200
```

Continuous reservation expiry worker:

```powershell
python -m worker.run_expire_reservations_loop
```

Notification worker:

```powershell
python -m worker.send_notifications --limit 50
```

## Deployment notes

- Put FastAPI behind a reverse proxy.
- Serve Next.js on the public domain.
- Keep PostgreSQL private.
- Terminate TLS at Nginx or your edge proxy.
- Run workers separately from the web processes.
- Ensure the reservation expiry worker or timer runs continuously in production.
- Keep secrets in the environment, not committed files.

Deployment scaffolding is included in:
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `deploy/docker-compose.yml`
- `deploy/nginx/default.conf`
- `deploy/systemd/*.service`
- `deploy/systemd/*.timer`

## Go-live

See `GO_LIVE_CHECKLIST.md`.
