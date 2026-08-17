# backend/app/services/billing.py
"""
Reine, netzwerkfreie Billing-Limit-Logik - siehe Design-Spec
Abschnitt "Limit-Durchsetzung". Alle Stripe-Netzwerk-Aufrufe (Checkout,
Portal, Webhook) leben in routers/billing.py; hier steht nur die
Entscheidungslogik "darf dieser Account das gerade tun", damit sie ohne
Mocking testbar ist.
"""
import logging

from app.models.client import Client
from app.models.user import AccountType, User
from app.services.email import send_quota_warning_email
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Fest im Code ausgenommener Betreiber-Account - siehe Design-Spec
# Abschnitt "Ausnahme: Betreiber-Account". Bewusst eine Code-Konstante,
# kein DB-Flag - für diesen einen bekannten Sonderfall ausreichend.
EXEMPT_EMAILS = {"basti.auer@outlook.com"}

# None = unbegrenzt. Ein Account OHNE aktives Abo (Status weder
# "trialing" noch "active") bekommt effektiv Limit 1 - das entspricht
# genau dem automatisch bei Account-Erstellung angelegten Client, ohne
# dass ein unbezahlter Coach-Account weitere Klienten anlegen kann.
TIER_CLIENT_LIMITS: dict[str, int | None] = {
    "starter": 5,
    "pro": 20,
    "business": None,
}
UNSUBSCRIBED_CLIENT_LIMIT = 1

FREE_CHECKINS_LIMIT = 2


def is_billing_exempt(user: User) -> bool:
    return user.email in EXEMPT_EMAILS


def has_active_subscription(user: User) -> bool:
    return user.subscription_status in ("trialing", "active")


def client_limit_for(user: User) -> int | None:
    """None bedeutet unbegrenzt. Gilt nur für Coach-Accounts sinnvoll -
    Single-Accounts werden stattdessen über check_and_consume_free_checkin
    limitiert, nicht über die Klientenzahl (die ist bei ihnen immer 1)."""
    if not has_active_subscription(user):
        return UNSUBSCRIBED_CLIENT_LIMIT
    return TIER_CLIENT_LIMITS.get(user.subscription_tier or "", UNSUBSCRIBED_CLIENT_LIMIT)


def check_can_create_client(user: User, db: Session) -> None:
    """Wirft HTTPException(402), wenn das Anlegen eines weiteren Clients
    das aktuelle Limit überschreiten würde. No-Op (kein Fehler), wenn
    erlaubt oder der Account von Billing ausgenommen ist."""
    if is_billing_exempt(user):
        return
    limit = client_limit_for(user)
    if limit is None:
        return
    current_count = db.query(Client).filter(Client.owner_id == user.id).count()
    if current_count >= limit:
        raise HTTPException(
            402,
            "Client limit reached - please subscribe or upgrade to the next tier.",
        )


def check_and_consume_free_checkin(user: User, db: Session) -> None:
    """Für SINGLE-Accounts: prüft, ob noch kostenloses Kontingent
    vorhanden ist (oder ein aktives Abo/eine Ausnahme vorliegt), und
    zählt bei Bedarf den kumulativen Verbrauch hoch. Wirft
    HTTPException(402), wenn das Kontingent erschöpft ist. No-Op für
    Coach-Accounts (die werden über die Klientenzahl limitiert, nicht
    über Check-ins) - Aufrufer ruft diese Funktion trotzdem unconditional
    auf, sie entscheidet selbst, ob sie überhaupt etwas tut.

    Der Verbrauchs-Check + die Erhöhung laufen als EIN atomares
    `UPDATE ... WHERE free_checkins_used < LIMIT` statt eines Python-
    seitigen Lesen-dann-Schreiben - sonst könnten zwei zeitgleiche
    Requests (z.B. Doppel-Klick, wackelige Mobilverbindung mit Retry)
    beide denselben, noch nicht erhöhten Zählerstand lesen und beide
    durchkommen, obwohl das Kontingent eigentlich nur einmal reicht
    (gefunden im finalen Billing-Review)."""
    if user.account_type != AccountType.SINGLE:
        return
    if is_billing_exempt(user) or has_active_subscription(user):
        return

    result = db.execute(
        update(User)
        .where(User.id == user.id, User.free_checkins_used < FREE_CHECKINS_LIMIT)
        .values(free_checkins_used=User.free_checkins_used + 1)
    )
    if result.rowcount == 0:
        raise HTTPException(
            402,
            "Free allowance used up - please subscribe to submit more check-ins.",
        )
    db.flush()
    db.refresh(user)

    # Nudge genau beim Uebergang zu "noch 1 uebrig" - dank des nie
    # sinkenden, kumulativen Zaehlers passiert das automatisch nur genau
    # einmal pro Account, kein zusaetzlicher Idempotenz-Mechanismus
    # noetig. Siehe Design-Spec "E-Mail-Sequenzen" Abschnitt 3.
    if user.free_checkins_used == FREE_CHECKINS_LIMIT - 1:
        try:
            send_quota_warning_email(to=user.email)
        except Exception:
            logger.warning("Could not send quota-warning email", exc_info=True)
