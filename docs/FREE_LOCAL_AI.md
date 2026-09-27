# Free, local-first AI/GIS setup

BHUMI-X can run the OCR, text embedding, and image inference paths on the
machine running its backend/worker. The application does not call a paid
inference API. Open model weights are downloaded once from their public model
repositories and then loaded from a local cache. Initial downloads need an
internet connection; inference can run offline after the weights are cached.
Compute, disk, and electricity still come from the machine you run it on.

## What is wired in

- **Searchable PDFs:** extract the embedded PDF text locally with `pypdf`.
- **Scanned PDFs:** use Tesseract OCR through Poppler, up to `OCR_MAX_PAGES`.
  English, Hindi, and Marathi language packs are included in the project Docker
  image. OCR text is retained as reviewable source data, with a mean confidence
  value; it does not silently decide ownership.
- **Building footprints:** optional Grounding DINO text-prompt detection plus
  SAM mask segmentation. Runs tile-by-tile on local CPU by default, or on CUDA
  / Apple MPS when PyTorch detects the device. Detections are stored as
  `building` features with the score and `needs_review=true`.
- **Text embeddings:** optional multilingual E5 embeddings complement fuzzy
  matching for owner names, land-use labels, and addresses. Parcel/survey
  identifiers continue to use string comparison rather than semantic vectors.
- **Spatial operations:** PostGIS is the production spatial database and has
  GiST indexes for matching candidates; deterministic topology checks/corrections remain GIS rules.
- **Dataset type suggestions:** local metadata rules inspect the dataset name,
  filename, and field names. Ambiguous suggestions require a manual selection.
  An optional Ollama tie-breaker can run locally and sees metadata only.

The pretrained weights are published as Apache-2.0 for [Grounding DINO
Tiny](https://huggingface.co/IDEA-Research/grounding-dino-tiny) and [SAM ViT
Base](https://huggingface.co/facebook/sam-vit-base), and MIT for [multilingual
E5 small](https://huggingface.co/intfloat/multilingual-e5-small). Review each
upstream model card and license before redistributing a deployment.

## Add local models after the core deployment is verified

Start by deploying and verifying the core profile from `README_DEPLOY.md`. The
core worker intentionally omits PyTorch, Transformers, and Sentence-Transformers.
When you are ready to add local inference, use the AI Compose override so the
worker and backend get the optional CPU-only Python dependency layer:

```sh
docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.ai.yml \
  run --rm --no-deps --build worker hf download intfloat/multilingual-e5-small
docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.ai.yml \
  run --rm --no-deps --build worker hf download IDEA-Research/grounding-dino-tiny
docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.ai.yml \
  run --rm --no-deps --build worker hf download facebook/sam-vit-base
```

These are separate public model downloads, not API inference calls. The model
cache is stored in the persistent `local_model_cache` volume mounted at
`/models`. Model weights are not downloaded during Docker image builds.

For E5, set `ENABLE_LOCAL_EMBEDDINGS=true` in `backend/.env.production` after
the core deployment has passed its checks. Keep DINO/SAM and Ollama disabled
unless you intentionally provision them. Recreate the backend and worker using
the AI override:

```sh
docker compose --env-file backend/.env.production \
  -f docker-compose.production.yml -f docker-compose.ai.yml \
  up -d --build backend worker
```

The AI-enabled override uses CPU-only PyTorch on Linux ARM64. E5 can run on the
2 OCPU / 12 GB Oracle Always Free VM, but throughput will be limited. Grounding
DINO, SAM, and Ollama are not recommended on that small VM.

For a local Python environment, install `backend/requirements-ai.txt` into the
backend virtual environment and download the same models into a local Hugging
Face cache before enabling the settings. Model loading is `local_files_only`,
so a missing checkpoint never triggers a hidden download.

## What the model output means

Grounding DINO's prompt asks for buildings, and SAM refines each detected box
to a mask. It is a pretrained baseline, not a cadastral boundary authority.
Building masks need human review and comparison with surveyed outlines before
they are used in parcel decisions. The output confidence is a detector score,
not a calibrated probability of cadastral correctness. No fine-tuning or
project-specific training is required for this initial pipeline.

E5 embeddings are additional evidence, not a replacement for parcel IDs,
spatial predicates, or reviewer decisions. Similar names can refer to
different parties; confidence calibration against a labeled local sample is
still required before raising the automation threshold.

## Still required for a defensible pilot

This local setup has no software license or API fee. It does not remove the
need for authorized high-resolution drone/ORI imagery, authoritative
cadastral parcels, and verified field points. Those sources are needed to
check whether pretrained detections and spatial matches are suitable for the
pilot area.
