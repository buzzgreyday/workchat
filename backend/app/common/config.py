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
# Chat content lives in Postgres, which has a retention policy and a redaction
# path. Logs have neither — they are an unencrypted Docker ring buffer — so
# message text stays out of them unless this is deliberately switched on for
# local debugging.
LOG_CHAT_CONTENT = env_bool("LOG_CHAT_CONTENT", default=False)

## Retention
# Days before chat message content is scrubbed by scripts/purge-chat-content.sh.
# The row, its counts and its timings survive; only the text is nulled.
CHAT_RETENTION_DAYS = int(os.environ.get("CHAT_RETENTION_DAYS") or 30)

## Database
POSTGRES_USER = require_env("POSTGRES_USER")
POSTGRES_PASSWORD = require_env("POSTGRES_PASSWORD")
POSTGRES_DB = require_env("POSTGRES_DB")

## URLs
BASE_URL = "http://localhost:8000" if DEV_MODE else require_env("BASE_URL")
# The host is `db`, the compose service name, which only resolves inside the
# compose network. The override is for everything outside it — running alembic
# from the host, pointing a migration rehearsal at a scratch database — and is
# never set in production, where the assembled default is what you want.
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@db:5432/{POSTGRES_DB}"
)
ALLOWED_HOSTS = ["*"] if DEV_MODE else [h.strip() for h in require_env("ALLOWED_HOSTS").split(",") if h.strip()]

## Secrets and hashing
OPENAI_API_KEY = require_env("OPENAI_API_KEY")
TOKEN_HASHING_SECRET = require_env("TOKEN_HASHING_SECRET")
SECRET_KEY = require_env("JWT_SECRET")
ADMIN_KEY = require_env("ADMIN_KEY")
ALGORITHM = "HS256"

## Token lifetimes (v2 claim/refresh/access flow)
# A v1 token is the whole grant: one long-lived JWT handed out in a link, valid
# until the grant expires. v2 splits that into a claim link the hirer exchanges,
# a refresh token that survives a closed tab, and an access token short enough
# that a leaked URL or log line goes stale on its own. Neither derived token can
# outlive its grant — Auth clamps both to tokens.expires_at when minting.
ACCESS_TOKEN_TTL_SECONDS = int(os.environ.get("ACCESS_TOKEN_TTL_SECONDS") or 60 * 15)
REFRESH_TOKEN_TTL_SECONDS = int(os.environ.get("REFRESH_TOKEN_TTL_SECONDS") or 60 * 60 * 24 * 7)
# How long a just-rotated refresh token is still recognised as *this* client
# retrying rather than someone replaying a stolen token. Without a window, three
# chat requests expiring at once and each retrying a refresh would be read as two
# replays and cut the grant — the client locks itself out. Measured from the
# moment of rotation; a token presented after it is a genuine replay.
REFRESH_ROTATION_GRACE_SECONDS = int(os.environ.get("REFRESH_ROTATION_GRACE_SECONDS") or 30)
# At most one operator notification per grant per window, so a bot hitting a dead
# claim link cannot flood the log (or, later, an inbox).
OWNER_NOTIFY_THROTTLE_SECONDS = int(os.environ.get("OWNER_NOTIFY_THROTTLE_SECONDS") or 60 * 60)

## Refresh cookie
# The refresh token is delivered as an httpOnly cookie and never in a response
# body, so script on the page cannot read it. In production Caddy serves the
# frontend and proxies the API under /api on one origin, so this is a plain
# same-origin cookie; in dev :3000 and :8000 differ in port but not in site, so
# SameSite=Strict still sends it once CORS allows credentials.
REFRESH_COOKIE_NAME = os.environ.get("REFRESH_COOKIE_NAME") or "cv_refresh"
# Path "/" rather than "/v2/auth" on purpose: behind Caddy the browser sees
# /api/v2/auth/... while the backend only ever sees /v2/auth/..., so a narrow
# path would be written for a prefix the browser never requests.
REFRESH_COOKIE_PATH = "/"
# No Secure flag in dev, where the frontend is plain http on localhost.
REFRESH_COOKIE_SECURE = not DEV_MODE
# Browsers refuse a credentialed request whose Access-Control-Allow-Origin is
# "*", so the dev wildcard has to become a concrete list once cookies are in play.
DEV_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
CORS_ORIGINS = DEV_ALLOWED_ORIGINS if DEV_MODE else ALLOWED_HOSTS

## LLM
# Measured, not assumed: on 26 eval questions x 3 runs, nano scored 22-24 and
# mini 25-26, taking every depth question in every run. nano also never once
# worked out how long a role has run, answering "since September 2025" to "how
# long" in every arm tried; mini gets it right most runs. Roughly 4x nano's
# input price and about a second slower per answer, which at a 20-query token
# per hiring manager is a latency decision rather than a cost one.
OPENAI_MODEL = "gpt-4.1-mini"
# Cap on tool-call round trips per user message. Each round is a paid API call, so an
# unbounded loop on a model that keeps requesting tools would burn quota indefinitely.
MAX_TOOL_ROUNDS = 5
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text()
except FileNotFoundError:
    raise ValueError(f"system prompt not found at {SYSTEM_PROMPT_PATH}")
if not SYSTEM_PROMPT.strip():
    raise ValueError(f"system prompt at {SYSTEM_PROMPT_PATH} is empty")