"""
The boundary contract: domain exceptions in, FastAPI-shaped errors out.

The services raise these from well below the HTTP layer, so what matters is that
main.py's handler renders them identically to an HTTPException — a client, the
frontend or an older test must not be able to tell which kind produced a given
401.
"""
import pytest

from app.common.exceptions import (
    AppError,
    AuthError,
    ClaimAlreadyUsed,
    InvalidToken,
    QuotaExhausted,
    RefreshTokenReplayed,
    RotationInProgress,
)
import uuid


def test_every_auth_error_defaults_to_401():
    assert AuthError().status_code == 401
    assert InvalidToken().status_code == 401


def test_conflicts_are_409_not_401():
    """A spent link and a raced rotation are not credential failures, and a
    client treating every non-200 as a logout would be wrong about both."""
    assert ClaimAlreadyUsed().status_code == 409
    assert RotationInProgress().status_code == 409


def test_quota_is_429():
    assert QuotaExhausted().status_code == 429


def test_detail_can_be_overridden_without_subclassing():
    assert InvalidToken().detail == "Invalid token"
    assert InvalidToken("Something else").detail == "Something else"


def test_replay_carries_the_grant_it_locked_out():
    """The layer that detects a replay cannot notify anyone — it has the session,
    not the hirer. The grant id rides along so the layer above can."""
    token_id = uuid.uuid4()
    exc = RefreshTokenReplayed(token_id)

    assert exc.token_id == token_id
    assert exc.context["token_id"] == str(token_id)
    assert exc.detail == "Refresh token already used"


def test_context_stays_out_of_the_detail():
    """`detail` is what the caller is told; anything that would help someone
    probing belongs in the log line instead."""
    exc = InvalidToken(field="tid", token_id="abc")

    assert exc.context == {"field": "tid", "token_id": "abc"}
    assert "abc" not in exc.detail


@pytest.mark.parametrize(
    "exc",
    [InvalidToken(), ClaimAlreadyUsed(), QuotaExhausted(), RotationInProgress()],
)
def test_all_are_app_errors_so_one_handler_catches_them(exc):
    assert isinstance(exc, AppError)


async def test_handler_renders_the_same_shape_as_httpexception(client):
    """A domain exception raised deep in a service, and FastAPI's own error for a
    missing header, must be indistinguishable to the caller."""
    from_service = await client.post("/chat", json={"message": "hi"})
    assert from_service.status_code == 401
    assert from_service.json() == {"detail": "Missing or malformed Authorization header"}

    from_fastapi = await client.post("/admin/issue-token", json={"subject": "s", "company": "c"})
    assert from_fastapi.status_code == 422
    assert "detail" in from_fastapi.json()
