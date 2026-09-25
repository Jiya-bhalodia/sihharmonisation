# Pilot input area

Place the approved `aoi.geojson` here in EPSG:4326 before calling the pilot
ready. Keep it small (one ward, village, or 1–2 km² survey block) and clip all
departmental sources to it. Do not derive this boundary from an unverified
building, revenue, or utility layer.

Original agency files stay immutable in `data/raw/`. Put cleaned, clipped
derivatives in `data/processed/pilot_area/` with a short provenance note.
