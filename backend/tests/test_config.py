"""
The model switch.

Config is read at import time, so these reload the module under a patched
environment and always reload it back — otherwise a later test would inherit
whichever arm ran last.
"""
import importlib
import os
from contextlib import contextmanager

import pytest

import app.common.config as config


@contextmanager
def _env(**overrides: str | None):
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield importlib.reload(config)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(config)


def test_dev_defaults_to_the_cheap_model():
    with _env(DEV_MODE="1", OPENAI_MODEL=None) as cfg:
        assert cfg.OPENAI_MODEL == "gpt-4.1-nano"


# DEV_MODE=0 makes BASE_URL and ALLOWED_HOSTS mandatory, which is the point of
# them; supply them so these tests fail over the model rather than over config.
PRODUCTION = {"DEV_MODE": "0", "BASE_URL": "https://x.test", "ALLOWED_HOSTS": "https://x.test"}


def test_production_defaults_to_the_better_model():
    """
    The measured choice, and the one a hirer actually gets — nano scored worse
    on depth questions. A cheaper default must never leak into DEV_MODE=0.
    """
    with _env(**PRODUCTION, OPENAI_MODEL=None) as cfg:
        assert cfg.OPENAI_MODEL == "gpt-4.1-mini"


@pytest.mark.parametrize(
    "mode", [{"DEV_MODE": "1"}, PRODUCTION], ids=["dev", "production"]
)
def test_explicit_model_wins_in_either_mode(mode):
    """How an eval arm pins a model regardless of the environment it runs in."""
    with _env(**mode, OPENAI_MODEL="gpt-4.1-nano") as cfg:
        assert cfg.OPENAI_MODEL == "gpt-4.1-nano"


def test_config_is_restored_after_reload():
    """The fixture's own guarantee — a stale module here would mislead every
    later test that reads config."""
    assert config.OPENAI_MODEL == "gpt-4.1-nano"  # conftest sets DEV_MODE=1
