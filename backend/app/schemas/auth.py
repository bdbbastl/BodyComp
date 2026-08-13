from app.models.user import AccountType
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType

    class Config:
        from_attributes = True
