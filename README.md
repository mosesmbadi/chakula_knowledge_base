# Chakula Knowledge Base API

FastAPI service for generating, reviewing, and approving food entries into the Chakula knowledge base.

## Stack
- **FastAPI** — API framework
- **PostgreSQL + pgvector** — storage and semantic search
- **Ollama** — local LLM (no API costs)
- **sentence-transformers** — local embeddings (no API costs)

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose

That's it. Postgres, pgvector, Ollama, and the API all run in containers.

---

## Setup

```bash
# 1. Start everything
docker compose up --build

# On first run this will:
#   - Pull the pgvector/postgres image
#   - Pull the Ollama image
#   - Download the llama3.2 model (~2GB — one time only, cached in a volume)
#   - Build the FastAPI image (pre-downloads the embedding model)
#   - Start all services
```

API docs available at: **http://localhost:8000/docs**

---

## Useful commands

```bash
# Start in background
docker compose up -d --build

# View logs
docker compose logs -f api        # FastAPI logs
docker compose logs -f ollama     # Ollama logs
docker compose logs -f db         # Postgres logs

# Stop everything
docker compose down

# Stop and wipe all data (nuclear option)
docker compose down -v

# Rebuild just the API after code changes
docker compose up --build api
```

---

## Swapping the LLM model

Edit `docker-compose.yml` — change both `OLLAMA_MODEL` and the pull command:

```yaml
ollama-pull:
  entrypoint: >
    sh -c "ollama pull mistral && echo '✅ Model ready'"   # ← change model here

api:
  environment:
    OLLAMA_MODEL: mistral                                   # ← and here
```

Good alternatives for low-resource machines:
- `llama3.2` — default, good balance (~2GB)
- `mistral` — fast, reliable (~4GB)
- `qwen2.5:3b` — very small, lower quality (~2GB)

---

## Connecting a DB client (TablePlus, DBeaver)

Postgres is exposed on `localhost:5432`:

| Field | Value |
|---|---|
| Host | localhost |
| Port | 5432 |
| User | chakula |
| Password | chakula_secret |
| Database | chakula |

---

## API Endpoints

### Generate foods for a region
```
POST /foods/generate
{
  "region": "Coast Kenya",
  "count": 10
}
```
Calls the local LLM, saves entries as **draft**.

### Upload foods manually as JSON
```
POST /api/foods/generate/upload/
{
  "region": "Coast Kenya",
  "foods": [
    {
      "name": "Mahamri",
      "local_names": ["Mandazi ya nazi"],
      "description": "A lightly sweet coconut dough fried until golden and commonly eaten with chai.",
      "price_min_kes": 30,
      "price_max_kes": 80,
      "meal_type": ["breakfast", "snack"],
      "ingredients": ["flour", "coconut milk", "cardamom", "yeast"],
      "common_at": ["street stalls", "homes", "bakeries"],
      "protein": "low",
      "carbs": "high",
      "vegetables": "low",
      "sub_regions": ["Mombasa", "Kilifi", "Kwale"],
      "tags": ["vegetarian", "halal"]
    }
  ]
}
```
Stores the uploaded foods as **draft** entries, using the same dedupe and approval flow as LLM-generated foods.

---

### List drafts (review queue)
```
GET /foods/drafts
GET /foods/drafts?region=Coast Kenya
```

---

### Approve a food (single entry)
```
POST /foods/{id}/approve
```
- Generates embedding vector
- Sets status to **verified**
- Entry is now live and semantically searchable

---

### Reject a food
```
POST /foods/{id}/reject
```
Marks as rejected. Kept in DB for audit trail.

---

### List verified (live) foods
```
GET /foods/verified
GET /foods/verified?region=Uganda North
```

---

## The Flow

```
POST /foods/generate (region: "Kisumu")
        ↓
  LLM generates 10 foods
        ↓
  Saved to Postgres as status=draft
        ↓
GET /foods/drafts  ← human reviews these
        ↓
POST /foods/{id}/approve  ← for each good one
        ↓
  Embedding generated → stored in pgvector
  Status set to verified
        ↓
  Food is now live and queryable
```

---

## Region examples
- `Kenya`
- `Coast Kenya`
- `Kiambu County`
- `Northern Kenya`
- `Uganda North`
- `Egypt`
- `Tanzania`
- `Nairobi CBD`
- `Lake Victoria region`


PROCESS: 

Generate foods for Uganda
Approve them (which creates the embeddings)
Then recommend will return results

```bash
# 1. Generate foods
curl -X POST http://localhost:8000/foods/generate \
  -H 'Content-Type: application/json' \
  -d '{"region": "Uganda", "count": 10}'

# 2. Check drafts
curl http://localhost:8000/foods/drafts?region=Uganda

# 3. Approve each one (replace <id> with actual IDs from step 2)
curl -X POST http://localhost:8000/foods/<id>/approve

# Approve all drafts
curl -X POST http://localhost:8000/foods/approve-all

# Approve all drafts for a specific region
curl -X POST "http://localhost:8000/foods/approve-all?region=Uganda"

# 4. Now recommend will work
curl -X POST http://localhost:8000/foods/recommend \
  -H 'Content-Type: application/json' \
  -d '{"region": "Uganda", "budget_per_meal_kes": 10000, "limit": 5}'
```

To test with more filters:

```bash
# Lunch only, budget under 800 KES
curl -X POST http://localhost:8000/foods/recommend \
  -H 'Content-Type: application/json' \
  -d '{"region": "Uganda", "budget_per_meal_kes": 800, "meal_type": "lunch", "limit": 3}'

# With dietary filter
curl -X POST http://localhost:8000/foods/recommend \
  -H 'Content-Type: application/json' \
  -d '{"region": "Uganda", "budget_per_meal_kes": 10000, "dietary_goals": ["kidney-friendly"], "limit": 5}'

# Exclude a food (e.g. user rejected Mandazi)
curl -X POST http://localhost:8000/foods/recommend \
  -H 'Content-Type: application/json' \
  -d '{"region": "Uganda", "budget_per_meal_kes": 10000, "exclude_food_ids": ["affc6a12-53f8-437a-b8a6-3339e342a210"], "limit": 5}'
```