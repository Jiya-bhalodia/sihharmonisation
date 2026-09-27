# BHUMI-X Render + Netlify staging plan

This document describes a staging deployment only. It does not change the
existing Docker/OCI deployment. Do not use production land records during the
first staging run; use synthetic or otherwise approved test data.

## Services

- **Render web service:** FastAPI, built from `backend/Dockerfile`. Set the
  start command to `sh -c 'uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"'`.
- **Render background worker:** built from the same backend Dockerfile, with
  start command `celery -A app.queue:celery_app worker -Q imagery,harmonization --concurrency=1 --max-tasks-per-child=10 --loglevel=INFO`.
- **Render Postgres:** PostgreSQL 13 or later with PostGIS available. The app
  enables PostGIS and applies its numbered migrations at startup.
- **Redis-compatible queue:** persistent Redis/Key Value for Celery broker and
  result backend. The web service and worker must use the same `REDIS_URL`.
- **External S3-compatible object storage:** private bucket for uploaded source
  files. Configure endpoint and credentials through environment variables.
  For Cloudflare R2, set `AWS_DEFAULT_REGION=auto`; do not put credentials in
  this file or in the repository.
- **Netlify frontend:** base directory `frontend`, build command
  `npm run build`, publish directory `dist`, and build variable `VITE_API_URL`.

Render web services should use the Render-provided `PORT`. The Compose-based
local service continues to use its existing port and command.

## Environment variable names

Set values in the relevant provider's private environment/secret settings.
The worker and web service need the shared backend values. `VITE_API_URL` is a
Netlify build-time variable.

```text
DATABASE_URL
REDIS_URL
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY
OBJECT_STORAGE_SECRET_KEY
AWS_DEFAULT_REGION
DEMO_MODE
AUTH_ENABLED
AUTH_SECRET_KEY
AUTH_TOKEN_TTL_MINUTES
BOOTSTRAP_ADMIN_EMAIL
BOOTSTRAP_ADMIN_PASSWORD
FRONTEND_ORIGIN
VITE_API_URL
DATA_DIR
CHANGE_SNAPSHOT_PATH
MAX_UPLOAD_SIZE_MB
LOGIN_RATE_LIMIT_ATTEMPTS
LOGIN_RATE_LIMIT_IP_ATTEMPTS
LOGIN_RATE_LIMIT_WINDOW_SECONDS
LOAD_SAMPLE_DATA
ENABLE_LOCAL_EMBEDDINGS
BUILDING_EXTRACTION_ENABLED
ENABLE_LOCAL_LLM_CLASSIFICATION
```

For the first hosted staging deployment, set `MAX_UPLOAD_SIZE_MB` to a
conservative value (the application default is 50 MB). Larger geospatial
uploads require more testing. Non-raster uploads are currently parsed in the
API process; direct-to-object-storage/presigned uploads are a future
improvement for very large imagery.

Set `DATA_DIR` to the Render worker's persistent disk mount path. By default,
the change-detection snapshot is stored at
`$DATA_DIR/generated/previous_snapshot.json`. Set `CHANGE_SNAPSHOT_PATH` only
when the snapshot needs a different explicit location. A disk attached to one
worker is suitable only while there is one worker; multiple workers need shared
durable storage or a later snapshot-storage redesign.

Login throttling counts failed attempts in Redis using a fixed 15-minute
window by default: up to five failures for an email/IP pair and 30 failures
from one IP. Further attempts receive HTTP 429 and a `Retry-After` header. A
Redis outage fails login closed with HTTP 503, so keep the queue service
available. The keys contain hashes rather than raw email addresses or IPs.

## Staging order

1. Confirm that the source repository is private and that any included data is
   authorized for hosting. Keep real land/revenue datasets out of staging.
2. Create a staging Postgres database with PostGIS, persistent Redis-compatible
   queue, and a private S3-compatible bucket. Configure backups and recovery
   before loading any valuable data.
3. Deploy the Render worker with `DATA_DIR` on a persistent disk. Keep all
   optional local AI flags disabled.
4. Deploy the Render web service with the same database, Redis, and object
   storage configuration; set its start command to use `$PORT`.
5. Configure Netlify with `VITE_API_URL` and the SPA fallback. Set
   `FRONTEND_ORIGIN` to the exact production Netlify origin.
6. Check `/api/health` for backward-compatible liveness and `/api/ready` for
   Postgres/PostGIS, Redis, and object-storage readiness. Test login throttling,
   uploads at the selected size limit, and one synthetic harmonization job.
7. Exercise backup and restore using disposable staging data, then review logs,
   quotas, and persistent-storage capacity before any broader pilot.

## Data durability and limits

Production requires persistent database, queue, object storage, and snapshot
storage, plus backups whose restore procedure has been tested. Free/ephemeral
services are not appropriate for durable land records. Large geospatial upload
behavior, request limits, memory use, and processing duration still need testing
on the selected staging plans. Do not assume the local Compose 4096 MB upload
setting is suitable for a hosted service.
