from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    tier: str  # "starter" | "pro" | "business" | "single"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str
