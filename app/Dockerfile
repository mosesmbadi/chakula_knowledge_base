# 1. Use the latest stable Python 3.12 image
FROM python:3.12-slim

# 2. Set environment variables to optimize Python performance
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/ \
    # Set a custom cache directory for transformers
    SENTENCE_TRANSFORMERS_HOME=/app/.cache

WORKDIR /app

# 3. Optimize APT: Only install what's needed for build, then clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. Separate dependency installation to leverage Docker layer caching
COPY requirements.txt .

# Install heavy dependencies first
RUN pip install --no-cache-dir --timeout 300 torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --timeout 300 -r requirements.txt

# 5. Pre-download the model during BUILD time
# This ensures the model is baked into the image, not downloaded at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 6. Copy application code
COPY . .

# 7. Use a non-root user for security (Production Best Practice)
RUN useradd -m mbadi_user && chown -R mbadi_user:mbadi_user /app
USER mbadi_user

EXPOSE 8000

# 8. Fixed Entrypoint logic
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]


# FROM python:3.11-slim

# WORKDIR /app

# RUN apt-get update && apt-get install -y \
#     gcc \
#     libpq-dev \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# COPY requirements.txt .
# RUN pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu
# RUN pip install -r requirements.txt

# RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# COPY . .

# EXPOSE 8000

# CMD ["sh", "-c", "alembic upgrade head && cd / && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
