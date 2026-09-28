# BHUMI-X hosted evaluation demo

This is a separate, resource-limited staging profile for a short public SIH evaluation. It does not replace or alter the Docker/OCI deployment. The hosted profile keeps the FastAPI API, PostgreSQL/PostGIS, authentication, role checks, vector GIS operations, and Supabase Storage. It omits the Celery worker and local inference models.

## Architecture

```text
Netlify (React/Vite static site, HTTPS)
  └── Render Free (FastAPI Docker web service)
        ├── Supabase Free PostgreSQL + PostGIS
        ├── Upstash Free Redis (login throttling only)
        └── Supabase Storage (private `bhumi-x` originals)
```

MinIO, Celery, worker queues, and the local model cache remain in the normal local/full deployment. In `FREE_DEMO_MODE`, the allowlisted vector harmonization job runs synchronously inside the API under strict limits; no Celery worker is started or required. Raster tasks are disabled and do not invoke Celery.

## Runtime mode and limits

Set `FREE_DEMO_MODE=true`. This profile takes precedence over `DEMO_MODE` for database selection: it uses `DATABASE_URL`, requires `AUTH_ENABLED=true`, and does not turn on the SQLite or unauthenticated local demo behavior. Set `DEMO_MODE=false` explicitly in hosted configuration to make the deployment intent clear.

Defaults are intentionally small for a 512 MB / 0.1 CPU Render Free web instance. They are configurable through environment variables:

| Variable | Default | Effect |
|---|---:|---|
| `FREE_DEMO_ALLOWED_JOB_TYPES` | `vector_harmonization` | Only this allowlisted job type runs synchronously. The implementation will not enable other job types just because they are added to this string. |
| `FREE_DEMO_MAX_UPLOAD_MB` | `2` | Maximum input file size. |
| `FREE_DEMO_MAX_DATASETS` | `20` | Maximum datasets in the hosted workspace. |
| `FREE_DEMO_MAX_FEATURES` | `1000` | Maximum combined feature count and per-run count. |
| `FREE_DEMO_MAX_GEOMETRY_COMPLEXITY` | `25000` | Maximum combined coordinate-position count. |
| `FREE_DEMO_MAX_PROCESSING_SECONDS` | `20` | Cooperative processing budget checked between geometry and pipeline work units. It cannot interrupt one currently-running native GIS operation. |
| Login throttling | `5` per account and `30` per IP in `900` seconds | Redis-backed failed-login limits. |

Only CSV, JSON, and GeoJSON vector uploads are accepted in this profile. Raster files, imagery, archives, PDF/OCR, DINO, SAM, E5, Ollama, and snapshot-based change detection are disabled. Heavy-format uploads receive a clear 422 response; over-limit files/features receive a 413 response. Full deployment behavior remains available when `FREE_DEMO_MODE=false`.

The processing-time limit is cooperative, not an operating-system hard timeout. The small byte, feature, geometry, and dataset caps are the primary resource controls. A timed-out run can have already committed earlier pipeline stages; treat the job as failed, do not present its partial outputs as final, and inspect its stages before retrying.

## Synthetic data and evaluator access

When `FREE_DEMO_MODE=true`, startup automatically seeds a bounded subset of the checked-in `data/sample/` fixtures; `LOAD_SAMPLE_DATA` is not required. Seeding uses stable dataset names and a PostgreSQL advisory lock, so restarts and concurrent startup do not duplicate fixture datasets. The seed does not load `data/raw/`, local SQLite data, or production records. Render packages only the reviewed hosted fixtures, including a bounded synthetic AOI for readiness. Seeded dataset names and backend provenance identify the records as synthetic. The UI labels synthetic sources and resulting records **Synthetic Demo Data** and states that they are not official government records, cadastral data, survey measurements, or SOI CORS observations.

Use only those fixtures or other data that has been confirmed synthetic or cleared for public SIH evaluation. The hosted upload flow requires an explicit operator attestation for each upload; that checkbox does not verify a file’s provenance. Do not use owner-level, restricted revenue, or unapproved government data. There are no public sample/evaluator credentials; an administrator must provision evaluator accounts, and the bootstrap administrator is created only from the backend-only bootstrap settings.

An administrator provisions evaluator accounts; evaluators sign in with the assigned account. Evaluators can view the dashboard, map, records, conflicts, harmonization results, and reports. In free-demo mode, the evaluator role has narrowly scoped access to run the bounded vector harmonization action and accept/reject supported conflict decisions. Owner fields are redacted and owner conflicts are filtered. Evaluators cannot upload/delete data, change mappings, manage accounts, or call privileged export endpoints. These restrictions are enforced by the API; hidden UI controls are not the security boundary.

## Required environment variable names

Set these in provider dashboards only; do not put values in the repository or frontend build environment.

**Render backend**

- `FREE_DEMO_MODE=true`
- `DEMO_MODE=false`
- `AUTH_ENABLED=true`
- `DATABASE_URL`
- `POSTGIS_SCHEMA`
- `AUTH_SECRET_KEY`
- `BOOTSTRAP_ADMIN_EMAIL`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `FRONTEND_ORIGIN`
- `REDIS_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET` (default `bhumi-x`)
- `ENABLE_LOCAL_EMBEDDINGS=false`
- `BUILDING_EXTRACTION_ENABLED=false`
- `ENABLE_LOCAL_LLM_CLASSIFICATION=false`
- Optional limit overrides: `FREE_DEMO_ALLOWED_JOB_TYPES`, `FREE_DEMO_MAX_UPLOAD_MB`, `FREE_DEMO_MAX_DATASETS`, `FREE_DEMO_MAX_FEATURES`, `FREE_DEMO_MAX_GEOMETRY_COMPLEXITY`, `FREE_DEMO_MAX_PROCESSING_SECONDS`

**Netlify frontend build**

- `VITE_API_URL` set to the Render service URL ending in `/api`

`DATABASE_URL`, the Supabase service-role key, Redis URL, and `AUTH_SECRET_KEY` are backend-only. Never use a `VITE_` prefix for credentials.

## Provider configuration and deployment order

1. **Supabase:** create a dedicated staging project. Enable PostGIS in a dedicated schema (for example `extensions` or `gis`) before the backend starts, then set `POSTGIS_SCHEMA` to that exact schema. Copy the shared **session pooler** connection string from Supabase Connect and convert its scheme to `postgresql+psycopg://`; include `sslmode=require`. Render networking is IPv4-only, while Supabase Free direct database connections are IPv6 by default. Session mode uses the IPv4 shared pooler and port 5432. Avoid transaction mode for this app’s persistent SQLAlchemy connection and startup migrations. The application’s PostgreSQL engine adds `public` and the configured extension schema to `search_path`; readiness verifies PostGIS through that schema.
2. **Upstash:** create a Redis database and configure its TLS Redis-protocol URL as `REDIS_URL`. In this hosted profile Redis is required for Redis-backed login throttling only, not as a Celery broker.
3. **Supabase Storage:** create or use a private bucket named `bhumi-x`. Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET` in the Render backend environment. The service-role key is used only server-side for uploads and readiness checks; never publish it in Netlify or expose it to the browser.
4. **Render:** create one Docker web service with the repository root as the build context and `backend/Dockerfile.render` as the Dockerfile. Its Dockerfile-specific ignore file allowlists backend code, migrations, requirements, and only the bounded hosted fixtures consumed by seeding/readiness (`cadastral_parcels`, `revenue_records`, `municipal_buildings`, `ground_truth_points`, `utility_lines`, `gnss_survey_points.csv`, `land_use`, and `hosted_demo_aoi.geojson`). It excludes `data/raw`, local environment files, caches, and model weights. Use this start command so the service binds to Render’s assigned port: `sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"'`. Set `/api/ready` as its health-check path. Startup seeds automatically when `FREE_DEMO_MODE=true`; no temporary `LOAD_SAMPLE_DATA` change is needed. The normal Docker/OCI `backend/Dockerfile` and Compose contexts are unchanged.
5. **Netlify:** set the base directory to `frontend`, build command to `npm ci && npm run build`, publish directory to `dist`, and `VITE_API_URL` to the Render API base. `frontend/public/_redirects` already supplies the React Router fallback. Set Render `FRONTEND_ORIGIN` to the exact published Netlify origin, then test login, map, records, a bounded vector run, and disabled-feature messages.
6. Confirm both `GET /api/health` and `GET /api/ready`. Health reports mode and disabled features without connection details. Readiness verifies Postgres/PostGIS, Redis, and object storage because all three are required for authenticated upload/demo operation. The AOI fixture is synthetic and exists only for bounded demo readiness; the hosted vector workflow does not clip data to it, so it is not production pilot evidence.

The application applies its PostGIS schema migration during startup. Validate startup/migrations, geometry insert/update trigger behavior, geometry queries, and health checks against a disposable Supabase project before SIH use. No live provider integration test has been performed by this repository change.

## Free-tier limitations and operational risks

These are provider limits, not performance guarantees:

- Render Free web services have 0.1 CPU and 512 MB RAM, sleep after 15 minutes idle, and can take about a minute to wake. Their filesystem is ephemeral, and they cannot attach persistent disks. Free services share a workspace allowance of 750 instance hours/month. [Render free limits](https://render.com/docs/free), [compute plans](https://render.com/docs/compute-plans)
- Supabase Free currently lists 500 MB database size and 5 GB egress; exceeding the database quota can force read-only mode. Free projects can pause after a week of low activity. [Supabase billing](https://supabase.com/docs/guides/platform/billing-on-supabase), [database size](https://supabase.com/docs/guides/platform/database-size), [project pausing](https://supabase.com/docs/guides/platform/free-project-pausing)
- Upstash Redis Free currently lists 256 MB data, 10 GB/month bandwidth, and 500,000 commands/month. [Upstash Redis pricing](https://upstash.com/pricing/redis)
- R2 Standard Free currently includes 10 GB-month storage, 1 million Class A operations, 10 million Class B operations, and free egress. [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- Netlify Free currently has 300 monthly credits; sites pause when the allowance is reached. [Netlify pricing](https://www.netlify.com/pricing/)

Provider terms and quotas can change. A free-tier plan may pause, sleep, become read-only, or reject requests during evaluation. Fixture size is intentionally bounded, but this repository does not claim measured Render memory consumption or live Supabase quota usage. A successful deployment is not an availability or performance guarantee.

## Data durability and backups

PostgreSQL rows and Supabase Storage originals are stored outside the Render container. `previous_snapshot.json` is **not** durable in this profile, so hosted Change Detection compares the seeded municipal features with the bundled `drone_buildings_v2.geojson` follow-up fixture. When two municipal source versions are present in PostgreSQL, it compares those persisted versions instead. These vector comparisons are computed by the existing stable-ID/property/geometry comparison logic; the local filesystem snapshot workflow remains disabled in hosted mode.

Before loading demo data, configure an independent backup/export process for Supabase database and Storage objects and test recovery on a disposable project. This repository’s Docker `backup.sh` and `restore.sh` operate on local Compose volumes; they are not a backup mechanism for these hosted providers. Keep the bucket private and retain any desired records until a recovery plan has been checked.

## Rollback

1. Stop public access by unpublishing the Netlify site or disabling the Render web service through provider controls.
2. Preserve the Supabase project and Storage bucket while you inspect logs and decide whether their data must be retained. Do not delete them as part of rollback.
3. Redeploy the last known application revision that was tested against the hosted profile. If returning to full Celery-backed behavior, use the existing Docker/OCI deployment with its worker, Redis broker, and MinIO/S3 configuration; merely switching `FREE_DEMO_MODE` off on Render does not create a worker or persistent disk.
4. Restore only from provider backups that have been independently tested. Never point the hosted service at local SQLite or production storage as a shortcut.
