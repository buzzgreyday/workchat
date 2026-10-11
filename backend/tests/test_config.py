"""
The model switch.

These used to reload `app.common.config` under a patched environment, because
the module read it at import and there was no other way to ask it a second
question. Settings are built by a call now, so a test clears the cache and asks
again — and does not have to put the module back afterwards.
"""
import importlib
import os
from contextlib import contextmanager

import pytest

from app.common.config import Settings, get_settings


@contextmanager
def _env(**overrides: str | None):
    """Build settings under a patched environment, restoring it afterwards.

    `get_settings.cache_clear()` runs on the way out as well as in: the cached
    value belongs to whatever environment built it, and leaving one behind that
    a later test did not ask for is the failure this file used to guard with a
    module reload.
    """
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        yield Settings.from_env()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def test_dev_defaults_to_the_cheap_model():
    with _env(DEV_MODE="1", OPENAI_MODEL=None, OPENAI_REASONING_EFFORT=None) as settings:
        assert settings.openai_model == "gpt-6-luna"
        # A reasoning model, so its effort is sent — and "none", the only one
        # OpenAI takes with tools over Chat Completions; sent nothing, it
        # defaults to "medium" and refuses.
        assert settings.openai_reasoning_effort == "none"


# DEV_MODE=0 makes BASE_URL and ALLOWED_HOSTS mandatory, which is the point of
# them; supply them so these tests fail over the model rather than over config.
PRODUCTION = {"DEV_MODE": "0", "BASE_URL": "https://x.test", "ALLOWED_HOSTS": "https://x.test"}


def test_production_defaults_to_the_better_model():
    """
    The measured choice, and the one a hirer actually gets — nano scored worse
    on depth questions. A cheaper default must never leak into DEV_MODE=0.
    """
    with _env(**PRODUCTION, OPENAI_MODEL=None, OPENAI_REASONING_EFFORT=None) as settings:
        assert settings.openai_model == "gpt-4.1-mini"
        # Not a reasoning model: no effort is sent, which it would reject.
        assert settings.openai_reasoning_effort is None


@pytest.mark.parametrize(
    "mode", [{"DEV_MODE": "1"}, PRODUCTION], ids=["dev", "production"]
)
def test_explicit_model_wins_in_either_mode(mode):
    """How an eval arm pins a model regardless of the environment it runs in."""
    with _env(**mode, OPENAI_MODEL="gpt-6.1-sol", OPENAI_REASONING_EFFORT=None) as settings:
        assert settings.openai_model == "gpt-6.1-sol"
        # A model named by hand gets no effort it was not given.
        assert settings.openai_reasoning_effort is None


def test_settings_are_restored_after_a_patched_environment():
    """The fixture's own guarantee — a stale cached Settings here would mislead
    every later test that reads one."""
    assert get_settings().openai_model == "gpt-6-luna"  # conftest sets DEV_MODE=1


def test_importing_the_application_reads_no_configuration():
    """The property the whole shape exists for.

    Importing used to demand a configured environment, because config.py called
    require_env at module level and app/main.py built a FastAPI at module level.
    Asserted on the cache rather than by scrubbing the environment, because
    `Settings.from_env` loads `backend/.env` — so on a developer's machine a
    "missing" secret is not missing at all, and the test would pass in CI and
    fail locally.
    """
    get_settings.cache_clear()
    importlib.reload(importlib.import_module("app.factory"))
    assert get_settings.cache_info().currsize == 0, (
        "importing app.factory built Settings; something reads configuration at import"
    )


# --- reasoning effort -----------------------------------------------------------

@pytest.mark.parametrize("mode", [{"DEV_MODE": "1"}, PRODUCTION], ids=["dev", "production"])
def test_reasoning_effort_is_set_centrally_and_wins(mode):
    with _env(**mode, OPENAI_REASONING_EFFORT="High") as settings:
        assert settings.openai_reasoning_effort == "high"


def test_an_empty_reasoning_effort_sends_none():
    """How a non-reasoning model is used in dev, where the default would send one."""
    with _env(DEV_MODE="1", OPENAI_MODEL="gpt-4.1-mini", OPENAI_REASONING_EFFORT="") as settings:
        assert settings.openai_reasoning_effort is None
    with _env(DEV_MODE="1", OPENAI_MODEL=None, OPENAI_REASONING_EFFORT="") as settings:
        assert settings.openai_reasoning_effort is None


def test_a_misspelt_reasoning_effort_stops_the_start():
    """Refused when the settings are built, not by OpenAI on every chat request."""
    with pytest.raises(ValueError, match="OPENAI_REASONING_EFFORT"):
        with _env(DEV_MODE="1", OPENAI_REASONING_EFFORT="loww"):
            pass

