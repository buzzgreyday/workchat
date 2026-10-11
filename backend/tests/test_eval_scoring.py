"""
The eval harness's scorer, held to what a reply means rather than how it is
typed. It grades every model comparison, so a scorer that mistakes "isn’t" for
something else, or an answer that was right in August for one wrong in
October, sends the comparison the wrong way.
"""

from datetime import date

from tests.evals.run_eval import duration_phrases, normalise, score

ABSENT = {"id": 0, "expect": "absent"}


def test_curly_apostrophes_and_contractions_read_as_plain_negation():
    assert normalise("Terraform isn’t listed") == "Terraform is not listed"
    assert score(ABSENT, "Go or Rust experience isn’t listed in Michael’s CV.")[0] == "ok"
    assert score(ABSENT, "Michael’s salary expectations aren’t on file.")[0] == "ok"


def test_an_answer_that_claims_the_skill_is_still_a_wrong_positive():
    assert score(ABSENT, "Yes, he has used Terraform for years.")[0] == "WRONG POSITIVE"


def test_how_long_is_judged_on_the_day_the_answer_was_given():
    q = {"id": 8, "expect": "covered", "since": "2025-09"}

    assert score(q, "He has been there for 11 months.", on=date(2026, 8, 14))[0] == "ok"
    assert score(q, "He has been there for 11 months.", on=date(2026, 10, 11))[0] == "MISSED FACT"
    assert score(q, "About 1 year and 1 month.", on=date(2026, 10, 11))[0] == "ok"
    assert score(q, "A little over one year.", on=date(2026, 10, 11))[0] == "ok"


def test_duration_phrases_change_with_the_calendar():
    assert "11 month" in duration_phrases("2025-09", date(2026, 8, 1))
    assert "year and 1 month" in duration_phrases("2025-09", date(2026, 10, 1))
    assert "11 month" not in duration_phrases("2025-09", date(2026, 10, 1))
