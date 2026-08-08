import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import SECRET_KEY, ALGORITHM
from app.common.logging.logging import logger
from app.common.models import JWT, IssueTokenRequest
from app.services.db import create_user_and_relate_token


async def create_user_and_access_token(req: IssueTokenRequest, db: AsyncSession) -> str:
    now_ts = int(time.time())
    now_dt = datetime.fromtimestamp(now_ts)
    exp_at_ts = now_ts + req.expires_in_seconds
    exp_at_dt = datetime.fromtimestamp(exp_at_ts, tz=timezone.utc)

    _jwt_obj = JWT(
        sub=req.subject,
        iat=now_ts,
        exp=exp_at_ts,
        jti=str(uuid.uuid4()),
        max_queries=req.max_queries
    )
    jwt = _jwt_obj.generate(secret_key=SECRET_KEY, algorithm=ALGORITHM)
    logger.info(
        "New access token generated",
        extra={
            "subject": req.subject, "job_title": req.job_title, "company": req.company,
            "email": req.email, "phone": req.phone, "expires_in_seconds": req.expires_in_seconds,
            "max_queries": req.max_queries, "type": req.type
        }
    )
    await create_user_and_relate_token(
        token_id=uuid.UUID(_jwt_obj.jti),
        raw_token=jwt,
        subject=req.subject,
        company=req.company,
        max_queries=req.max_queries,
        expires_at=exp_at_dt,
        job_title=req.job_title,
        email=req.email,
        phone=req.phone,
        created_at=now_dt,
        db=db
    )

    return jwt