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
    created_at: datetime
    # Nicht Teil der API-Antwort (exclude=True) - nur intern gelesen, damit
    # `has_password` unten berechnet werden kann. Das Frontend braucht das,
    # um z.B. bei der Konto-Löschung das Passwortfeld nur bei Accounts mit
    # Passwort anzuzeigen (Google-only-Accounts haben keins).
    password_hash: str | None = Field(default=None, exclude=True)
    # Analog zu password_hash - roh nicht Teil der Antwort, nur zur
    # Berechnung von has_google_account. Steuert im Frontend, ob der
    # E-Mail-Änderungsbereich angezeigt wird (Google-Accounts loggen sich
    # über Google ein, eine eigene E-Mail-Änderung ergibt da keinen Sinn).
    google_id: str | None = Field(default=None, exclude=True)
    subscription_status: str | None
    subscription_tier: str | None
    trial_ends_at: datetime | None
    free_checkins_used: int
    onboarding_completed_at: datetime | None

    class Config:
        from_attributes = True

    @computed_field
    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @computed_field
    @property
    def has_google_account(self) -> bool:
        return self.google_id is not None
