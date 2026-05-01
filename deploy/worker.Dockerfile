# File: Dockerfile.worker
FROM python:3.10-slim

# Install system dependencies (nodejs required by yt-dlp for JS challenges)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    curl \
    nodejs \
    fonts-noto \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Optimization: Pre-warm models to cache them in the layer
RUN python scripts/prewarm_models.py

# Environment Defaults
ENV PYTHONPATH=.
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Use bootstrap for orchestration (wait for migrations -> worker)
ENTRYPOINT ["python", "bootstrap.py"]
CMD ["worker"]
