from datetime import datetime

from app.models.user import AccountType
from pydantic import BaseModel, EmailStr, Field, computed_field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType
    # Nicht Teil der API-Antwort (exclude=True) - nur intern gelesen, damit
    # `has_password` unten berechnet werden kann. Das Frontend braucht das,
    # um z.B. bei der Konto-Löschung das Passwortfeld nur bei Accounts mit
    # Passwort anzuzeigen (Google-only-Accounts haben keins).
    password_hash: str | None = Field(default=None, exclude=True)
    subscription_status: str | None
    subscription_tier: str | None
    trial_ends_at: datetime | None
    free_checkins_used: int

    class Config:
        from_attributes = True

    @computed_field
    @property
    def has_password(self) -> bool:
        return self.password_hash is not None
