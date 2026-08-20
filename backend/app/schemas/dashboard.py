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


class DayCount(BaseModel):
    date: str  # ISO date "YYYY-MM-DD"
    count: int


class WeekCount(BaseModel):
    week_start: str  # ISO date (Monday) "YYYY-MM-DD"
    count: int


class ActivityItem(BaseModel):
    type: str  # "checkin_submitted" | "checkin_reviewed" | "client_added"
    client_id: int
    client_name: str
    timestamp: datetime


class CoachDashboardSummary(BaseModel):
    pending_checkins: list[PendingCheckinSummary]
    needs_attention: list[NeedsAttentionClient]
    week_stats: WeekStats
    active_clients_last_7_days: list[DayCount]
    checkins_per_week: list[WeekCount]
    activity_feed: list[ActivityItem]
