from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import engine, Base
from app.routers.foods import router as foods_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (pgvector extension must already exist)
    async with engine.begin() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS foods_knowldgebase")
        )
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Chakula API", lifespan=lifespan)

app.include_router(foods_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
