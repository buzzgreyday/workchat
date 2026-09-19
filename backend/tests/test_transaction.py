"""
The request's transaction.

Moving the commit into `get_db` is what lets a service write through
repositories and say nothing about durability. That only holds if the teardown
really does commit a clean request and discard a failed one, including when a
domain error is caught and rendered as a response — so this asserts both
against rows, using the same `transaction` helper production uses.
"""
import httpx
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from starlette.requests import Request

from app.common.db import transaction
from app.common.exceptions import AppError
from app.common.schemas import DatabaseUser


async def _names(db_session) -> list[str]:
    result = await db_session.execute(select(DatabaseUser.name))
    return [n for (n,) in result.all()]


@pytest.fixture
async def probe(session_maker):
    """
    A minimal app wired exactly as the real one: the same transaction helper as
    a yield dependency, and the same AppError handler from main.py.
    """
    async def get_db():
        async with transaction(session_maker) as session:
            yield session

    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.post("/clean")
    async def clean(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
        db.add(DatabaseUser(name="Clean", email=None, phone=None))
        await db.flush()
        return {"ok": True}

    @app.post("/domain-error")
    async def domain_error(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
        db.add(DatabaseUser(name="DomainError", email=None, phone=None))
        await db.flush()
        raise AppError()

    @app.post("/crash")
    async def crash(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
        db.add(DatabaseUser(name="Crash", email=None, phone=None))
        await db.flush()
        raise RuntimeError("boom")

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


async def test_clean_request_commits(probe, db_session):
    resp = await probe.post("/clean")

    assert resp.status_code == 200
    assert "Clean" in await _names(db_session)


async def test_handled_domain_error_rolls_back(probe, db_session):
    """
    The subtle one. An AppError is caught and rendered as a response, so it
    would be easy to assume the teardown never sees it — but FastAPI runs
    exception handlers outside the dependency exit stack, so the rollback fires
    before the error becomes a 500.
    """
    resp = await probe.post("/domain-error")

    assert resp.status_code == AppError.status_code
    assert "DomainError" not in await _names(db_session)


async def test_unhandled_error_rolls_back(probe, db_session):
    resp = await probe.post("/crash")

    assert resp.status_code == 500
    assert "Crash" not in await _names(db_session)
