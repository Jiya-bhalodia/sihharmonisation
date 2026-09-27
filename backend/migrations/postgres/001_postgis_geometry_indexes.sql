ALTER TABLE features ADD COLUMN IF NOT EXISTS geom geometry(Geometry, 4326);
ALTER TABLE unified_parcels ADD COLUMN IF NOT EXISTS geom geometry(Geometry, 4326);

CREATE OR REPLACE FUNCTION bhumix_sync_feature_geom() RETURNS trigger AS $$
BEGIN
  IF NEW.geometry_geojson IS NULL OR NEW.geometry_geojson = '' THEN
    NEW.geom := NULL;
  ELSE
    NEW.geom := ST_SetSRID(ST_GeomFromGeoJSON(NEW.geometry_geojson), 4326);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION bhumix_sync_parcel_geom() RETURNS trigger AS $$
BEGIN
  IF NEW.geometry_geojson IS NULL OR NEW.geometry_geojson = '' THEN
    NEW.geom := NULL;
  ELSE
    NEW.geom := ST_SetSRID(ST_GeomFromGeoJSON(NEW.geometry_geojson), 4326);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS features_geom_sync ON features;
CREATE TRIGGER features_geom_sync BEFORE INSERT OR UPDATE OF geometry_geojson ON features
FOR EACH ROW EXECUTE FUNCTION bhumix_sync_feature_geom();
DROP TRIGGER IF EXISTS parcels_geom_sync ON unified_parcels;
CREATE TRIGGER parcels_geom_sync BEFORE INSERT OR UPDATE OF geometry_geojson ON unified_parcels
FOR EACH ROW EXECUTE FUNCTION bhumix_sync_parcel_geom();

UPDATE features SET geometry_geojson = geometry_geojson WHERE geometry_geojson IS NOT NULL AND geom IS NULL;
UPDATE unified_parcels SET geometry_geojson = geometry_geojson WHERE geometry_geojson IS NOT NULL AND geom IS NULL;
CREATE INDEX IF NOT EXISTS ix_features_geom_gist ON features USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_unified_parcels_geom_gist ON unified_parcels USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_features_dataset_type ON features (dataset_id, canonical_type);
CREATE INDEX IF NOT EXISTS ix_datasets_uploaded_at ON datasets (uploaded_at DESC);
CREATE INDEX IF NOT EXISTS ix_conflicts_status_created ON conflicts (status, created_at DESC);

CREATE OR REPLACE FUNCTION bhumix_reject_audit_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_logs is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;
CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION bhumix_reject_audit_mutation();
