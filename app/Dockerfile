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
# so the first approval request isn't slow
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app/ ./app

RUN chmod +x /app/app/entrypoint.sh

EXPOSE 8000

CMD ["sh", "-c", "cd /app/app && alembic upgrade head && cd /app && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
