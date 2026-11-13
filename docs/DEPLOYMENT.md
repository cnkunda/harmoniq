# Deployment

Backend releases use one immutable image, a one-shot migration step, and a
health gate. This document covers the GHCR artifact, the staging Compose target,
promotion, and rollback.

## Artifact

CI publishes to GitHub Container Registry on every push to `main`/`master` and
on manual `workflow_dispatch` runs:

- `ghcr.io/<owner>/harmoniq-backend:sha-<full commit SHA>` — immutable release tag
- `ghcr.io/<owner>/harmoniq-backend:latest` — updated only on `main`/`master`

Pull requests build the image and run the migration/health checks but do not
publish. The digest is written to the workflow run summary.

If the push is denied, confirm the repository allows workflow write access
(Settings → Actions → General → Workflow permissions) and that the job's
`packages: write` permission is present. New GHCR packages are private by
default; make the package public or authenticate pulls as described below.

## CI pipeline

The `docker-build` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml):

1. Builds `backend/Dockerfile` once and loads it locally (GHA cache).
2. Starts Postgres and Redis from [`docker-compose.yml`](../docker-compose.yml).
3. Runs the one-shot `migrate` service (`alembic upgrade head`).
4. Verifies `alembic current` reports `0001 (head)` and `alembic_version` is set.
5. Tests rollback: `alembic downgrade base` then `alembic upgrade head`.
6. Starts the API and worker, then polls `/health` until it reports
   `"status":"ok"` (HTTP 200 alone is not enough; see limitations).
7. Only after all checks pass, logs in to GHCR and pushes the SHA tag (and
   `latest` on the main branch).

The job runs for main/dispatch pushes and for PRs that change the Dockerfile,
Compose file, dependency lock, Alembic config, or migrations.

## Staging deployment

The repository does not provision infrastructure. Staging is the existing
Compose stack pulling a published image.

```bash
export HARMONIQ_IMAGE=ghcr.io/<owner>/harmoniq-backend:sha-<commit>
docker login ghcr.io -u <github-user>   # PAT with read:packages for private packages

docker compose pull
docker compose up -d --wait postgres redis
docker compose run --rm migrate
docker compose up -d --no-deps --wait api
docker compose up -d --no-deps worker

curl -fsS http://127.0.0.1:8000/health
```

`/health` must return `"status":"ok"`. The worker has no healthcheck; check
`docker compose ps worker` and the worker logs after startup.

Set the environment variables from [`docs/CONFIGURATION.md`](CONFIGURATION.md)
for the target host. Do not use the dev credentials from `docker-compose.yml`
in production.

## Promotion

1. Deploy the candidate SHA tag to staging.
2. Run the health gate and exercise the analysis pipeline.
3. Promote the **same digest** (not a retagged/rebuild) to production:
   `HARMONIQ_IMAGE=ghcr.io/<owner>/harmoniq-backend@sha256:<digest>`.
4. Record the digest and the commit SHA in the release notes.

Because the image is immutable, staging and production run identical bytes.

## Rollback

### Application

Set `HARMONIQ_IMAGE` to the previous `sha-` tag or digest and restart the
services. Do not rebuild.

```bash
export HARMONIQ_IMAGE=ghcr.io/<owner>/harmoniq-backend:sha-<previous>
docker compose pull
docker compose up -d --no-deps --wait api
docker compose up -d --no-deps worker
curl -fsS http://127.0.0.1:8000/health
```

### Database

The API no longer runs migrations on startup; `migrate` is the only writer.

- **Reversible migration:** `docker compose run --rm migrate alembic downgrade -1`
  (or to a specific revision), then redeploy the matching application image.
- **Destructive migration:** restore the database backup or point-in-time
  recovery snapshot. `0001_initial_schema.py` drops all four tables on
  downgrade, so never run `downgrade base` against production data.

CI tests `downgrade base` → `upgrade head` on a disposable database. That proves
the migration scripts are reversible; it does **not** prove production data
survives a downgrade.

## Local development

`docker compose up -d` now starts a one-shot `migrate` service before the API.
If you run the image directly (`docker run`), run migrations first:

```bash
docker compose run --rm migrate
```

## Limitations

- `/health` checks Redis only and returns HTTP 200 when Redis is unreachable
  (`status: "degraded"`). The CI gate parses the JSON body and requires
  `status: "ok"`. Database readiness is proven by the migration step, not by
  the endpoint.
- The worker has no healthcheck, so the gate covers the API only.
- Images are built for the runner's `linux/amd64` platform; multi-arch builds
  are not configured.
- Cloud provisioning and automated production deploys are out of scope; this
  document is the promotion runbook.
