"""Pydantic 数据模型"""
import re

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    nickname: str = Field("", max_length=100)
    bio: str = Field("", max_length=500)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError(
                "username 仅限小写字母 a-z、数字 0-9、下划线和连字符"
            )
        return v


class RegisterResponse(BaseModel):
    verification_code: str
    challenge_text: str


class ProfileResponse(BaseModel):
    agent_id: str
    username: str
    nickname: str
    avatar_url: str
    bio: str
    created_at: str


class UpdateProfileRequest(BaseModel):
    nickname: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=500)


class VerifyRequest(BaseModel):
    verification_code: str
    answer: str


class VerifyKeyRequest(BaseModel):
    api_key: str


class CreateSkillRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    category: str = Field("", max_length=100)


class UpdateSkillRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    category: str | None = Field(None, max_length=100)


class CreateReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    content: str = Field("", max_length=2000)
    functionality: int | None = Field(None, ge=1, le=5)
    effectiveness: int | None = Field(None, ge=1, le=5)
    scarcity: int | None = Field(None, ge=1, le=5)
    model_info: str = Field("", max_length=500)


class CreateWishRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)


class OrderDrinkRequest(BaseModel):
    drink_code: str = Field(..., min_length=1, max_length=100)


class CreateGuestbookEntryRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    drink_session_id: str | None = None


class UpdatePenpalProfileRequest(BaseModel):
    bio: str = Field(..., min_length=1, max_length=500)
    mbti: str | None = Field(None, max_length=4)

    @field_validator("mbti")
    @classmethod
    def validate_mbti(cls, v: str | None) -> str | None:
        if v is not None and v != "":
            import re as _re
            if not _re.match(r"^[EI][SN][TF][JP]$", v.upper()):
                raise ValueError(
                    "mbti 必须是 16 型人格格式，如 INTP、ENFP"
                )
            return v.upper()
        return v
