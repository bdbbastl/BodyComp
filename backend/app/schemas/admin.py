"""Schemas für den Master-Admin-Bereich - siehe Design-Spec
"Master-Admin-Dashboard". Alle Endpunkte, die diese Schemas nutzen,
liegen hinter require_admin (app/routers/auth.py)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.user import AccountType


class AdminOverviewOut(BaseModel):
    total_accounts: int
    single_accounts: int
    coach_accounts: int
    active_subscriptions: int
    signups_this_week: int
    signups_this_month: int


class AdminAccountOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType
    created_at: datetime
    subscription_status: str | None
    subscription_tier: str | None
    client_count: int
    is_active: bool
    is_admin: bool
    last_activity_at: datetime | None
    activity_status: Literal["active", "inactive", "never"]

    class Config:
        from_attributes = True


class AdminClientSummaryOut(BaseModel):
    id: int
    name: str
    photo_count: int
    last_activity_at: datetime | None


class AdminAccountDetailOut(AdminAccountOut):
    clients: list[AdminClientSummaryOut]
    total_checkins: int
    total_storage_bytes: int
    photos_with_unknown_size: int


class AdminSetActiveRequest(BaseModel):
    is_active: bool


class AdminInvoiceOut(BaseModel):
    amount: float
    currency: str
    paid_at: datetime | None
    status: str


class AdminBillingOut(BaseModel):
    has_stripe_customer: bool
    subscription_id: str | None
    next_billing_date: datetime | None
    recent_invoices: list[AdminInvoiceOut]
