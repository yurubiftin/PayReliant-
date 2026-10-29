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
    created_at: datetime
    ledger_entries: list[LedgerEntryOut]
