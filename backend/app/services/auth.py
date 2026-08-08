"""
JWT-based access control for the CV chat backend.

Each token encodes:
  - sub:         who the token is for (e.g. "Acme Corp hiring manager")
  - exp:         expiry timestamp (validated automatically by jwt.decode)
  - jti:         unique token ID, used to track per-token usage
  - max_queries: how many /chat calls this token is allowed to make

Per-token usage is enforced by an atomic UPDATE in the tokens table
(see services/db.update_token_used_query_count), not in-memory, so it
survives restarts and works across replicas.
"""

import hmac
import uuid

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import ADMIN_KEY, ALGORITHM, SECRET_KEY
from app.common.db import get_db
from app.common.models import TokenContext
from app.services.db import update_token_used_query_count

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_and_consume(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> TokenContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    raw_token = credentials.credentials  # already stripped of "Bearer " prefix

    try:
        payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(401, "Invalid token")

    try:
        token_id = uuid.UUID(jti)
    except ValueError:
        raise HTTPException(401, "Invalid token")

    row = await update_token_used_query_count(token_id=token_id, db=db)

    return TokenContext(
        sub=row.subject,
        jti=str(row.id),
        max_queries=row.max_queries,
        used_queries=row.used_queries,
        remaining_queries=row.max_queries - row.used_queries,
    )


def require_admin(x_admin_key: str = Header(...)) -> None:
    """FastAPI dependency for the token-issuing endpoint. Only you should
    be able to mint tokens — protect this with a secret only you know."""
    # compare_digest avoids leaking key length / prefix through response timing.
    if not hmac.compare_digest(x_admin_key.encode(), ADMIN_KEY.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")