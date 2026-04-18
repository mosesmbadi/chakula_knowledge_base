from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.routers.foods import generation_router, router as foods_router

# Configure logging
logger.add(
    lambda msg: print(msg, end=""),  # Output to stdout for Docker
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    level="INFO",
    serialize=False,  # Set to True for JSON in prod
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup")
    yield
    logger.info("Application shutdown")


app = FastAPI(title="Chakula API", lifespan=lifespan)

# Add loguru middleware for request logging
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class LogRequestsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip logging for health checks to avoid noise
        if request.url.path == "/health":
            return await call_next(request)
        
        logger.info(f"{request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"Response: {response.status_code}")
        return response

app.add_middleware(LogRequestsMiddleware)

app.include_router(foods_router)
app.include_router(generation_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
