# BHUMI-X deployment on Oracle Cloud Infrastructure

This deployment uses one Oracle Cloud Infrastructure (OCI) Ampere A1 ARM64 VM. The Always Free Ampere A1 allowance for an Always Free tenancy is **2 OCPUs and 12 GB RAM total**, not 4 OCPUs / 24 GB. The deployment guidance below stays within 2 OCPUs / 12 GB. [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

The stack serves the React application through an HTTP-only Nginx edge. PostgreSQL/PostGIS, Redis, MinIO, backend, worker, and the frontend static server are internal to Compose. The edge uses Docker DNS resolution so recreated backend/frontend containers are followed without restarting Nginx. TLS is not configured in the current Nginx file.

## Resource planning estimates

These are planning estimates, not measured benchmarks or performance guarantees.

| Profile | VM budget | Expected use |
|---|---:|---|
| Core | 2 OCPU / 12 GB RAM | AI dependencies and local AI features off; recommended initial free-tier setup. Upload throughput and GIS processing are modest. |
| Core + multilingual E5 | 2 OCPU / 12 GB RAM | CPU-only embeddings; limited concurrent throughput. Enable only after core is verified and E5 weights have been downloaded to the model volume. |
| Grounding DINO / SAM / Ollama | Not recommended on the free 2 OCPU / 12 GB VM | Image detection/segmentation and local LLM workloads compete with PostGIS and raster processing for CPU and memory. Use a larger paid VM or keep these disabled. |

Use at least a 100 GB boot volume as an initial planning target for the OS, images, database, uploads, and backups; actual need depends on imagery and retention. Oracle's included block volume capacity is shared across all boot and block volumes, so verify the current console allocation before provisioning.

## Image architecture review

On 2026-09-27, the exact registry manifests for all production image tags were inspected with Docker Buildx; each image in the Compose stack includes `linux/arm64` (the locally built backend, worker, and frontend images also resolved to `linux/arm64`). The official `postgis/postgis:16-3.4` tag was inspected separately and its single manifest declares `linux/amd64` only. The retained SOGIS replacement is the same PostgreSQL 16 / PostGIS 3.4 line and its exact tag includes both `linux/amd64` and `linux/arm64`.

| Service | Exact image/tag | linux/arm64 | Basis |
|---|---|---:|---|
| Database and backup client | `sogis/postgis:16-3.4` | Yes | The tag listing shows both `linux/amd64` and `linux/arm64`: [SOGIS tags](https://hub.docker.com/r/sogis/postgis/tags). |
| Official PostGIS candidate | `postgis/postgis:16-3.4` | **No** | The official image's published supported architecture is AMD64; it does not provide the required ARM64 image: [official PostGIS image](https://hub.docker.com/r/postgis/postgis/). This is why the Compose file retains the alternative; it is not an assumption based on Docker generally supporting ARM. |
| Redis | `redis:7.4-alpine` | Yes | Official image supports `arm64v8`; the tag family is listed here: [Redis tags](https://hub.docker.com/_/redis/tags?name=7.4-alpine). |
| MinIO | `ghcr.io/golithus/minio:RELEASE.2025-10-15T17-29-55Z` | Yes | The publisher's release lists the exact tag as a multi-architecture image and includes a Linux ARM64 binary: [MinIO release](https://github.com/golithus/minio-builds/releases/tag/RELEASE.2025-10-15T17-29-55Z). |
| MinIO client / object-store init | `ghcr.io/golithus/mc:RELEASE.2025-08-13T08-35-41Z` | Yes | The publisher's release lists the exact tag as multi-architecture and includes an ARM64 binary: [`mc` release](https://github.com/golithus/minio-builds/releases/tag/mc-RELEASE.2025-08-13T08-35-41Z). |
| Backend and worker base | `python:3.12-slim` | Yes | The exact official Python tag includes `linux/arm64/v8`: [Python tag listing](https://hub.docker.com/_/python/tags?name=3.12-slim). The two services are built from this base. |
| Frontend build stage | `node:22-alpine` | Yes | The official tag listing includes ARM64 for the `22-alpine` tags: [official Node image definitions](https://github.com/docker-library/official-images/blob/master/library/node). |
| Frontend static server and edge proxy | `nginx:alpine` | Yes | The official image definitions list ARM64 for the `alpine` tag: [official Nginx image definitions](https://github.com/docker-library/official-images/blob/master/library/nginx). |

The `sogis/postgis:16-3.4` alternative is third-party and its exact 3.4 tag is older than the official image line. Review its provenance and lifecycle before a long-lived production deployment. It preserves the PostgreSQL/PostGIS major-minor line and is the available ARM64-compatible tag verified here. No database volume is deleted or migrated by these instructions.

## 1. Create the VM and network rules

1. In OCI, create an **Ubuntu 22.04 ARM64 / AArch64** VM using the Ampere A1 shape. Allocate no more than the Always Free total of 2 OCPUs and 12 GB RAM.
2. Assign a public IPv4 address. In the VCN security list or network security group, allow TCP 22 from your administrative IP and TCP 80 for the initial HTTP-only site. Keep TCP 5432, 6379, 9000, 9001, 8000, 8001, and 5173 closed. Open TCP 443 only when HTTPS has actually been configured.
3. SSH to the VM.

The single-VM design is a small deployment target, not high availability. Keep off-VM backups and monitor available disk space.

## 2. Install Docker Engine and Compose

Run on the Ubuntu VM:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run --rm hello-world
sudo docker compose version
```

## 3. Get the project and configure secrets

```bash
git clone https://github.com/Jiya-bhalodia/sihharmonisation.git bhumi-x
cd bhumi-x
cp backend/.env.example backend/.env.production
nano backend/.env.production
```

Set `DEMO_MODE=false`, a URL-safe `POSTGRES_PASSWORD`, a random `AUTH_SECRET_KEY` of at least 32 bytes, a bootstrap admin email and unique password, unique MinIO access/secret keys, and `FRONTEND_ORIGIN` to the site's origin. `openssl rand -hex 32` is suitable for random secrets. Keep `backend/.env.production` private; do not commit it. Do not change production secrets as part of this review.

For the initial **core** deployment, set all three flags to false in `backend/.env.production`:

```dotenv
ENABLE_LOCAL_EMBEDDINGS=false
BUILDING_EXTRACTION_ENABLED=false
ENABLE_LOCAL_LLM_CLASSIFICATION=false
```

## 4. Deploy the core profile first

The core profile includes PostgreSQL/PostGIS, Redis, MinIO, backend, worker, frontend, and Nginx. It sets `INSTALL_LOCAL_AI=false`, so the worker skips the optional PyTorch/Transformers/Sentence-Transformers dependency layer. No model weights are downloaded.

From the repository root:

```bash
sudo ./deploy.sh
sudo docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.core.yml ps
```

Check container health and the application at `http://<VM_PUBLIC_IP>/`. Check `http://<VM_PUBLIC_IP>/api/health` and `http://<VM_PUBLIC_IP>/healthz`. The current Nginx configuration is HTTP-only.

## 5. Add multilingual E5 only after core verification

First verify the core UI, API, database, uploads, and worker. Then change `ENABLE_LOCAL_EMBEDDINGS=true` in `backend/.env.production`; keep DINO and local LLM flags false unless separately planned. Build and start the AI-enabled backend/worker override:

```bash
sudo docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.ai.yml \
  up -d --build backend worker
```

This separate profile sets `INSTALL_LOCAL_AI=true` for backend and worker, which is needed because E5 matching runs in the backend harmonization path. It installs CPU-only dependencies; it does not download model weights. Download E5 separately into the persistent local model cache:

```bash
sudo docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.ai.yml \
  run --rm --no-deps --build worker hf download intfloat/multilingual-e5-small
```

After the checkpoint is present, recreate backend and worker with the AI override. On this 2 OCPU VM, embeddings are CPU inference with limited throughput. Do not enable E5 before verifying the core deployment.

## 6. HTTPS is a future manual change

HTTPS is **not implemented** by the current Nginx configuration. It has no TLS listener, certificate mounts, or port 443 publication, and it does not set HSTS.

To add HTTPS later, after choosing a domain and certificate issuer:

1. Point the domain to the VM and allow inbound TCP 443 in OCI.
2. Obtain a real certificate and private key for that domain.
3. Add a `listen 443 ssl` Nginx server block that references the actual issued certificate/key paths, and add an HTTP-to-HTTPS redirect on port 80.
4. Mount the real certificate directory read-only into the Nginx service and publish host port 443 to container port 443.
5. Recreate Nginx, verify the certificate/chain and HTTPS app/API routes, then consider enabling HSTS.

No placeholder certificates or paths are included in this repository.

## 7. Backups and restores

`backup.sh` makes a consistent local archive of the PostgreSQL database, the shared `DATA_DIR` volume, and the complete MinIO data volume (including object version metadata). It briefly stops backend/worker writes and MinIO while taking volume archives, then restarts them. It writes into `BACKUP_DIR` if set, otherwise `<repo>/backups`; that directory is Git-ignored.

```bash
sudo BACKUP_DIR=/var/backups/bhumix ./backup.sh
```

Both backup scripts use `backend/.env.production` by default. For a local or staging Compose stack, set `COMPOSE_ENV_FILE` to that stack's env file and `COMPOSE_PROJECT_NAME` to its Compose project name. This lets you validate recovery with isolated credentials and volumes without reading or changing production settings.

PostgreSQL credentials are passed to the backup service as `PGPASSWORD` from Compose's `POSTGRES_PASSWORD`. The MinIO archive is made from its stopped Docker volume, so MinIO credentials are not used for this operation. The archive includes raw MinIO volume data and must be restored with the same MinIO image release. Keep backup copies off the VM.

`restore.sh` requires an explicit `--confirm`, first creates a rollback backup, stops writers and MinIO, applies the PostgreSQL archive with `pg_restore --clean`, extracts the MinIO and DATA_DIR archives over their named volumes, then restarts services. This is an overlay restore: it does not prune database objects, MinIO objects, or DATA_DIR files that are absent from the selected archive.

```bash
sudo ./restore.sh /var/backups/bhumix/<UTC_TIMESTAMP> --confirm
```

Local disposable-stack validation passed for PostgreSQL, `DATA_DIR`, and MinIO: the saved DB row, snapshot file, and object contents were restored. The test also confirmed the restore is **overlay-style**, not an exact replacement: a DB table created after the backup and extra MinIO/`DATA_DIR` files remained. `pg_restore --clean` replaces objects represented in the dump but does not remove every newer, unrepresented database object. These checks do not establish production backup durability or off-VM recovery. Before relying on this in production, test on a disposable staging deployment and copy archives off the VM.

## 8. Persistence and operations

Named volumes retain PostgreSQL, Redis, MinIO, local model cache, and `/data` change-detection snapshots across container recreation. Do not run `docker compose down -v` on a deployment. To inspect logs:

```bash
sudo docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.core.yml \
  logs -f backend worker nginx
```

## Remaining manual tasks before production

- Confirm the Oracle tenancy console's current Always Free quota and VM allocation.
- Review the third-party SOGIS image provenance/maintenance and the pinned MinIO community image publisher before storing production records.
- Test the core stack end to end on a disposable VM, then validate backup/restore there.
- Arrange off-VM backup storage and a retention policy.
- Configure HTTPS with a real domain/certificate before handling credentials or sensitive data over the public network.
- Review and rotate deployment secrets on the VM; no production secret was edited here.
