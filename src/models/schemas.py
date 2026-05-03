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
