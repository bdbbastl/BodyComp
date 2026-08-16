"""
Stripe-Netzwerk-Aufrufe (Checkout, Customer Portal) - siehe Design-Spec
Abschnitt "Zahlungsanbieter & Verwaltung". Die eigentliche Limit-Logik
(wer darf was) lebt in services/billing.py, hier geht es nur um die
Kommunikation mit Stripe selbst.
"""
import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import AccountType, User
from app.routers.auth import get_current_user
from app.schemas.billing import CheckoutRequest, CheckoutResponse, PortalResponse

router = APIRouter(prefix="/api/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key

# Staffel-Name -> Stripe-Price-ID. "single" ist bewusst kein Coach-Tier
# (siehe Design-Spec) - eigener Preis, keine Klienten-Staffelung.
TIER_PRICE_IDS: dict[str, str] = {
    "starter": settings.stripe_price_starter,
    "pro": settings.stripe_price_pro,
    "business": settings.stripe_price_business,
    "single": settings.stripe_price_single,
}
COACH_TIERS = {"starter", "pro", "business"}


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout_session(
    payload: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.tier not in TIER_PRICE_IDS:
        raise HTTPException(400, "Ungültige Staffel")
    if current_user.account_type == AccountType.SINGLE and payload.tier != "single":
        raise HTTPException(400, "Single-Accounts können nur das Single-Abo wählen")
    if current_user.account_type == AccountType.COACH and payload.tier not in COACH_TIERS:
        raise HTTPException(400, "Coach-Accounts wählen eine Klienten-Staffel")

    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        current_user.stripe_customer_id = customer.id
        db.commit()

    session_kwargs = dict(
        customer=current_user.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": TIER_PRICE_IDS[payload.tier], "quantity": 1}],
        success_url=f"{settings.frontend_base_url}/account?billing=success",
        cancel_url=f"{settings.frontend_base_url}/account?billing=cancelled",
    )
    # Nur Coach-Accounts bekommen den 14-Tage-Trial (siehe Design-Spec
    # Abschnitt "Trial") - Single-Accounts haben stattdessen das
    # kumulative Check-in-Kontingent, keinen Zeit-Trial.
    if current_user.account_type == AccountType.COACH:
        session_kwargs["subscription_data"] = {"trial_period_days": 14}

    checkout_session = stripe.checkout.Session.create(**session_kwargs)
    return CheckoutResponse(checkout_url=checkout_session.url)


@router.post("/portal", response_model=PortalResponse)
def create_portal_session(current_user: User = Depends(get_current_user)):
    if not current_user.stripe_customer_id:
        raise HTTPException(400, "Kein Stripe-Kunde vorhanden - zuerst ein Abo abschließen")
    portal_session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=f"{settings.frontend_base_url}/account",
    )
    return PortalResponse(portal_url=portal_session.url)
