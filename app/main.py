from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers.foods import router as foods_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Chakula API", lifespan=lifespan)

app.include_router(foods_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
