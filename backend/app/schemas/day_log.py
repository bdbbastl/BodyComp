from datetime import date as date_

from pydantic import BaseModel, field_validator

from app.utils.weight import parse_weight_kg


class DayLogUpsert(BaseModel):
    date: date_
    weight_kg: float | None = None
    notes: str | None = None

    @field_validator("weight_kg", mode="before")
    @classmethod
    def _parse_weight(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        try:
            return parse_weight_kg(v)
        except ValueError:
            raise ValueError("weight_kg must be a number (comma or dot as decimal separator)")


class DayLogOut(BaseModel):
    id: int
    date: date_
    weight_kg: float | None
    notes: str | None

    class Config:
        from_attributes = True
