import uuid
from typing import List, Optional, Literal

import jwt
from pydantic import BaseModel, EmailStr, Field

class Usage(BaseModel):
    used: int
    remaining: int
    max: int

class Record(BaseModel):
    file: str          # relative path, e.g. "experience/company-a.md"
    type: str          # "experience" | "project" | "skill"
    title: str         # e.g. "Senior Engineer @ Acme Corp"
    tags: List[str] = []
    dates: Optional[str] = None
    summary: Optional[str] = None  # 1-liner shown in search results before full fetch
    skill_notes: dict = {}  # optional {tag: "scope/caveat note"}, e.g.
                            # {"kubernetes": "Deployed existing services; did not design cluster architecture."}

class ChatRequest(BaseModel):
    message: str
    history: list = []  # [{"role": "user"/"assistant"/"tool", ...}]

class IssueTokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    # 60s minimum (anything shorter is basically useless) up to 90 days.
    expires_in_seconds: int = Field(default=60 * 60 * 24 * 7, ge=60, le=60 * 60 * 24 * 90)
    max_queries: int = Field(default=20, ge=1, le=1000)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    job_title: str | None = Field(default=None, max_length=255)
    type: Literal["token", "qr"] = "token"

class ChatResponse(BaseModel):
    type: str | None = None
    reply: str
    history: list[dict]
    usage: Usage

class TokenContext(BaseModel):
    sub: str
    jti: str
    max_queries: int
    used_queries: int
    remaining_queries: int

class JWT(BaseModel):
    sub: str # Freetext: currently used as identifier by the chatbot
    iat: int
    exp: int
    # default_factory so each instance gets its own jti; using
    # `str(uuid.uuid4())` as a bare default fires once at class-definition
    # time and every JWT() would share that same id.
    jti: str = Field(default_factory=lambda: str(uuid.uuid4()))
    max_queries: int = 20

    def generate(self, secret_key: str, algorithm: str) -> str:
        return jwt.encode(self.model_dump(), secret_key, algorithm=algorithm)

