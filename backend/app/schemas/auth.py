from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    # Role is assigned server-side; never trust it from the client (privilege
    # escalation). It is intentionally not a field here.
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
