from datetime import datetime

from pydantic import BaseModel, Field


class PoseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PoseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None


class PoseOut(BaseModel):
    id: int
    name: str
    sort_order: int
    created_at: datetime

    class Config:
        from_attributes = True
