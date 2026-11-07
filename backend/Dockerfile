# VisionFlywheel backend — production image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for OpenCV + torch
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (better layer caching)
COPY backend/requirements.txt backend/requirements-ml.txt ./
RUN pip install -r requirements.txt
# ML extras are opt-in: install with --build-arg WITH_ML=1
ARG WITH_ML=0
RUN if [ "$WITH_ML" = "1" ]; then pip install -r requirements-ml.txt; fi

COPY backend/ ./backend/
COPY scripts/ ./scripts/

WORKDIR /app/backend

# Runtime state dirs
RUN mkdir -p /app/runtime_data/uploads /app/runtime_data/results \
             /app/runtime_data/datasets /app/backend/weights

EXPOSE 8000

# Run as non-root
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
