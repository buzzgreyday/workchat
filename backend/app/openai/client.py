from functools import lru_cache

from openai import AsyncOpenAI

from app.common.config import get_settings


@lru_cache  # first call caches the client; FastAPI dependency picks it up as a singleton.
def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)