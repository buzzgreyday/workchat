import os
from pathlib import Path

from dotenv import load_dotenv


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} not found or empty in environment variables")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


## Paths
# config.py lives at backend/app/common/config.py, so three parents up is backend/.
BACKEND_DIR = Path(__file__).parent.parent.parent.resolve()
RESOURCES_DIR = BACKEND_DIR / "resources"
# Env overrides let tests point these at fixture files.
INDEX_PATH = Path(os.environ.get("INDEX_PATH") or (RESOURCES_DIR / "index.json"))
SYSTEM_PROMPT_PATH = Path(os.environ.get("SYSTEM_PROMPT_PATH") or (RESOURCES_DIR / "system-prompt.md"))

# Load environment
load_dotenv(BACKEND_DIR / ".env")

## Modes
DEV_MODE = env_bool("DEV_MODE", default=False)

## Database
POSTGRES_USER = require_env("POSTGRES_USER")
POSTGRES_PASSWORD = require_env("POSTGRES_PASSWORD")
POSTGRES_DB = require_env("POSTGRES_DB")

## URLs
BASE_URL = "http://localhost:8000" if DEV_MODE else require_env("BASE_URL")
DATABASE_URL = f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@db:5432/{POSTGRES_DB}"
ALLOWED_HOSTS = ["*"] if DEV_MODE else [h.strip() for h in require_env("ALLOWED_HOSTS").split(",") if h.strip()]

## Secrets and hashing
OPENAI_API_KEY = require_env("OPENAI_API_KEY")
TOKEN_HASHING_SECRET = require_env("TOKEN_HASHING_SECRET")
SECRET_KEY = require_env("JWT_SECRET")
ADMIN_KEY = require_env("ADMIN_KEY")
ALGORITHM = "HS256"

## LLM
OPENAI_MODEL = "gpt-4.1-nano"
# Cap on tool-call round trips per user message. Each round is a paid API call, so an
# unbounded loop on a model that keeps requesting tools would burn quota indefinitely.
MAX_TOOL_ROUNDS = 5
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text()
except FileNotFoundError:
    raise ValueError(f"system prompt not found at {SYSTEM_PROMPT_PATH}")
if not SYSTEM_PROMPT.strip():
    raise ValueError(f"system prompt at {SYSTEM_PROMPT_PATH} is empty")