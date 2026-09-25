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
| Text PDF | Extracts page text and common survey/gat/CTS, khata and area cues into a reviewable document feature | Scanned PDFs need OCR; the record must be linked to a parcel before it can settle ownership |

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
