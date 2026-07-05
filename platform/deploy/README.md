# Production deployment — TLS + hardening

The dev compose files publish the backend (`:8000`) and frontend (`:3000`)
directly over plain HTTP for convenience. **Never run that configuration on a
public network.** In production, put the [Caddy](https://caddyserver.com) reverse
proxy in front: it terminates HTTPS, auto-provisions and renews a Let's Encrypt
certificate, sends the hardened security headers (HSTS, CSP, …), and is the only
thing exposed to the internet.

## Quick start

```bash
cd frs/backend            # (or any scenario's compose dir)

# 1. Point DNS: an A/AAAA record for your domain → this host's public IP.
# 2. Bring the stack up WITH the TLS overlay:
SITE_DOMAIN=frs.example.com ACME_EMAIL=ops@example.com \
  docker compose \
    -f docker-compose.yml \
    -f ../../platform/deploy/docker-compose.tls.yml \
    up -d
```

Caddy obtains a certificate on first boot (ports **80** and **443** must be
reachable for the ACME challenge) and redirects all HTTP → HTTPS automatically.

- **Requires Docker Compose v2.24+** for the `!reset` port override. On older
  Compose, instead edit the base file to remove the `ports:` from `backend` and
  `frontend` so only Caddy is published.
- **Local / staging (no public DNS):** set `SITE_DOMAIN=localhost`. Caddy issues
  an internal-CA certificate; trust it locally or accept the browser warning.

## What the overlay changes

| Concern | Dev | Production (this overlay) |
|---|---|---|
| Ingress | backend :8000, frontend :3000 on host | **only** Caddy :80/:443 |
| Transport | plain HTTP | HTTPS (auto-renewing cert) + HTTP→HTTPS redirect |
| HSTS | header set by app (ignored on HTTP) | enforced end-to-end |
| CSP | permissive baseline | authoritative policy in the `Caddyfile` |
| Postgres / Redis / Qdrant | internal only (already) | internal only |

## App configuration for production

Set these in the scenario's `.env` (see `edge/core/config.py`):

```bash
VE_ENV=prod                                   # enables strict secret enforcement
VE_JWT_SECRET=<64+ random chars>              # openssl rand -hex 48
VE_SECRETS_KEY=<32+ random chars>             # openssl rand -hex 24
VE_FRONTEND_URL=https://frs.example.com       # correct links in invite/reset mails
VE_CORS_ORIGINS=["https://frs.example.com"]   # lock CORS to the real origin
VE_CORS_ORIGIN_REGEX=                          # clear the permissive dev default
VE_ENCRYPT_MEDIA_PREFIXES=["frs/"]            # biometric media encrypted at rest
VE_APPEARANCE_RETENTION_DAYS=90               # auto-purge sightings after N days
VE_LOCKOUT_MAX_ATTEMPTS=5
VE_PASSWORD_HISTORY_COUNT=5
```

With `VE_ENV=prod`, the app **refuses to start** on default/weak `JWT_SECRET` or
`SECRETS_KEY` (see `_enforce_secrets` in `edge/core/api.py`).

## Data-at-rest (defence in depth)

App-level encryption protects biometric *media* (face crops/enrolment images).
Also encrypt the underlying volumes so the DB and vector store are covered:

- **Disk:** run the host on LUKS full-disk encryption (or a cloud encrypted volume).
- **Postgres / Qdrant:** keep their Docker volumes on that encrypted disk.
- **S3 backend:** enable bucket default encryption (SSE-KMS).

## Retention purge on a schedule

`POST /api/v1/events/purge` enforces `appearance_retention_days` on demand. To run
it nightly, add a cron entry that calls it with a service API key, e.g.:

```cron
30 3 * * *  curl -fsS -X POST https://frs.example.com/api/v1/events/purge \
              -H "X-API-Key: $VIZOR_PURGE_KEY" >/dev/null
```
