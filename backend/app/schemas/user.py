from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserProfile(BaseModel):
    id: str
    email: EmailStr
    displayName: str
    phone: Optional[str] = None
    preferredLanguage: str = Field(default="ky", pattern="^(ky|ru)$")
    is_platform_admin: bool = False
    teacher_status: str = "none"
    locale: Optional[str] = None


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="Password at least 6 characters")
    displayName: Optional[str] = None
    phone: Optional[str] = None
    lang: Optional[str] = Field("ky", pattern="^(ky|ru)$", description="Language of the verification email")


class RegisterResponse(BaseModel):
    """Registration does not log the user in: they must first enter the code emailed to them."""
    verificationRequired: bool = True
    email: str
    resendAfterSeconds: int
    codeTtlMinutes: int


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    password: str
    code: str = Field(min_length=4, max_length=12)


class ResendCodeRequest(BaseModel):
    email: EmailStr
    lang: Optional[str] = Field("ky", pattern="^(ky|ru)$")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    lang: Optional[str] = Field("ky", pattern="^(ky|ru)$")


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6, description="New password at least 6 characters")


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
    lang: Optional[str] = Field("ky", pattern="^(ky|ru)$", description="Language of a verification email, if one is needed")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile
