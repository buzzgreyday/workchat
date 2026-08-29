import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logging.logging import logger
from app.common.models import IssueTokenRequest
from app.services.auth import auth
from app.services.db import create_user_and_relate_token


async def create_user_and_access_token(req: IssueTokenRequest, db: AsyncSession) -> str:
    """
    Mint the token that goes in the hirer's link.

    Whether that is a v1 access token or a v2 claim token is the only difference
    between the two versions here: the grant row, the user, the quota and the
    expiry are minted identically either way, because a claim token is a way of
    *reaching* a grant, not a different kind of grant.

    Token construction itself lives on Auth so the claim shape is decided in one
    place — this function and the claim/refresh paths must agree on it exactly.
    """
    now_ts = int(time.time())
    now_dt = datetime.fromtimestamp(now_ts)
    exp_at_ts = now_ts + req.expires_in_seconds
    exp_at_dt = datetime.fromtimestamp(exp_at_ts, tz=timezone.utc)
    token_id = uuid.uuid4()

    token = auth.mint_grant_token(
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
    await create_user_and_relate_token(
        token_id=token_id,
        raw_token=token,
        subject=req.subject,
        company=req.company,
        max_queries=req.max_queries,
        expires_at=exp_at_dt,
        job_title=req.job_title,
        email=req.email,
        phone=req.phone,
        created_at=now_dt,
        version=req.version,
        db=db
    )

    return token
