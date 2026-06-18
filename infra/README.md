# Deployment (Phase 14)

Production deployment assets for the NEPSE AI Trading research platform: Docker
images, Docker Compose, Kubernetes manifests, monitoring, and database backups.

## Components

| Path | Purpose |
| ---- | ------- |
| `docker/api.Dockerfile` | Multi-stage, non-root API image with HEALTHCHECK |
| `docker/dashboard.Dockerfile` | Multi-stage, non-root Streamlit image |
| `docker-compose.yml` | Local/staging stack with healthchecks and restart policies |
| `k8s/` | Kubernetes manifests (namespace, config, deployments, backup CronJob) |
| `../scripts/backup_db.sh` | Standalone `pg_dump` backup + retention script |

## Local / staging with Docker Compose

```bash
cp .env.example .env          # fill in real values
docker compose -f infra/docker-compose.yml up --build
```

Services:

- API: <http://localhost:8000> (`/health`, `/health/live`, `/health/ready`, `/metrics`, `/docs`)
- Dashboard: <http://localhost:8501>
- Postgres: `localhost:5432`, Redis: `localhost:6379`, MLflow: <http://localhost:5000>

The API waits for Postgres and Redis to report healthy before starting.

## Kubernetes

```bash
kubectl apply -f infra/k8s/namespace.yaml
# Replace secret placeholders before applying configmap.yaml in a real cluster.
kubectl apply -f infra/k8s/configmap.yaml
kubectl apply -f infra/k8s/api-deployment.yaml
kubectl apply -f infra/k8s/dashboard-deployment.yaml
kubectl apply -f infra/k8s/backup-cronjob.yaml
```

The API Deployment uses:

- **Liveness** probe on `/health/live` (process up).
- **Readiness** probe on `/health/ready` (database reachable) — pods only receive
  traffic once the DB is connectable.
- Rolling updates with zero unavailable replicas.
- Prometheus scrape annotations pointing at `/metrics`.

## Monitoring

The API exposes Prometheus metrics at `/metrics`:

- `http_requests_total{method,endpoint,status}` — request counter.
- `http_request_duration_seconds` — latency histogram.

Scrape with Prometheus using the pod annotations, or point any scraper at
`http://<api-host>/metrics`.

## Backups

- **Kubernetes**: `k8s/backup-cronjob.yaml` runs a daily `pg_dump` (custom format)
  to a PVC and keeps the 14 most recent dumps.
- **Manual / cron**: `scripts/backup_db.sh [BACKUP_DIR] [RETENTION]` reads
  `DATABASE_URL` from the environment or `.env`.

Restore a dump with:

```bash
pg_restore --clean --if-exists --dbname "$DATABASE_URL" path/to/backup.dump
```

## Security notes

- Both images run as a non-root `app` user.
- `.dockerignore` keeps secrets, local DBs, and caches out of the build context.
- `.env`, `infra/docker-compose.override.yml`, and Streamlit secrets are local-only
  and git-ignored; copy `.env.example` to `.env` and fill in real values per machine.
- Never commit real secrets; the Kubernetes `Secret` in `configmap.yaml` ships with
  placeholders only.
