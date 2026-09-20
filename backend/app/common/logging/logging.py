import json
import logging.config
import os
from pathlib import Path


def load_logging_config():
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    logging.config.dictConfig(config)
    # config.json pins DEBUG so local dev sees everything; in prod that would
    # log full chat transcripts at INFO, so cap it there.
    #
    # DEV_MODE is read from the environment directly rather than through
    # get_settings(). This runs at import — handlers have to exist before
    # anything logs — and get_settings() reads every secret the app has and
    # raises if one is missing. Making the logger unavailable until the whole
    # configuration validates would mean a misconfiguration could not be logged,
    # which is precisely when you want a log line.
    dev_mode = (os.environ.get("DEV_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
    logging.getLogger().setLevel(logging.DEBUG if dev_mode else logging.INFO)

load_logging_config()
logger = logging.getLogger(__name__)
