"""
Building the application.

Separate from `main.py` so that importing the factory does not build an app —
and therefore does not read the environment. `main.py` is the ASGI entrypoint
and does build one; a test imports this module instead and builds its own.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.config import Settings, get_settings
from app.common.exceptions import AppError
from app.common.logging.logging import logger
from app.common.middleware import RequestContextMiddleware
from app.openai.client import get_openai_client
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router
from app.routes.session import router as session_router
from app.services.search import get_search


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info(
        f'Starting chat server, in {"DEV" if settings.dev_mode else "PROD"} mode.',
        extra={"app": app},
    )
    # Before the socket is bound, so a server with no CV never gets the chance
    # to answer from nothing. Raising here makes uvicorn exit rather than serve,
    # which is what turns a broken resources mount into a failed deploy instead
    # of a live site that denies everything it is asked.
    await get_search().load()
    yield
    logger.info("Stopping chat server.", extra={"app": app})
    logger.debug("Closing chat client.", extra={"client": get_openai_client()})
    await get_openai_client().close()


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    The one place a domain exception becomes a status code.

    Renders the same `{"detail": ...}` body FastAPI produces for an
    HTTPException, so nothing downstream — a client, a test, the frontend's
    error handling — can tell which of the two a given 401 came from.
    """
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the application.

    A factory rather than a module-level `FastAPI(...)`, because constructing it
    reads configuration — the docs URLs and the CORS list both key off DEV_MODE —
    and doing that at import is what made importing this module require a fully
    configured environment. A test can now build an app against its own settings
    instead of arranging the environment before its own import statements.
    """
    settings = settings or get_settings()

    app = FastAPI(
        lifespan=lifespan,
        docs_url="/docs" if settings.dev_mode else None,
        redoc_url="/redoc" if settings.dev_mode else None,
        openapi_url="/openapi.json" if settings.dev_mode else None,
    )

    app.add_middleware(
        CORSMiddleware,
        # Concrete origins, never "*": the refresh cookie makes these credentialed
        # requests, and a browser refuses one whose Access-Control-Allow-Origin is a
        # wildcard. In production the frontend and the API share an origin behind
        # Caddy anyway, so this only really governs dev on :3000.
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Added last, for future observability, so it wraps outermost and every log line
    # of the request — CORS included — carries the correlation id.
    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(AppError, app_error_handler)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(session_router)
    app.include_router(chat_router)
    app.include_router(admin_router)
    return app
