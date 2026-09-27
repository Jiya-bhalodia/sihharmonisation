FROM python:3.12-slim

WORKDIR /app
ARG INSTALL_LOCAL_AI=false
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-mar \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
COPY requirements-ai.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Apple Silicon development and Oracle ARM64 deployment use Linux ARM64
# workers without NVIDIA GPUs. Install the official CPU-only PyTorch wheel so
# pip cannot select CUDA/NVIDIA packages. Model weights remain a separate
# local cache download; this build never downloads model weights.
RUN if [ "$INSTALL_LOCAL_AI" = "true" ]; then \
    pip install --no-cache-dir --timeout 1000 --retries 10 \
      --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple \
      "torch==2.14.0+cpu" && \
    pip install --no-cache-dir --timeout 1000 --retries 10 -r requirements-ai.txt; \
    fi
COPY app ./app
COPY migrations ./migrations
COPY run_seed.py .
COPY healthcheck.py .

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
