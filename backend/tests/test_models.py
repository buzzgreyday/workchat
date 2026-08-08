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