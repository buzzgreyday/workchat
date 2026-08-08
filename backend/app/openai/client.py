from functools import lru_cache

from openai import AsyncOpenAI

from app.common.config import OPENAI_API_KEY


@lru_cache  # first call caches the client; FastAPI dependency picks it up as a singleton.
def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=OPENAI_API_KEY)