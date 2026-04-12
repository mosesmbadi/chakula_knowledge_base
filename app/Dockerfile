FROM python:3.11-slim

WORKDIR /app

# System deps needed for psycopg2 and sentence-transformers
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt

# Pre-download the embedding model at build time
# so the first request isn't slow
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy app directory contents directly into WORKDIR so paths are:
#   /app/alembic.ini          ← alembic finds its config here
#   /app/app/                 ← Python package (app.main, app.config, …)
#   /app/migrations/          ← alembic migration scripts
COPY app/ .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && cd / && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
