from datetime import date as date_, datetime

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    height_cm: float | None = None
    birth_date: date_ | None = None
    gender: str | None = None
    start_date: date_ | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    height_cm: float | None = None
    birth_date: date_ | None = None
    gender: str | None = None
    start_date: date_ | None = None
    coach_private_note: str | None = None
    email: str | None = None
    checkin_reminder_days: int | None = None


class ClientOut(BaseModel):
    id: int
    name: str
    height_cm: float | None
    birth_date: date_ | None
    gender: str | None
    start_date: date_ | None
    created_at: datetime
    photo_count: int
    last_activity: date_ | None
    pending_checkins_count: int
    checkin_token: str
    coach_private_note: str | None
    email: str | None
    checkin_reminder_days: int | None

    class Config:
        from_attributes = True
