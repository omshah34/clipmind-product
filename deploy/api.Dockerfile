# File: Dockerfile.api
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Environment Defaults
ENV PYTHONPATH=.
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

EXPOSE 8000

# Use bootstrap for orchestration (migrations -> api)
ENTRYPOINT ["python", "bootstrap.py"]
CMD ["api"]
