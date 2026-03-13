# Docker Deploy Notes

Use the Docker stack from `deploy/docker-compose.yml`.

## Environment

- Application defaults come from the project root `.env`.
- Docker-only database overrides belong in `deploy/.env.docker`.
- `deploy/.env.docker` is machine-specific and should not be committed.
- Start from `deploy/.env.docker.example` and replace the placeholder URL with the real deploy database connection string.

## Start

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
```

## Routing

- Browser traffic goes through Nginx on port `80`.
- Next.js handles `/`, `/api/session/*`, and `/api/proxy/*`.
- FastAPI handles `/api/*`.

## Notes

- The frontend container binds to `0.0.0.0:3000` so Nginx can reach it over the Docker network.
- Server-side Next fetches use the internal API base URL; browser traffic uses the public proxied API path.
