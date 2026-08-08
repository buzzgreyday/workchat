from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_200_OK

from app.common.config import BASE_URL
from app.common.db import get_db
from app.common.models import IssueTokenRequest
from app.helpers.qr_code import get_qr_code
from app.services.admin import create_user_and_access_token
from app.services.auth import require_admin
from app.common.logging import logging

router = APIRouter(prefix="/admin", tags=['Admin'], include_in_schema=False)
logger = logging.logger

@router.post(
    "/issue-token",
    dependencies=[Depends(require_admin)],
    response_class=JSONResponse,
    summary="Mint a new access token",
    description="Mint a new access token for a hirer. Requires your admin key in the X-Admin-Key header.",
    responses={
        200: {
            "description": "JSON `{token: ...}` when type=token, PNG bytes when type=qr.",
        }
    },
)
async def issue_token(req: IssueTokenRequest, db: AsyncSession = Depends(get_db)):
    logger.info(
        "Issuing a new access token",
        extra={
            "subject": req.subject, "job_title": req.job_title, "company": req.company,
            "email": req.email, "phone": req.phone, "expires_in_seconds": req.expires_in_seconds,
            "max_queries": req.max_queries, "type": req.type
        }
    )
    access_token = await create_user_and_access_token(req, db)
    if req.type == "qr":
        qr = get_qr_code(url=f"{BASE_URL}/?token={access_token}")
        return Response(content=bytes(qr), media_type="image/png", status_code=HTTP_200_OK)
    return JSONResponse(content={"token": access_token}, media_type="application/json", status_code=HTTP_200_OK)