"""Regression tests for issues fixed in commit ef8cb2b."""
import pytest
from pydantic import ValidationError

from app.common.models import JWT, IssueTokenRequest


def test_issue_token_request_rejects_bad_email():
    with pytest.raises(ValidationError):
        IssueTokenRequest(subject="s", company="c", email="not-an-email")


def test_issue_token_request_rejects_out_of_range_max_queries():
    with pytest.raises(ValidationError):
        IssueTokenRequest(subject="s", company="c", max_queries=0)
    with pytest.raises(ValidationError):
        IssueTokenRequest(subject="s", company="c", max_queries=1001)


def test_issue_token_request_rejects_too_short_expiry():
    with pytest.raises(ValidationError):
        IssueTokenRequest(subject="s", company="c", expires_in_seconds=59)


def test_issue_token_request_rejects_empty_subject():
    with pytest.raises(ValidationError):
        IssueTokenRequest(subject="", company="c")


def test_issue_token_request_accepts_valid_input():
    req = IssueTokenRequest(
        subject="hire-mgr",
        company="Acme",
        email="jane@acme.com",
        max_queries=50,
        expires_in_seconds=3600,
    )
    assert req.max_queries == 50

def test_chat_request_rejects_empty_message():
    import pytest
    from pydantic import ValidationError
    from app.common.models import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_chat_request_rejects_oversized_message():
    """Bounded so it cannot exceed the chat_messages.content column, and to cap
    what one request costs in OpenAI tokens."""
    import pytest
    from pydantic import ValidationError
    from app.common.models import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 4001)


def test_chat_request_accepts_conversation_id():
    import uuid
    from app.common.models import ChatRequest

    cid = uuid.uuid4()
    assert ChatRequest(message="hi", conversation_id=str(cid)).conversation_id == cid
