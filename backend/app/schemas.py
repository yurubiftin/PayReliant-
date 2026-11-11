"""The shape of data the API sends back.

models.py  = how data is stored in the database
schemas.py = how data looks in the API's JSON responses
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    name: str
    phone: str
    status: str


class MerchantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    merchant_id: int
    name: str
    business_code: str
    status: str
    login_username: str | None = None  # filled in for admins only


class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: int
    owner_type: str
    owner_id: int
    balance: Decimal


class BalanceOut(BaseModel):
    """What the USSD 'Check balance' option shows."""

    name: str
    phone: str
    balance: Decimal


class PaymentRequest(BaseModel):
    """What a client (the USSD simulator, a test) sends to make a payment.

    FastAPI checks these rules automatically and rejects bad requests
    with a 422 error before our code even runs.
    """

    customer_phone: str = Field(examples=["254712000217"])
    merchant_code: str = Field(examples=["52011"])
    # gt=0: must be more than zero. decimal_places=2: no fractions of a cent.
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, examples=["500.00"])


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_id: int
    wallet_id: int
    entry_type: str
    amount: Decimal


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    idempotency_key: str
    customer_id: int
    merchant_id: int
    amount: Decimal
    status: str
    failure_reason: str | None
    processing_ms: float | None
    replay_count: int
    created_at: datetime
    updated_at: datetime
    ledger_entries: list[LedgerEntryOut]


class StatsOut(BaseModel):
    """Headline numbers for the dashboard (Step 8)."""

    total_transactions: int
    successful: int
    failed: int
    pending: int  # PENDING or PROCESSING right now
    success_rate: float | None  # % of finished transactions that succeeded
    avg_processing_ms: float | None
    duplicates_blocked: int
    volume_successful: Decimal  # total KES moved by successful payments
    ledger_balanced: bool  # total DEBITs == total CREDITs


# --- Step 9a: authentication and account management --------------------------------

class UserOut(BaseModel):
    """Who is logged in (returned by /auth/login and /auth/me)."""

    username: str
    role: str  # "ADMIN" or "MERCHANT"
    merchant_id: int | None
    merchant_name: str | None


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, examples=["Wanjiku M."])
    # Kenyan mobile number in international format: 254 + 7xx or 1xx + 6 digits
    phone: str = Field(pattern=r"^254(7|1)\d{8}$", examples=["254712000220"])
    initial_balance: Decimal = Field(ge=0, max_digits=12, decimal_places=2, examples=["5000.00"])


class MerchantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, examples=["Duka La Mama"])
    business_code: str = Field(pattern=r"^\d{5}$", examples=["52014"])
    # The merchant's dashboard login
    username: str = Field(pattern=r"^[a-z0-9_]{3,30}$", examples=["dukalamama"])
    password: str = Field(min_length=8, max_length=100)


class StatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(ACTIVE|SUSPENDED)$")
