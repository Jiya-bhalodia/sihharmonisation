"""
BHUMI-X Synthetic Demo Data Generator
======================================

Generates a realistic-but-SYNTHETIC urban ward dataset across six
"departments", with deliberate real-world messiness baked in:

  - Cadastral (Survey Dept)   : ~220 parcels, field names: parcel_id, owner, area_sq_m, land_use
  - Revenue (Revenue Dept)    : ~200 records, field names: survey_no, landholder, area, classification
  - Municipal (Municipal Corp): ~180 buildings, field names: property_id, owner_name, plot_area, usage_type
  - GNSS (Ground Survey Team) : ~60 points, slightly displaced from true parcel centroids
  - Ground Truth (Field Team) : ~55 verification points
  - Utility (Utility Dept)    : ~40 line features (water/power) that sometimes cross parcel boundaries
  - Drone-derived buildings (v2 "after" snapshot) for change detection demo

Fixed after senior review: previously EVERY generated dataset was already
in EPSG:4326, so the "CRS Normalization" pipeline stage had nothing real
to demonstrate. The Municipal Buildings dataset is now generated in
EPSG:32643 (UTM Zone 43N) and shipped with an explicit "crs_hint", so
uploading/seeding it triggers a genuine, visible coordinate
transformation back to EPSG:4326.

Requires pyproj (already a backend dependency) -- run this script using
the same Python environment / virtualenv as the backend.

Run:
    cd bhumix
    python scripts/generate_sample_data.py

Output written to: data/sample/*.geojson and *.csv
All data is clearly synthetic and does not represent any real place,
department, or individual.
"""
import json
import os
import random
import csv

from pyproj import Transformer

random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sample")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# A fictional ward centered near a plausible Indian urban coordinate.
BASE_LAT = 16.7050
BASE_LON = 74.2433

GRID_COLS = 16
GRID_ROWS = 14
CELL_SIZE_DEG = 0.00075  # roughly ~80m per cell at this latitude

LAND_USES = ["Residential", "Commercial", "Mixed Use", "Institutional", "Vacant"]
FIRST_NAMES = ["Ramesh", "Sita", "Anil", "Kavita", "Suresh", "Meena", "Vijay", "Priya",
               "Ganesh", "Lata", "Ashok", "Rekha", "Sunil", "Nirmala", "Prakash", "Sunita",
               "Deepak", "Anita", "Manoj", "Shobha"]
LAST_NAMES = ["Patil", "Kulkarni", "Deshmukh", "Joshi", "Shinde", "Pawar", "Chavan",
              "Jadhav", "More", "Bhosale", "Gaikwad", "Kadam"]

# Live CRS transform used to demonstrate real CRS normalization: the
# Municipal Buildings dataset is written in UTM 43N, then reprojected to
# WGS84 on ingestion by the backend's CRS normalization stage.
_WGS84_TO_UTM43N = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def rand_owner():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def jitter(value, magnitude):
    return value + random.uniform(-magnitude, magnitude)


def cell_bounds(row, col):
    lat0 = BASE_LAT + row * CELL_SIZE_DEG
    lon0 = BASE_LON + col * CELL_SIZE_DEG
    lat1 = lat0 + CELL_SIZE_DEG
    lon1 = lon0 + CELL_SIZE_DEG
    return lat0, lon0, lat1, lon1


def make_parcel_polygon(row, col, shrink=0.0, shift_lat=0.0, shift_lon=0.0):
    lat0, lon0, lat1, lon1 = cell_bounds(row, col)
    pad_lat = CELL_SIZE_DEG * (0.08 + shrink)
    pad_lon = CELL_SIZE_DEG * (0.08 + shrink)
    lat0, lat1 = lat0 + pad_lat, lat1 - pad_lat
    lon0, lon1 = lon0 + pad_lon, lon1 - pad_lon

    corner_nudge = CELL_SIZE_DEG * 0.05 * random.random()

    coords = [
        (lon0 + shift_lon, lat0 + shift_lat),
        (lon1 + shift_lon, lat0 + shift_lat),
        (lon1 + shift_lon, lat1 - corner_nudge + shift_lat),
        (lon0 + corner_nudge + shift_lon, lat1 + shift_lat),
        (lon0 + shift_lon, lat0 + shift_lat),
    ]
    return {"type": "Polygon", "coordinates": [coords]}


def make_small_building_polygon(row, col, offset_frac=0.25, size_frac=0.35, shift_lat=0.0, shift_lon=0.0):
    lat0, lon0, lat1, lon1 = cell_bounds(row, col)
    span_lat = (lat1 - lat0)
    span_lon = (lon1 - lon0)
    blat0 = lat0 + span_lat * offset_frac + shift_lat
    blon0 = lon0 + span_lon * offset_frac + shift_lon
    blat1 = blat0 + span_lat * size_frac
    blon1 = blon0 + span_lon * size_frac
    coords = [
        (blon0, blat0), (blon1, blat0), (blon1, blat1), (blon0, blat1), (blon0, blat0)
    ]
    return {"type": "Polygon", "coordinates": [coords]}


def polygon_centroid(polygon_geom):
    coords = polygon_geom["coordinates"][0][:-1]
    lon = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return lat, lon


def approx_area_sqm(polygon_geom):
    coords = polygon_geom["coordinates"][0]
    area_deg2 = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        area_deg2 += x1 * y2 - x2 * y1
    area_deg2 = abs(area_deg2) / 2.0
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * 0.958  # cos(~16.7 deg)
    return area_deg2 * m_per_deg_lat * m_per_deg_lon


def to_utm43n_feature(feature):
    """Reproject a Polygon feature's coordinates from WGS84 to EPSG:32643,
    used only for the Municipal Buildings dataset to demonstrate a real
    CRS transformation during harmonization."""
    ring = feature["geometry"]["coordinates"][0]
    utm_ring = [list(_WGS84_TO_UTM43N.transform(lon, lat)) for lon, lat in ring]
    feature["geometry"]["coordinates"] = [utm_ring]
    return feature


def write_geojson(filename, features, extra_props=None):
    path = os.path.join(OUTPUT_DIR, filename)
    payload = {"type": "FeatureCollection", "features": features, **(extra_props or {})}
    with open(path, "w") as f:
        json.dump(payload, f, indent=None)
    print(f"Wrote {len(features)} features -> {path}" + (f"  [{extra_props}]" if extra_props else ""))


def write_csv(filename, rows, fieldnames):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {len(rows)} rows -> {path}")


def main():
    cadastral_features = []
    revenue_features = []
    municipal_features = []
    gnss_rows = []
    ground_truth_features = []
    utility_features = []

    parcel_registry = []

    grid_cells = [(r, c) for r in range(1, GRID_ROWS - 1) for c in range(1, GRID_COLS - 1)]
    random.shuffle(grid_cells)
    selected_cells = grid_cells[:230]

    survey_counter = 100
    for idx, (row, col) in enumerate(selected_cells):
        survey_counter += 1
        parcel_id = f"P-{survey_counter:04d}"
        owner = rand_owner()
        land_use = random.choice(LAND_USES)
        has_building = random.random() < 0.75
        building_count = random.choice([0, 1, 1, 1, 2, 3]) if has_building else 0

        cad_geom = make_parcel_polygon(row, col, shrink=0.0)
        cad_area = round(approx_area_sqm(cad_geom), 1)
        cadastral_features.append({
            "type": "Feature",
            "geometry": cad_geom,
            "properties": {
                "parcel_id": parcel_id,
                "owner": owner,
                "area_sq_m": cad_area,
                "land_use": land_use,
                "ward": "Ward-07",
            },
        })

        rev_geom = make_parcel_polygon(row, col, shrink=random.uniform(0.0, 0.6),
                                        shift_lat=random.uniform(-0.00003, 0.00003),
                                        shift_lon=random.uniform(-0.00003, 0.00003))
        rev_area = round(cad_area * random.uniform(0.92, 1.08), 1)
        rev_owner = owner if random.random() > 0.12 else _mutate_name(owner)
        revenue_features.append({
            "type": "Feature",
            "geometry": rev_geom,
            "properties": {
                "survey_no": parcel_id,
                "landholder": rev_owner,
                "area": rev_area,
                "classification": land_use if random.random() > 0.1 else random.choice(LAND_USES),
                "khasra_no": f"KH-{survey_counter:04d}",
            },
        })

        for b in range(building_count):
            offset_frac = 0.15 + b * 0.30
            if offset_frac > 0.55:
                offset_frac = 0.55
            crosses = random.random() < 0.12
            shift_lat = CELL_SIZE_DEG * 0.35 if crosses else 0.0
            bldg_geom = make_small_building_polygon(row, col, offset_frac=offset_frac, size_frac=0.3,
                                                      shift_lat=shift_lat)
            municipal_features.append({
                "type": "Feature",
                "geometry": bldg_geom,
                "properties": {
                    "property_id": f"B-{survey_counter:04d}-{b+1}",
                    "owner_name": owner if random.random() > 0.15 else _mutate_name(owner),
                    "plot_area": round(approx_area_sqm(bldg_geom), 1),
                    "usage_type": land_use,
                    "linked_parcel": parcel_id,
                },
            })

        if random.random() < 0.27:
            true_lat, true_lon = polygon_centroid(cad_geom)
            disp_lat = jitter(true_lat, CELL_SIZE_DEG * 0.12)
            disp_lon = jitter(true_lon, CELL_SIZE_DEG * 0.12)
            if random.random() < 0.08:
                disp_lat = jitter(true_lat, CELL_SIZE_DEG * 3.0)
                disp_lon = jitter(true_lon, CELL_SIZE_DEG * 3.0)
            gnss_rows.append({
                "point_id": f"G-{survey_counter:04d}",
                "latitude": round(disp_lat, 7),
                "longitude": round(disp_lon, 7),
                "linked_parcel_id": parcel_id,
                "surveyor": random.choice(["Team A", "Team B", "Team C"]),
                "accuracy_m": round(random.uniform(0.3, 2.5), 2),
            })

        if random.random() < 0.24:
            true_lat, true_lon = polygon_centroid(cad_geom)
            ground_truth_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [jitter(true_lon, CELL_SIZE_DEG * 0.05),
                                                                jitter(true_lat, CELL_SIZE_DEG * 0.05)]},
                "properties": {
                    "gt_id": f"GT-{survey_counter:04d}",
                    "parcel_id": parcel_id,
                    "field_verified": True,
                    "verification_date": "2026-02-14",
                    "notes": random.choice(["Boundary confirmed", "Structure matches records",
                                             "Minor discrepancy noted", "Verified via local witness"]),
                },
            })

        parcel_registry.append({
            "row": row, "col": col, "parcel_id": parcel_id, "owner": owner,
            "land_use": land_use, "building_count": building_count, "cad_area": cad_area,
        })

    # --- INTENTIONALLY INVALID / DUPLICATE / OVERLAPPING GEOMETRIES for topology testing ---
    bad_row, bad_col = 3, 3
    self_intersecting = {
        "type": "Polygon",
        "coordinates": [[
            (BASE_LON + bad_col * CELL_SIZE_DEG, BASE_LAT + bad_row * CELL_SIZE_DEG),
            (BASE_LON + (bad_col + 1) * CELL_SIZE_DEG, BASE_LAT + (bad_row + 1) * CELL_SIZE_DEG),
            (BASE_LON + (bad_col + 1) * CELL_SIZE_DEG, BASE_LAT + bad_row * CELL_SIZE_DEG),
            (BASE_LON + bad_col * CELL_SIZE_DEG, BASE_LAT + (bad_row + 1) * CELL_SIZE_DEG),
            (BASE_LON + bad_col * CELL_SIZE_DEG, BASE_LAT + bad_row * CELL_SIZE_DEG),
        ]],
    }
    cadastral_features.append({
        "type": "Feature",
        "geometry": self_intersecting,
        "properties": {"parcel_id": "P-9001", "owner": "Bowtie Test Parcel", "area_sq_m": 4200.0,
                        "land_use": "Vacant", "ward": "Ward-07"},
    })

    dup_source = cadastral_features[5]
    dup_feature = json.loads(json.dumps(dup_source))
    dup_feature["properties"] = dict(dup_feature["properties"])
    dup_feature["properties"]["parcel_id"] = "P-9002"
    dup_feature["properties"]["owner"] = "Duplicate Test Entry"
    cadastral_features.append(dup_feature)

    overlap_row, overlap_col = 6, 9
    overlap_geom_a = make_parcel_polygon(overlap_row, overlap_col, shrink=0.0)
    overlap_geom_b = make_parcel_polygon(overlap_row, overlap_col, shrink=0.0,
                                          shift_lat=CELL_SIZE_DEG * 0.25, shift_lon=CELL_SIZE_DEG * 0.15)
    cadastral_features.append({"type": "Feature", "geometry": overlap_geom_a,
                                "properties": {"parcel_id": "P-9003", "owner": "Overlap Test A",
                                                "area_sq_m": round(approx_area_sqm(overlap_geom_a), 1),
                                                "land_use": "Residential", "ward": "Ward-07"}})
    cadastral_features.append({"type": "Feature", "geometry": overlap_geom_b,
                                "properties": {"parcel_id": "P-9004", "owner": "Overlap Test B",
                                                "area_sq_m": round(approx_area_sqm(overlap_geom_b), 1),
                                                "land_use": "Residential", "ward": "Ward-07"}})

    # --- UTILITY LINES ---
    for i in range(42):
        row = random.randint(1, GRID_ROWS - 2)
        col_start = random.randint(1, GRID_COLS - 3)
        lat0, lon0, lat1, lon1 = cell_bounds(row, col_start)
        length_cells = random.choice([1, 2, 3])
        end_lon = lon0 + length_cells * CELL_SIZE_DEG
        mid_lat = (lat0 + lat1) / 2 + random.uniform(-CELL_SIZE_DEG * 0.2, CELL_SIZE_DEG * 0.2)
        utility_type = random.choice(["water_main", "power_line", "sewer_line"])
        utility_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[lon0, mid_lat], [end_lon, mid_lat]]},
            "properties": {
                "utility_id": f"U-{i+1:03d}",
                "utility_type": utility_type,
                "department": "Utility Department",
                "install_year": random.randint(1998, 2023),
            },
        })

    # --- DRONE-DERIVED "AFTER" SNAPSHOT for Change Detection demo (kept in WGS84,
    #     copied BEFORE the municipal dataset is reprojected to UTM below) ---
    drone_after_features = [json.loads(json.dumps(f)) for f in municipal_features]
    for _ in range(2):
        if drone_after_features:
            drone_after_features.pop(random.randrange(len(drone_after_features)))
    for i in random.sample(range(len(drone_after_features)), min(2, len(drone_after_features))):
        feat = drone_after_features[i]
        coords = feat["geometry"]["coordinates"][0]
        new_coords = [[x + CELL_SIZE_DEG * 0.02, y + CELL_SIZE_DEG * 0.02] for x, y in coords]
        feat["geometry"]["coordinates"] = [new_coords]
        feat["properties"]["usage_type"] = "Commercial"
        feat["properties"]["property_id"] = feat["properties"]["property_id"] + "-EXT"
    vacant_cells = [p for p in parcel_registry if p["building_count"] == 0][:3]
    for i, p in enumerate(vacant_cells):
        new_geom = make_small_building_polygon(p["row"], p["col"], offset_frac=0.3, size_frac=0.3)
        drone_after_features.append({
            "type": "Feature",
            "geometry": new_geom,
            "properties": {
                "property_id": f"B-NEW-{i+1:03d}",
                "owner_name": p["owner"],
                "plot_area": round(approx_area_sqm(new_geom), 1),
                "usage_type": "Residential",
                "linked_parcel": p["parcel_id"],
            },
        })

    write_geojson("cadastral_parcels.geojson", cadastral_features)
    write_geojson("revenue_records.geojson", revenue_features)

    # Reproject the Municipal Buildings dataset to EPSG:32643 so the
    # backend's CRS Normalization stage has a real transformation to
    # perform and display, not just a no-op.
    utm_municipal_features = [to_utm43n_feature(json.loads(json.dumps(f))) for f in municipal_features]
    write_geojson("municipal_buildings.geojson", utm_municipal_features, extra_props={"crs_hint": "EPSG:32643"})

    write_geojson("ground_truth_points.geojson", ground_truth_features)
    write_geojson("utility_lines.geojson", utility_features)
    write_geojson("drone_buildings_v2.geojson", drone_after_features)
    write_csv("gnss_survey_points.csv", gnss_rows,
              fieldnames=["point_id", "latitude", "longitude", "linked_parcel_id", "surveyor", "accuracy_m"])

    print("\nSample data generation complete.")
    print(f"  Cadastral parcels : {len(cadastral_features)}  (EPSG:4326)")
    print(f"  Revenue records   : {len(revenue_features)}  (EPSG:4326)")
    print(f"  Municipal bldgs   : {len(municipal_features)}  (EPSG:32643 -- demonstrates live CRS transform)")
    print(f"  GNSS points       : {len(gnss_rows)}  (EPSG:4326)")
    print(f"  Ground truth pts  : {len(ground_truth_features)}  (EPSG:4326)")
    print(f"  Utility lines     : {len(utility_features)}  (EPSG:4326)")
    print(f"  Drone v2 buildings: {len(drone_after_features)}  (EPSG:4326)")
    print("\nAll data is SYNTHETIC DEMO DATA and does not represent any real place or person.")


def _mutate_name(name):
    variations = [
        lambda n: n.replace("a", "aa", 1) if "a" in n else n + " ",
        lambda n: n.upper(),
        lambda n: n.split()[0] if " " in n else n,
        lambda n: n + " Sr.",
    ]
    return random.choice(variations)(name)


if __name__ == "__main__":
    main()