import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_200_OK

from app.common.config import BASE_URL
from app.common.models import (
    ChatMessageOut,
    ConversationDetail,
    ConversationSummary,
    IssueTokenRequest,
)
from app.helpers.qr_code import get_qr_code
from app.repositories import (
    get_conversation_repository,
    get_refresh_session_repository,
    get_token_repository,
    get_user_repository,
)
from app.repositories.base import (
    ConversationRepository,
    RefreshSessionRepository,
    TokenRepository,
    UserRepository,
)
from app.services import admin
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
async def issue_token(
    req: IssueTokenRequest,
    users: UserRepository = Depends(get_user_repository),
    tokens: TokenRepository = Depends(get_token_repository),
) -> Response:
    logger.info(
        "Issuing a new access token",
        extra={
            "subject": req.subject, "job_title": req.job_title, "company": req.company,
            "email": req.email, "phone": req.phone, "expires_in_seconds": req.expires_in_seconds,
            "max_queries": req.max_queries, "type": req.type, "version": req.version
        }
    )
    token = await admin.issue_token(req, users=users, tokens=tokens)
    # v1 puts the access token straight in the link; v2 puts a claim token there
    # instead, so the query parameter has to change with it. The frontend reads
    # whichever one it finds — ?token= is still what every issued link carries.
    param = "token" if req.version == 1 else "claim"
    if req.type == "qr":
        qr = get_qr_code(url=f"{BASE_URL}/?{param}={token}")
        return Response(content=bytes(qr), media_type="image/png", status_code=HTTP_200_OK)
    # "token" stays the key for both so an existing caller reading body["token"]
    # is unaffected; "kind" is what says which flow it belongs to.
    return JSONResponse(
        content={"token": token, "version": req.version, "kind": "access" if req.version == 1 else "claim"},
        media_type="application/json",
        status_code=HTTP_200_OK,
    )

@router.post(
    "/tokens/{token_id}/revoke",
    dependencies=[Depends(require_admin)],
    response_class=JSONResponse,
    summary="Revoke a grant and every session under it",
    description=(
        "The kill switch. Stamps `tokens.revoked_at` and cuts every refresh "
        "session, so outstanding refresh tokens stop rotating and outstanding "
        "access tokens stop being honoured on their next request. Idempotent."
    ),
)
async def revoke_token(
    token_id: uuid.UUID,
    tokens: TokenRepository = Depends(get_token_repository),
    sessions: RefreshSessionRepository = Depends(get_refresh_session_repository),
) -> JSONResponse:
    grant = await tokens.get(token_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Token not found")

    already_revoked, sessions_cut = await admin.revoke_grant(token_id, tokens, sessions)
    logger.warning(
        "Grant revoked by admin",
        extra={
            "token_id": token_id, "subject": grant.subject, "company": grant.company,
            "already_revoked": already_revoked, "sessions_cut": sessions_cut,
        },
    )
    return JSONResponse(
        content={
            "token_id": str(token_id),
            "already_revoked": already_revoked,
            "sessions_cut": sessions_cut,
        },
        status_code=HTTP_200_OK,
    )


@router.get(
    "/conversations",
    dependencies=[Depends(require_admin)],
    response_model=list[ConversationSummary],
    summary="List chat conversations",
    description="What hirers have been asking. Requires your admin key in the X-Admin-Key header.",
)
async def get_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    company: str | None = None,
    since: datetime | None = None,
    conversations: ConversationRepository = Depends(get_conversation_repository),
) -> list[ConversationSummary]:
    previews = await conversations.list_previews(
        limit=limit, offset=offset, company=company, since=since
    )
    return [ConversationSummary.model_validate(p, from_attributes=True) for p in previews]


@router.get(
    "/conversations/{conversation_id}",
    dependencies=[Depends(require_admin)],
    response_model=ConversationDetail,
    summary="Read one conversation in full",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    conversations: ConversationRepository = Depends(get_conversation_repository),
) -> ConversationDetail:
    conversation, messages = await conversations.get_with_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationDetail(
        id=conversation.id,
        subject=conversation.subject,
        company=conversation.company,
        job_title=conversation.job_title,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        redacted_at=conversation.redacted_at,
        messages=[ChatMessageOut.model_validate(m) for m in messages],
    )


@router.post(
    "/conversations/{conversation_id}/redact",
    dependencies=[Depends(require_admin)],
    response_class=JSONResponse,
    summary="Erase the content of one conversation",
    description=(
        "Nulls the message text and stamps redacted_at, keeping the row so counts "
        "and timings survive. Deletion is not offered: every foreign key here is "
        "RESTRICT, and the operational record is worth keeping."
    ),
)
async def redact(
    conversation_id: uuid.UUID,
    conversations: ConversationRepository = Depends(get_conversation_repository),
) -> JSONResponse:
    # An existence check, not a load: the transcript this used to fetch was
    # discarded, and every message body came back with it.
    if not await conversations.exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    redacted = await conversations.redact(conversation_id)
    return JSONResponse(
        content={"conversation_id": str(conversation_id), "messages_redacted": redacted},
        status_code=HTTP_200_OK,
    )
