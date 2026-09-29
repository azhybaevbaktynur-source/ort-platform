from enum import Enum
from typing import Optional, Dict
from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"


class TargetScore(BaseModel):
    overall: int = Field(default=200, ge=60, le=245, description="Target total scaled ORT score")
    math: int = Field(default=50, ge=10, le=60)
    reading: int = Field(default=25, ge=5, le=30)
    grammar: int = Field(default=25, ge=5, le=30)
    analogies: int = Field(default=25, ge=5, le=30)


class StreakInfo(BaseModel):
    current: int = 0
    longest: int = 0
    lastActiveDate: Optional[str] = None


class UserBase(BaseModel):
    email: EmailStr
    displayName: str
    role: UserRole = UserRole.STUDENT
    preferredLanguage: str = Field(default="ky", pattern="^(ky|ru)$")


class UserCreate(UserBase):
    firebaseUid: Optional[str] = None


class UserProfile(UserBase):
    id: str
    targetScore: TargetScore = Field(default_factory=TargetScore)
    target_score: Optional[int] = Field(default=200, ge=60, le=245)
    currentEstimatedScore: int = 150
    streak: StreakInfo = Field(default_factory=StreakInfo)
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="Password at least 6 characters")
    displayName: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user: UserProfile


class TargetScoreUpdate(BaseModel):
    overall: Optional[int] = Field(None, ge=60, le=245)
    math: Optional[int] = Field(None, ge=10, le=60)
    reading: Optional[int] = Field(None, ge=5, le=30)
    grammar: Optional[int] = Field(None, ge=5, le=30)
    analogies: Optional[int] = Field(None, ge=5, le=30)


class TargetScoreUpdatePayload(BaseModel):
    target_score: Optional[int] = Field(None, ge=60, le=245)
    overall: Optional[int] = Field(None, ge=60, le=245)
