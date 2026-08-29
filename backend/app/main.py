"""
Public-facing chat backend for the CV agent.
Hirers hit /chat with a message; this calls the model with tool definitions
mirroring search_cv() / get_full_entry(), executes them locally, and
returns the model's final answer.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.config import CORS_ORIGINS, DEV_MODE
from app.common.exceptions import AppError
from app.common.logging.logging import logger
from app.common.middleware import RequestContextMiddleware
from app.openai.client import get_openai_client
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router
from app.routes.session import router as session_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
    # Concrete origins, never "*": the refresh cookie makes these credentialed
    # requests, and a browser refuses one whose Access-Control-Allow-Origin is a
    # wildcard. In production the frontend and the API share an origin behind
    # Caddy anyway, so this only really governs dev on :3000.
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Added last, for future observability, so it wraps outermost and every log line of the request — CORS
# included — carries the correlation id.
app.add_middleware(RequestContextMiddleware)

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """
    The one place a domain exception becomes a status code.

    Renders the same `{"detail": ...}` body FastAPI produces for an
    HTTPException, so nothing downstream — a client, a test, the frontend's
    error handling — can tell which of the two a given 401 came from.
    """
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(session_router)
app.include_router(chat_router)
app.include_router(admin_router)