import json
import logging.config
from pathlib import Path

from app.common.config import DEV_MODE


def load_logging_config():
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    logging.config.dictConfig(config)
    # config.json pins DEBUG so local dev sees everything; in prod that would
    # log full chat transcripts at INFO, so cap it there.
    logging.getLogger().setLevel(logging.DEBUG if DEV_MODE else logging.INFO)

load_logging_config()
logger = logging.getLogger(__name__)
