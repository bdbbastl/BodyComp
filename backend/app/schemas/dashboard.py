"""Response-Schema für das Coach-Dashboard-Widget-Layout - siehe
Design-Spec "Coach-Dashboard: 4-Widget-Layout"."""
from datetime import datetime

from pydantic import BaseModel


class PendingCheckinSummary(BaseModel):
    id: int
    client_id: int
    client_name: str
    submitted_at: datetime
    weight_kg: float | None


class NeedsAttentionClient(BaseModel):
    client_id: int
    client_name: str
    days_since_activity: int | None  # None = noch nie Aktivität


class WeekStats(BaseModel):
    checkins: int
    photos: int
    active_clients: int


class CoachDashboardSummary(BaseModel):
    pending_checkins: list[PendingCheckinSummary]
    needs_attention: list[NeedsAttentionClient]
    week_stats: WeekStats
