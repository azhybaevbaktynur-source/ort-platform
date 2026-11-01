import unicodedata
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

DISPLAY_NAME_MAX = 100


def _no_control_chars(value: Optional[str]) -> Optional[str]:
    """Display names reach email headers and other users' screens: no control characters (CR/LF, tabs, NUL...)."""
    if value is not None and any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("displayName must not contain control characters")
    return value


class UserProfile(BaseModel):
    id: str
    email: str  # a response: a test student's reserved `.invalid` address is not an EmailStr (requests keep EmailStr)
    displayName: str
    phone: Optional[str] = None
    preferredLanguage: str = Field(default="ky", pattern="^(ky|ru)$")
    is_platform_admin: bool = False
    teacher_status: str = "none"
    locale: Optional[str] = None
    is_test_student: bool = False
    is_guardian: bool = False  # Phase 11: an active guardian link from the database


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="Password at least 6 characters")
    displayName: Optional[str] = Field(None, max_length=DISPLAY_NAME_MAX)
    phone: Optional[str] = None
    lang: Optional[str] = Field("ky", pattern="^(en|ky|ru)$", description="Language of the verification email")
    # Phase 11 S1 (PHASE_11_DESIGN 3.2): checked in the route, so a missing band answers 422 `age_band_required`
    ageBand: Optional[str] = Field(None, max_length=16)
    policyVersionIds: Optional[List[str]] = Field(None, max_length=10)

    @field_validator("displayName")
    @classmethod
    def _display_name_clean(cls, value: Optional[str]) -> Optional[str]:
        return _no_control_chars(value)


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
    lang: Optional[str] = Field("ky", pattern="^(en|ky|ru)$")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    lang: Optional[str] = Field("ky", pattern="^(en|ky|ru)$")


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6, description="New password at least 6 characters")


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
    lang: Optional[str] = Field("ky", pattern="^(en|ky|ru)$", description="Language of a verification email, if one is needed")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile
