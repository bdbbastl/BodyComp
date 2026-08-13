from datetime import date as date_

from pydantic import BaseModel


class DayLogUpsert(BaseModel):
    date: date_
    weight_kg: float | None = None
    notes: str | None = None


class DayLogOut(BaseModel):
    id: int
    date: date_
    weight_kg: float | None
    notes: str | None

    class Config:
        from_attributes = True
