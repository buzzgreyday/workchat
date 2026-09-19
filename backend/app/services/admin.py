import time
import uuid
from datetime import datetime, timezone

from app.common.logging.logging import logger
from app.common.models import Grant, IssueTokenRequest
from app.repositories.base import TokenRepositoryBase, UserRepositoryBase
from app.services.auth import auth
from app.services.db import hash_token


async def issue_token(
        req: IssueTokenRequest,
        users: UserRepositoryBase,
        tokens: TokenRepositoryBase,
) -> str:
    """
    Mint the token that goes in the user's link.

    Whether that is a v1 access token or a v2 claim token is the only difference
    between the two versions here: the grant row, the user, the quota and the
    expiry are minted identically either way, because a claim token is a way of
    *reaching* a grant, not a different kind of grant.

    Token construction itself lives on Auth so the claim shape is decided in one
    place — this function and the claim/refresh paths must agree on it exactly.

    Nothing below names a storage backend, and nothing below says when a write
    becomes durable. That is the repositories' business, and for SQL it is the
    request's session — which is why both writes land together without this
    function claiming a transaction it could not promise on every store.

    Repositories are currently configured in repositories.__init__, this might change.
    """
    now_ts = int(time.time())
    now_dt = datetime.fromtimestamp(now_ts)
    exp_at_ts = now_ts + req.expires_in_seconds
    exp_at_dt = datetime.fromtimestamp(exp_at_ts, tz=timezone.utc)
    token_id = uuid.uuid4()

    raw_token = auth.mint_grant_token(
        subject=req.subject,
        token_id=token_id,
        issued_at=now_ts,
        expires_at=exp_at_ts,
        max_queries=req.max_queries,
        version=req.version,
    )
    logger.info(
        "New access token generated",
        extra={
            "subject": req.subject, "job_title": req.job_title, "company": req.company,
            "email": req.email, "phone": req.phone, "expires_in_seconds": req.expires_in_seconds,
            "max_queries": req.max_queries, "type": req.type, "version": req.version
        }
    )

    # Get the user from, or create the user in, the configured storage repository
    user = await users.get_by_name(req.company)
    if user is None:
        user = await users.add(name=req.company, email=req.email, phone=req.phone)

    # Create the token for the user in the configured storage repository
    grant = await tokens.add(
        Grant(
            id=token_id,
            user_id=user.id,
            token_hash=hash_token(raw_token),
            subject=req.subject,
            company=req.company,
            job_title=req.job_title,
            created_at=now_dt,
            max_queries=req.max_queries,
            expires_at=exp_at_dt,
            version=req.version,
        )
    )

    logger.info(
        "Stored token and user",
        extra={
            "token": {
                "user_id": grant.user_id,
                "token_hash": grant.token_hash,
                "subject": grant.subject,
                "company": grant.company,
                "job_title": grant.job_title,
                "created_at": grant.created_at,
                "max_queries": grant.max_queries,
                "expires_at": grant.expires_at,
                "version": grant.version
            },
            "user": {
                "id": user.id,
                "company (name)": user.name,
                "email": user.email,
                "phone": user.phone,
                "created_at": user.created_at
            }
        }
    )
    return raw_token