from uuid import UUID
from pydantic import BaseModel, EmailStr, field_serializer


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    username: str | None = None


class LoginRequest(BaseModel):
    identifier: str  # email or username
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    email: str
    username: str | None
    full_name: str | None
    role: str
    is_active: bool

    @field_serializer("id")
    def serialize_id(self, v: UUID) -> str:
        return str(v)

    class Config:
        from_attributes = True
