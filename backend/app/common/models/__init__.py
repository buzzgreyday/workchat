"""
The Pydantic models, split by what they are for.

`api` holds the request/response shapes the HTTP surface speaks in; `user`,
`token` and `session` hold the domain models the repository layer returns in
place of ORM rows. All are re-exported here so `from app.common.models import X`
keeps working regardless of which side of that split X lives on.
"""

from app.common.models.api import (
    ChatMessageOut,
    ChatRequest,
    ClaimRequest,
    ConversationDetail,
    ConversationRedacted,
    ConversationSummary,
    GrantRevoked,
    IssueTokenRequest,
    JWT,
    Record,
    RefreshRequest,
    SessionInfo,
    SessionOut,
    TokenClaims,
    TokenContext,
    TokenPair,
    Usage,
)
from app.common.models.conversation import (
    ChatMessage,
    Conversation,
    ConversationPreview,
)
from app.common.models.session import RefreshSession
from app.common.models.token import Grant
from app.common.models.user import User

__all__ = [
    "JWT",
    "Grant",
    "ChatMessage",
    "ChatMessageOut",
    "ChatRequest",
    "ClaimRequest",
    "Conversation",
    "ConversationDetail",
    "ConversationPreview",
    "ConversationRedacted",
    "ConversationSummary",
    "GrantRevoked",
    "IssueTokenRequest",
    "Record",
    "RefreshSession",
    "RefreshRequest",
    "SessionInfo",
    "SessionOut",
    "TokenClaims",
    "TokenContext",
    "TokenPair",
    "Usage",
    "User",
]
