"""
Configuration, read once and handed out as an object.

Nothing here runs at import. That is the whole point of the shape: `Settings`
is built by `get_settings()` on first call, so importing any module in this
application cannot raise because an environment variable is missing, and a test
can set the environment in a fixture instead of before its own imports.

It used to be a page of module-level constants, several of them calling
`require_env`, plus a file read for the system prompt. Importing `app.main`
therefore demanded a fully configured environment, which is why `conftest.py`
had to set seven variables above its own import block and mark every import
below it `# noqa: E402`.

The values that depend on no environment stay module constants, because they
are facts about the application rather than settings: the algorithm the tokens
are signed with, the cap on tool rounds, the cookie path.
"""

import hashlib
import hmac
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} not found or empty in environment variables")
    return value


def env_list(name: str) -> list[str]:
    """Comma-separated env var to a list, dropping blanks. Absent or empty gives
    an empty list, so a caller can tell "unset" from "set to something"."""
    return [v.strip() for v in (os.environ.get(name) or "").split(",") if v.strip()]


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


## Facts, not settings — no environment is consulted for any of these.
# config.py lives at backend/app/common/config.py, so three parents up is backend/.
BACKEND_DIR = Path(__file__).parent.parent.parent.resolve()
ALGORITHM = "HS256"
# Cap on tool-call round trips per user message. Each round is a paid API call, so an
# unbounded loop on a model that keeps requesting tools would burn quota indefinitely.
MAX_TOOL_ROUNDS = 5
# The longest question anyone may ask, in characters. A question about a CV is a
# sentence or two; anything longer is more often an attempt to paste a prompt in
# than a question, and every character is paid for again on every later turn,
# since the history goes back to the model each time. Only the question being
# asked is held to it: the replies, and the history they build up, are as long
# as they need to be. The frontend's composer mirrors this number
# (frontend/src/lib/limits.ts); change both together.
MAX_MESSAGE_CHARS = 150
# Path "/" rather than "/v2/auth" on purpose: behind Caddy the browser sees
# /api/v2/auth/... while the backend only ever sees /v2/auth/..., so a narrow
# path would be written for a prefix the browser never requests.
REFRESH_COOKIE_PATH = "/"
# Browsers refuse a credentialed request whose Access-Control-Allow-Origin is
# "*", so the dev wildcard has to become a concrete list once cookies are in play.
DEV_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
# Not on Settings, because `/v2/auth/refresh` declares it as a Cookie alias and
# FastAPI builds a route's parameter model when the route is declared — the name
# has to be known at import or not at all. Reading it here is still import-safe:
# an optional variable with a default cannot fail the way require_env can.
REFRESH_COOKIE_NAME = os.environ.get("REFRESH_COOKIE_NAME") or "cv_refresh"


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything this application reads from its environment."""

    # --- paths ---
    resources_dir: Path
    system_prompt_path: Path
    system_prompt: str

    # --- modes ---
    dev_mode: bool
    # Chat content lives in Postgres, which has a retention policy and a redaction
    # path. Logs have neither — they are an unencrypted Docker ring buffer — so
    # message text stays out of them unless this is deliberately switched on for
    # local debugging.
    log_chat_content: bool
    # SQLAlchemy's echo writes every statement and its bound parameters to the log,
    # which on the issue-token path means a hirer's email and phone and the grant's
    # token_hash. Those are values the rest of this codebase keeps out of logs, and
    # echo puts them in the log *message* rather than in extra={}, where
    # RedactionFilter cannot reach them. So it is its own opt-in rather than riding
    # on dev_mode, which had every local session logging them by default.
    sql_echo: bool

    # --- retention ---
    # Read by scripts/purge-chat-content.sh rather than by this application; kept
    # here so the default the script assumes is stated once, in Python, where the
    # rest of the configuration lives.
    chat_retention_days: int

    # --- urls ---
    base_url: str
    database_url: str
    cors_origins: list[str]

    # --- secrets ---
    openai_api_key: str
    token_hashing_secret: str
    secret_key: str
    admin_key: str
    # Signs the history the server hands back each turn, so a client can only
    # send back a history the server produced (services/chat/history.py).
    # Without it the history is whatever the client says it is — padded,
    # rewritten, or long fake "earlier questions" that cost a model call each.
    # Optional: unset, it is derived from JWT_SECRET under its own label, so a
    # deployment that predates it keeps starting. Setting it separates the two,
    # and rotating it only drops the conversations in flight to a fresh start.
    history_signing_secret: str

    # --- guest trial (services/trial) ---
    # Off unless switched on: a visitor without a link can then ask a few
    # questions after an invisible proof-of-work, once per IP per day, within a
    # daily ceiling on trials. Every number below bounds a cost; together they
    # are the most a day of strangers can spend: daily_limit x max_queries.
    trial_enabled: bool
    # Required only while trials are on. The root of the keys trials use — one
    # for signing proof-of-work challenges, one per UTC day for hashing IPs —
    # each derived with its own label, so neither can stand in for the other.
    trial_secret: str | None
    trial_max_queries: int
    # How long a trial grant lives, after which it is spent whatever is left.
    trial_ttl_seconds: int
    # Trials across everyone, per UTC day.
    trial_daily_limit: int
    # The proof-of-work's difficulty: the search space a browser covers to find
    # the answer, on average half of it. 100 000 SHA-256 rounds is well under a
    # second in a worker on a phone, and a real cost to a script asking for a
    # thousand trials.
    trial_pow_max_number: int
    # Whether the client's address may be read from X-Forwarded-For. True only
    # behind the Caddy this repo ships, which sets that header itself and is the
    # only way in; anywhere the backend's port is reachable directly — dev
    # publishes 8000 — the header is whatever the client chose to send.
    trust_proxy_headers: bool

    # --- token lifetimes (v2 claim/refresh/access flow) ---
    # A v1 token is the whole grant: one long-lived JWT handed out in a link, valid
    # until the grant expires. v2 splits that into a claim link the hirer exchanges,
    # a refresh token that survives a closed tab, and an access token short enough
    # that a leaked URL or log line goes stale on its own. Neither derived token can
    # outlive its grant — Auth clamps both to tokens.expires_at when minting.
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    # How long a just-rotated refresh token is still recognised as *this* client
    # retrying rather than someone replaying a stolen token. Without a window, three
    # chat requests expiring at once and each retrying a refresh would be read as two
    # replays and cut the grant — the client locks itself out. Measured from the
    # moment of rotation; a token presented after it is a genuine replay.
    refresh_rotation_grace_seconds: int
    # At most one operator notification per grant per window, so a bot hitting a dead
    # claim link cannot flood the log (or, later, an inbox).
    owner_notify_throttle_seconds: int

    # --- refresh cookie ---
    refresh_cookie_secure: bool

    # --- llm ---
    # Measured, not assumed: on 26 eval questions x 3 runs, nano scored 22-24 and
    # mini 25-26, taking every depth question in every run. nano also never once
    # worked out how long a role has run, answering "since September 2025" to "how
    # long" in every arm tried; mini gets it right most runs. Roughly 4x nano's
    # input price and about a second slower per answer, which at a 20-query token
    # per hiring manager is a latency decision rather than a cost one.
    #
    # So mini is what a hirer gets, and nano is the default while dev_mode is on.
    # That is not a reversal of the measurement above — locally the question being
    # asked is "does the tool round-trip work", not "is the answer good", and a
    # reload loop against a paid endpoint is an easy way to spend real money on
    # answers nobody reads.
    #
    # Set OPENAI_MODEL to override either default. That is also how to run an eval
    # arm against a specific model: run_eval.py drives the running server and only
    # reads this value to label its report, so the arm is whatever the server was
    # started with.
    openai_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Read the environment, `backend/.env` included.

        `load_dotenv` runs *first*, which it did not before: `RESOURCES_DIR` and
        `SYSTEM_PROMPT_PATH` were computed above the `load_dotenv()` call, so
        neither could ever be set from `backend/.env` — only from the real
        environment. Setting them there now works.
        """
        load_dotenv(BACKEND_DIR / ".env")

        dev_mode = env_bool("DEV_MODE", default=False)
        # Resolved rather than taken as given: CVSearch guards traversal by asking
        # whether this directory is among a path's resolved parents, and a path
        # with a symlink in it would fail that for every record in the corpus.
        resources_dir = Path(os.environ.get("RESOURCES_DIR") or (BACKEND_DIR / "resources")).resolve()
        system_prompt_path = Path(
            os.environ.get("SYSTEM_PROMPT_PATH") or (resources_dir / "system-prompt.md")
        )

        postgres_user = require_env("POSTGRES_USER")
        postgres_password = require_env("POSTGRES_PASSWORD")
        postgres_db = require_env("POSTGRES_DB")

        trial_enabled = env_bool("TRIAL_ENABLED", default=False)

        allowed_hosts = (
            ["*"] if dev_mode
            else [h.strip() for h in require_env("ALLOWED_HOSTS").split(",") if h.strip()]
        )

        return cls(
            resources_dir=resources_dir,
            system_prompt_path=system_prompt_path,
            system_prompt=cls._read_system_prompt(system_prompt_path),
            dev_mode=dev_mode,
            log_chat_content=env_bool("LOG_CHAT_CONTENT", default=False),
            sql_echo=env_bool("SQL_ECHO", default=False),
            chat_retention_days=int(os.environ.get("CHAT_RETENTION_DAYS") or 30),
            base_url="http://localhost:8000" if dev_mode else require_env("BASE_URL"),
            # The host is `db`, the compose service name, which only resolves inside
            # the compose network. The override is for everything outside it —
            # running alembic from the host, pointing a migration rehearsal at a
            # scratch database — and is never set in production, where the assembled
            # default is what you want.
            database_url=(
                os.environ.get("DATABASE_URL")
                or f"postgresql+psycopg://{postgres_user}:{postgres_password}@db:5432/{postgres_db}"
            ),
            cors_origins=_dev_cors_origins() if dev_mode else allowed_hosts,
            openai_api_key=require_env("OPENAI_API_KEY"),
            token_hashing_secret=require_env("TOKEN_HASHING_SECRET"),
            secret_key=require_env("JWT_SECRET"),
            admin_key=require_env("ADMIN_KEY"),
            history_signing_secret=(
                os.environ.get("HISTORY_SIGNING_SECRET")
                or _derive(require_env("JWT_SECRET"), "history")
            ),
            trial_enabled=trial_enabled,
            trial_secret=require_env("TRIAL_SECRET") if trial_enabled else None,
            trial_max_queries=int(os.environ.get("TRIAL_MAX_QUERIES") or 3),
            trial_ttl_seconds=int(os.environ.get("TRIAL_TTL_SECONDS") or 60 * 60 * 24),
            trial_daily_limit=int(os.environ.get("TRIAL_DAILY_LIMIT") or 50),
            trial_pow_max_number=int(os.environ.get("TRIAL_POW_MAX_NUMBER") or 100_000),
            trust_proxy_headers=env_bool("TRUST_PROXY_HEADERS", default=False),
            access_token_ttl_seconds=int(os.environ.get("ACCESS_TOKEN_TTL_SECONDS") or 60 * 15),
            refresh_token_ttl_seconds=int(os.environ.get("REFRESH_TOKEN_TTL_SECONDS") or 60 * 60 * 24 * 7),
            refresh_rotation_grace_seconds=int(os.environ.get("REFRESH_ROTATION_GRACE_SECONDS") or 30),
            owner_notify_throttle_seconds=int(os.environ.get("OWNER_NOTIFY_THROTTLE_SECONDS") or 60 * 60),
            # No Secure flag in dev, where the frontend is plain http on localhost.
            refresh_cookie_secure=not dev_mode,
            openai_model=os.environ.get("OPENAI_MODEL") or ("gpt-4.1-nano" if dev_mode else "gpt-4.1-mini"),
        )

    @staticmethod
    def _read_system_prompt(path: Path) -> str:
        try:
            prompt = path.read_text()
        except FileNotFoundError:
            raise ValueError(f"system prompt not found at {path}")
        if not prompt.strip():
            raise ValueError(f"system prompt at {path} is empty")
        return prompt


def _derive(secret: str, label: str) -> str:
    """
    A key for one purpose, from a secret kept for another.

    HMAC under a label, so the derived key reveals nothing about the secret and
    a key derived for one label is useless for any other.
    """
    return hmac.new(secret.encode(), f"workchat:{label}".encode(), hashlib.sha256).hexdigest()


def _dev_cors_origins() -> list[str]:
    """
    The dev origins, plus anything in ALLOWED_HOSTS that is actually an origin.

    A union rather than an override, because ALLOWED_HOSTS in a dev .env is not
    necessarily a CORS origin at all — a domain pattern like `*.example.com` is a
    perfectly reasonable thing to have in there, and letting it *replace* the
    defaults would leave localhost unable to talk to the API at all. Entries
    without a scheme are skipped for the same reason: Starlette matches
    allow_origins by exact string, so a pattern would never match an Origin
    header and only crowds the list.
    """
    extra = [
        origin for origin in env_list("ALLOWED_HOSTS")
        if "://" in origin and origin not in DEV_ALLOWED_ORIGINS
    ]
    return DEV_ALLOWED_ORIGINS + extra


@lru_cache
def get_settings() -> Settings:
    """
    The settings, built on first call and kept.

    Cached rather than re-read because the environment does not change under a
    running process, and because two callers disagreeing about a secret would be
    worse than either answer. Tests that need a different environment call
    `get_settings.cache_clear()`.
    """
    return Settings.from_env()