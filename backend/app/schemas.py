"""The shape of data the API sends back.

models.py  = how data is stored in the database
schemas.py = how data looks in the API's JSON responses
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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
