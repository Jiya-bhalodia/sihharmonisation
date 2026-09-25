<<<<<<< HEAD
# BHUMI-X
### AI-Powered Urban Land Record Harmonization Platform

**Problem Statement ID:** 26013 — *Automated Integration and Intelligent Harmonization of
Multi-source Geospatial Data for Urban Land Record Management*
**Organization:** Ministry of Rural Development

---

## 1. Overview

Urban land administration draws on many independently-produced datasets — cadastral maps,
revenue records, municipal GIS layers, GNSS/CORS survey points, ground-truthing data, utility
networks, and drone/orthorectified imagery. These datasets use different coordinate systems,
different schemas, and disagree with each other on geometry, area, and even ownership.

**BHUMI-X** ("Bhoomi" = land, "X" = intelligent integration) automatically ingests these
sources, normalizes their coordinate reference systems, harmonizes their attribute schemas,
spatially matches equivalent real-world features across sources using an **explainable,
weighted GeoAI scoring model**, validates topology, detects spatial and attribute conflicts,
computes multi-dimensional confidence scores, and produces a single **Unified Land Record**
with full source-level provenance (lineage).

> This is described honestly as **explainable GeoAI-assisted spatial harmonization** — a
> transparent, weighted scoring pipeline built on real geometry/attribute computation — not a
> black-box deep-learning system.

## 2. Problem → Solution Mapping

| Requirement | BHUMI-X Implementation |
|---|---|
| Integrate multiple datasets | GeoJSON / CSV / Shapefile ingestion via FastAPI |
| Harmonize spatial data | PyProj-based CRS detection & reprojection |
| Match equivalent features | Weighted GeoAI matcher (proximity, IoU, area, attributes) |
| Map attributes | Fuzzy synonym-based schema mapper with confidence scores |
| Correct topology | Shapely `make_valid`, duplicate/overlap/sliver detection |
| Detect spatial conflicts | Boundary crossings, area mismatches, owner mismatches, etc. |
| Detect changes | Snapshot-diff change detection between harmonization runs |
| Assign confidence scores | Spatial / attribute / geometry / source-agreement per parcel |
| Unified cadastral dataset | `unified_parcels` table + GeoJSON/CSV export |

## 3. Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full Mermaid architecture diagram
and database schema.

**Pipeline flow:**

Multiple Sources → Ingestion → CRS Normalization → Attribute Harmonization
→ AI Spatial Matching → Topology Validation → Conflict Detection
→ Confidence Scoring → Unified Land Record → Change Detection + Reporting



## 4. Tech Stack

**Frontend:** React 18, TypeScript, Vite, Tailwind CSS, React Router, Leaflet + react-leaflet,
Recharts, Lucide React

**Backend:** Python 3.11+, FastAPI, Uvicorn, Pydantic, GeoPandas, Shapely, PyProj,
scikit-learn-compatible weighted scoring, pandas, numpy

**Database:** SQLite (zero-install **Demo Mode**, default) — architecture is fully compatible
with **PostgreSQL + PostGIS** for production by changing two environment variables.

No paid APIs. No proprietary GIS software required.

## Pilot readiness

Before treating a run as a real pilot, use **Pilot Readiness** in
the web app (or `GET /api/pilot/readiness`). It requires an approved common
AOI, authoritative cadastral parcels keyed by CTS/survey/gat number, linked
revenue records, municipal buildings, 10+ GNSS points with accuracy, and a
verified high-resolution (<=20 cm) drone/ORI raster. A passing result is only
ready for departmental review; it is not a legal-title certification.

Put the approved AOI in `data/raw/pilot/aoi.geojson`, retain original sources
in `data/raw/`, and store cleaned derivatives in `data/processed/pilot_area/`.

## 5. Project Structure

bhumix/
├── backend/ FastAPI application, services, GeoAI/ML engines
├── frontend/ React + TypeScript + Vite application
├── data/sample/ Generated synthetic demo datasets
├── data/generated/ Harmonization run snapshots
├── scripts/ Sample data generator
├── docs/ Architecture documentation
└── README.md


## 6. Installation (Manual, No Docker Required)

### Prerequisites
- Python 3.11 or later
- Node.js 18 or later (Node 20 recommended) + npm
- No PostgreSQL required for Demo Mode

### 6.1 Backend Setup

```bash
cd bhumix/backend
python -m venv venv

# Activate the virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
```

> GeoPandas depends on GDAL/GEOS/PROJ system libraries. On most systems `pip install
> geopandas` pulls compatible wheels automatically. If you hit build errors on Linux, install
> system packages first: `sudo apt-get install -y gdal-bin libgdal-dev libgeos-dev libproj-dev`

### 6.2 Generate Synthetic Sample Data

From the **project root** (`bhumix/`):

```bash
python scripts/generate_sample_data.py
```

This writes GeoJSON/CSV files into `data/sample/` — ~230 cadastral parcels, ~200 revenue
records, ~180 municipal buildings, ~60 GNSS points, ~55 ground-truth points, ~40 utility
lines, and a second "drone v2" building snapshot used for the Change Detection demo.

### 6.3 Seed the Database

From `backend/` (with the virtual environment active):

```bash
python run_seed.py
```

This ingests every sample file through the same code path as the API upload endpoint, so the
seeded state is 100% reproducible.

### 6.4 Start the Backend

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger/OpenAPI documentation: **http://localhost:8000/docs**

### 6.5 Frontend Setup

In a new terminal, from `bhumix/frontend`:

```bash
npm install
npm run dev
```

Open **http://localhost:5173**

### 6.6 (Optional) PostgreSQL + PostGIS Setup

To run against PostgreSQL instead of SQLite:

```sql
CREATE DATABASE bhumix;
CREATE USER bhumix WITH PASSWORD 'use-a-strong-secret';
GRANT ALL PRIVILEGES ON DATABASE bhumix TO bhumix;
\c bhumix
CREATE EXTENSION postgis;
```

Then in `backend/.env`:
DEMO_MODE=false
DATABASE_URL=postgresql+psycopg://bhumix:use-a-strong-secret@localhost:5432/bhumix


Restart the backend — table creation and all services work unchanged, since the codebase
already stores/reads geometry as GeoJSON text through SQLAlchemy and Shapely.

For a containerised PostgreSQL/PostGIS baseline, set a strong password, then run:

```bash
export POSTGRES_PASSWORD='replace-with-a-strong-secret'
docker compose -f docker-compose.production.yml up --build
```

## 7. Running the Full Demo Workflow

1. Start backend (`uvicorn app.main:app --reload --port 8000`) and frontend (`npm run dev`).
2. Open the **Dashboard** — see connected sources and (initially empty) statistics.
3. Open **Data Sources** — confirm 6 synthetic departments are listed after seeding.
4. Open **Harmonization** → click **RUN HARMONIZATION** — watch all 9 pipeline stages
   execute against live data.
5. Open **Spatial Matching** — inspect explainable AI match score breakdowns per group.
6. Open **Conflict Resolution** — review detected conflicts (boundary crossings, area
   mismatches, owner mismatches), click one to highlight it on the map, resolve it.
7. Open **Topology Validation** — see per-dataset invalid-geometry counts and corrections.
8. Open **Unified Land Records** — switch between table/map view, click a parcel to see its
   full confidence breakdown and **data lineage** across all contributing sources.
9. To demo **Change Detection**: go to Data Sources → upload
   `data/sample/drone_buildings_v2.geojson` as a new **Municipal** dataset → return to
   Harmonization → **RUN HARMONIZATION** again → open **Change Detection** to see new,
   removed, and modified buildings.
10. Open **Reports** → export the Harmonization, Data Quality, Conflict, and Change reports
    as JSON. Export the Unified Land Record as GeoJSON or CSV from **Unified Land Records**.
11. Open **API / System Status** to show the live Swagger documentation and endpoint list.

## 8. API Documentation

All 17 endpoints are documented interactively at `/docs` (Swagger UI) once the backend is
running. Key endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | System status |
| GET/POST | `/api/datasets`, `/api/datasets/upload` | Dataset management |
| GET | `/api/parcels`, `/api/parcels/{id}` | Unified land records |
| POST/GET | `/api/harmonize`, `/api/harmonize/{job_id}` | Pipeline execution |
| GET | `/api/matches` | AI spatial match results |
| GET/POST | `/api/conflicts`, `/api/conflicts/{id}/resolve` | Conflict workflow |
| GET | `/api/changes` | Change detection events |
| GET | `/api/statistics`, `/api/data-quality` | Aggregate reporting |
| GET | `/api/export/geojson`, `/api/export/csv` | Data export |

## 9. Sample Data

All demo data is **clearly synthetic** and generated by `scripts/generate_sample_data.py`
with a fixed random seed for reproducibility. It intentionally includes the exact
inconsistencies described in the problem statement: mismatched schema field names across
departments, coordinate drift between sources, area disagreements, a few invalid/duplicate/
overlapping geometries, buildings crossing parcel boundaries, displaced GNSS points, and
conflicting owner-name spellings.

## 10. Screenshots

*(Add screenshots of the Dashboard, Harmonization pipeline, Spatial Matching, Conflict
Resolution, and Unified Land Records map here before submission.)*

## 11. Limitations

- Demo Mode uses SQLite and approximate area calculations suitable for a ward-scale synthetic
  dataset; production deployment should use PostgreSQL+PostGIS with proper geodetic area
  functions.
- Shapefile ingestion requires a valid `.shp`/`.shx`/`.dbf` set inside the uploaded ZIP.
- GeoTIFF/DSM/DTM ingestion is not implemented in this prototype (Rasterio is included in
  requirements for future raster-based feature extraction, e.g. drone orthoimagery analysis).
- The spatial matching model uses fixed, tunable weights rather than a trained ML classifier;
  it is intentionally explainable rather than a black box.

## 12. Future Enhancements

- Raster-based building footprint extraction from drone orthoimagery / DSM using Rasterio
- Trainable ML classifier for spatial matching (using resolved conflicts as labeled data)
- PDF report generation
- Role-based access control for department-level data stewardship
- Real-time collaborative conflict resolution
- PostGIS-native spatial indexing for city-scale datasets
=======
# sihharmonisation
>>>>>>> 132e6444c55e993f65c59027ef0272835649dc80
