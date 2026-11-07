"""Regression tests for issues fixed in commit ef8cb2b."""
import pytest
from pydantic import ValidationError

from app.common.models import JWT, IssueTokenRequest, TokenClaims


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


# --- TokenClaims: the decode-side model --------------------------------------

def test_token_claims_invents_nothing():
    """A v1 token carries none of the v2 claims, and parsing one must not make
    any up — `JWT`, the minting model, would have defaulted max_queries to 20."""
    claims = TokenClaims.model_validate({"sub": "hire", "iat": 1, "exp": 2, "jti": "abc"})
    assert claims.version == 1
    assert (claims.ver, claims.typ, claims.tid, claims.sid) == (None, None, None, None)


def test_token_claims_refuses_a_boolean_version():
    """`True` is an `int` in Python, and a lax field would coerce it to 1 —
    reading a boolean as the version that marks the tokens already in the wild."""
    with pytest.raises(ValidationError):
        TokenClaims.model_validate({"ver": True})


def test_token_claims_keeps_an_unknown_type_parseable():
    """Not a Literal on purpose: an unrecognised `typ` has to reach the auth
    service, which answers "not an access token" rather than "unparseable"."""
    assert TokenClaims.model_validate({"ver": 2, "typ": "nonsense"}).typ == "nonsense"


def test_token_claims_ignores_claims_it_does_not_know():
    assert TokenClaims.model_validate({"ver": 2, "something_new": "x"}).version == 2


# --- Grant.refusal: the one statement of what makes a grant unusable --------

def _grant(**overrides):
    import uuid
    from datetime import datetime, timedelta, timezone

    from app.common.models import Grant

    fields = dict(
        user_id=uuid.uuid4(),
        subject="s",
        token_hash="h",
        max_queries=5,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    fields.update(overrides)
    return Grant(**fields)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_a_live_grant_has_no_refusal():
    assert _grant().refusal(_now()) is None


def test_a_spent_quota_is_not_a_refusal():
    # Exhaustion is the spend's business: /session reports zero, it does not 401.
    assert _grant(used_queries=5).refusal(_now()) is None


def test_a_revoked_grant_is_refused_as_revoked():
    from app.common.exceptions import TokenRevoked

    assert isinstance(_grant(revoked_at=_now()).refusal(_now()), TokenRevoked)


def test_an_expired_grant_is_refused_as_expired():
    from app.common.exceptions import TokenExpired

    assert isinstance(_grant(expires_at=_now()).refusal(_now()), TokenExpired)


def test_revoked_wins_over_expired():
    from app.common.exceptions import TokenRevoked

    refusal = _grant(revoked_at=_now(), expires_at=_now()).refusal(_now())
    assert isinstance(refusal, TokenRevoked)


def test_a_version_mismatch_is_an_invalid_token():
    from app.common.exceptions import InvalidToken

    assert isinstance(_grant(version=2).refusal(_now(), expected_version=1), InvalidToken)


def test_no_expected_version_checks_none():
    assert _grant(version=2).refusal(_now()) is None
