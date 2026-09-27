# Pilot area: data, workflow, and deployment checklist

BHUMI-X is now able to process vector data, KML/KMZ, GeoTIFF/COG rasters,
lat/lon CSVs, and text-based PDF revenue documents. It produces a real
dataset record from every successful upload; it does **not** make up parcel
geometry or ownership when those values are absent.

## 1. Select one defensible area of interest

Start with one ward, village, or a 1–2 km² survey block. Record the AOI
as `data/raw/pilot/aoi.geojson`, using EPSG:4326. Clip every source to this
same boundary before using it for acceptance metrics.

The repository's present raw building data may cover only a subset of the
intended jurisdiction. Treat it as a candidate reference only after it is
verified against the parcel and revenue sources for the selected area.

## 2. Put inputs in this structure

```text
data/raw/pilot/
  cadastral/      parcel polygons: CTS/survey/gat number is mandatory
  revenue/        CSV, GeoJSON or text-based 7/12 PDF
  municipal/      building footprints, address/property layer
  utilities/      authoritative water/sewer/electric layers
  ground_truth/   KML, KMZ, GeoJSON, or GNSS CSV
  imagery/        orthorectified GeoTIFF/COG + metadata
  dsm/            GeoTIFF/COG with CRS, resolution and vertical datum
  dtm/            GeoTIFF/COG with CRS, resolution and vertical datum
```

Keep originals immutable. Write any manually cleaned vector data to
`data/processed/pilot_area/`; do not overwrite a department-supplied file.

## 3. Supported upload behaviour

| Input | What BHUMI-X actually processes | What is still required |
|---|---|---|
| GeoJSON / Shapefile ZIP | Geometry, fields, CRS, quality, matching inputs | Valid source CRS and unique IDs |
| CSV | Converts a configurable latitude/longitude pair into points | For revenue-only tables, a parcel/CTS key is needed for linking |
| KML / KMZ | Reads spatial features and fields into the normal vector pipeline | Verify KML CRS/feature semantics |
| GeoTIFF / COG | Reads CRS, extent, pixel dimensions, band count, pixel size and sampled raster statistics; stores its true footprint | High-resolution drone/ORI is needed for footprint extraction; a 17×17 Sentinel image is only metadata/demo scale |
| PDF | Extracts searchable text and common survey/gat/CTS, khata and area cues. The Docker image also runs local Tesseract OCR on scanned pages (up to the configured page limit) and stores a mean OCR confidence for review. | OCR is not authoritative; verify IDs and area against the source. Scans needing other scripts require the matching Tesseract language pack. A document must be linked to a parcel before it can settle ownership. |

The supplied KML/KMZ and GeoTIFF files can now be uploaded directly. The
existing revenue CSV needs to be uploaded as a revenue source, but it has no
geometry: use its `survey_gat_no` to link it to a cadastral parcel layer.

## 4. Minimum viable pilot dataset

Do not run a final parcel confidence score until this set exists for the same
AOI:

1. **Authoritative cadastral parcels** in GeoJSON or Shapefile, with unique
   CTS/survey/gat IDs. This is the spatial anchor and is currently missing.
2. **Revenue extract** keyed to that same ID. Mask personal data for demos.
3. **Municipal building footprints** with capture date/source.
4. **At least 10–20 GNSS or field verification points** whose accuracy and
   survey date are known.
5. **High-resolution ORI/drone image** (typically 5–20 cm GSD) and, if
   available, DSM/DTM with documented vertical datum.
6. **Authoritative utility layer**; do not describe generic road/OSM layers
   as an underground-utility record.

## 5. First real run

1. Upload the cadastral layer first and select **Cadastral**.
2. Upload all other sources and make the correct source-type choice.
3. In **Data Sources**, check CRS, feature count and quality score.
4. Run **Harmonization**. Corrected topology is retained in the audit table
   and used by later stages; all matches, conflicts and change events come
   from uploaded data.
5. Review low-confidence records and conflicts. Resolve only with a recorded
   departmental decision; never let the app silently overwrite a source.
6. Export GeoJSON/CSV from **Unified Land Records**.

## 6. Production handoff

Before expanding past a pilot, move to PostgreSQL + PostGIS, introduce roles
(Survey, Revenue, Municipal, Reviewer), preserve original files in object
storage with checksums, and add a job queue for large imagery. Use the local
projected CRS appropriate to your jurisdiction for metric operations and
EPSG:4326 only for web/API display.

## 7. Production starter services in this repository

The `docker-compose.production.yml` profile now provides PostgreSQL 16 with
PostGIS 3.4, Redis, MinIO object storage, an imagery worker, and a daily
compressed `pg_dump` retained for 14 days in the Docker volume
`database_backups`. It is a single-host starter: copy database and object
storage backups off-host before relying on it for production recovery.

1. Create `backend/.env.production` from `backend/.env.example` (the local
   production secrets file is ignored by Git).
   Use unique random credentials for Postgres and MinIO, a random
   `AUTH_SECRET_KEY` of at least 32 characters, and a unique bootstrap admin
   password of at least 12 characters. Keep these out of source control.
   The compose database URL expects a URL-safe Postgres password.
   Put the API behind an HTTPS reverse proxy; its container port is bound to
   localhost so bearer credentials are not served directly over public HTTP.
2. Start the stack with
   `docker compose --env-file backend/.env.production -f docker-compose.production.yml up -d --build`.
   The API is available at `http://localhost:8001`; the Vite frontend proxies
   API requests to this port while keeping the demo API on port 8000 untouched.
   For this local review stack, `LOAD_SAMPLE_DATA=true` loads generated synthetic
   datasets and runs harmonization only when the database has no datasets. Keep
   `LOAD_SAMPLE_DATA=false` in any real deployment; sample values are not official records.
   Startup creates the PostGIS extension, SQL tables, tracked SQL migrations,
   spatial geometry columns, GiST indexes and the bootstrap administrator.
3. Sign in through `POST /api/auth/login`. Create departmental accounts with
   `POST /api/auth/users` using the administrator bearer token. Roles are
   `survey_officer`, `revenue_officer`, `municipal_officer`, `reviewer`, and
   `administrator`. Review recorded actions through `GET /api/auth/audit`.

   | Role | Operational access |
   |---|---|
   | Survey officer | Upload cadastral, GNSS, ground-truth, orthoimagery, DSM and DTM data; view records with owner names masked |
   | Revenue officer | Upload revenue data; view owner data; export records |
   | Municipal officer | Upload municipal, utility and drone data; view records with owner names masked |
   | Reviewer | Run harmonization, override mappings, resolve conflicts, view owner data and export |
   | Administrator | All actions, account management and audit-log access |
4. Original uploads are stored in MinIO; large GeoTIFF/COG files above the
   configured 32 MB threshold are queued in Redis for a worker to inspect.
   The production upload limit is 4 GB. Replace MinIO with a managed,
   replicated S3 service for multi-host deployments.
5. Check a restore copy before go-live. The `database_backups` volume is
   local to the Docker host; schedule an encrypted off-host copy. Keep object
   storage backups/versioning aligned with the database recovery point.
6. Run the read-load benchmark against a pre-production copy with realistic
   city-scale data, for example:
   `python scripts/performance/benchmark_api.py --base-url https://staging.example.org --iterations 300 --concurrency 12`.
   Record p50/p95/p99 latency and request failures alongside database size,
   PostGIS version, CPU, memory and worker queue depth. No representative
   city-scale performance result is asserted by this starter configuration.

The migration creates GiST indexes and maintains PostGIS geometry columns
from the application's GeoJSON fields. The harmonization matcher uses the
PostGIS GiST index to retrieve nearby candidates in production; SQLite/demo
deployments use an in-memory spatial tree. Citywide AOI queries should use the indexed PostGIS columns; the current map and
statistics endpoints still need workload-specific pagination and capacity
review before a multi-department rollout.
