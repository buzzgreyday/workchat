"""
Public-facing chat backend for the CV agent.
Hirers hit /chat with a message; this calls the model with tool definitions
mirroring search_cv() / get_full_entry(), executes them locally, and
returns the model's final answer.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.config import DEV_MODE, ALLOWED_HOSTS
from app.common.logging.logging import logger
from app.common.middleware import RequestContextMiddleware
from app.openai.client import get_openai_client
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f'Starting chat server, in {"DEV" if DEV_MODE else "PROD"} mode.', extra={"app": app})
    yield
    logger.info("Stopping chat server.", extra={"app": app})
    logger.debug("Closing chat client.", extra={"client": get_openai_client()})
    await get_openai_client().close()


app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if DEV_MODE else None,
    redoc_url="/redoc" if DEV_MODE else None,
    openapi_url="/openapi.json" if DEV_MODE else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_HOSTS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Added last, for future observability, so it wraps outermost and every log line of the request — CORS
# included — carries the correlation id.
app.add_middleware(RequestContextMiddleware)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(admin_router)