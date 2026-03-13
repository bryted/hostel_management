## Go-Live Checklist

- Run `python -m app.scripts.healthcheck`
- Run `alembic upgrade head`
- Run `python -m compileall app worker`
- Run `pytest -q tests` against a test database or with transactional rollback enabled
- Run `cd frontend && npm run build`
- Confirm at least one strong-password admin account exists
- Confirm `.env` secrets are set from the deployment environment, not committed files
- Verify the reverse proxy terminates TLS and routes traffic to Next.js and FastAPI correctly
- Verify database backups and restore procedure before production cutover
- Verify notification credentials and worker services are enabled
- Verify the reservation expiry worker or timer is enabled so unpaid bed holds release automatically
- Execute the manual hostel flow:
  1. Create tenant
  2. Create and approve invoice
  3. Record payment
  4. Allocate bed
  5. Transfer or move out tenant
  6. Confirm reports reflect the change
