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
    with _env(DEV_MODE="1", OPENAI_MODEL=None) as settings:
        assert settings.openai_model == "gpt-4.1-nano"


# DEV_MODE=0 makes BASE_URL and ALLOWED_HOSTS mandatory, which is the point of
# them; supply them so these tests fail over the model rather than over config.
PRODUCTION = {"DEV_MODE": "0", "BASE_URL": "https://x.test", "ALLOWED_HOSTS": "https://x.test"}


def test_production_defaults_to_the_better_model():
    """
    The measured choice, and the one a hirer actually gets — nano scored worse
    on depth questions. A cheaper default must never leak into DEV_MODE=0.
    """
    with _env(**PRODUCTION, OPENAI_MODEL=None) as settings:
        assert settings.openai_model == "gpt-4.1-mini"


@pytest.mark.parametrize(
    "mode", [{"DEV_MODE": "1"}, PRODUCTION], ids=["dev", "production"]
)
def test_explicit_model_wins_in_either_mode(mode):
    """How an eval arm pins a model regardless of the environment it runs in."""
    with _env(**mode, OPENAI_MODEL="gpt-4.1-nano") as settings:
        assert settings.openai_model == "gpt-4.1-nano"


def test_settings_are_restored_after_a_patched_environment():
    """The fixture's own guarantee — a stale cached Settings here would mislead
    every later test that reads one."""
    assert get_settings().openai_model == "gpt-4.1-nano"  # conftest sets DEV_MODE=1


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
