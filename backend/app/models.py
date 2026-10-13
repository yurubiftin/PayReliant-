"""Database tables, matching Figure 4.3 (ER diagram) in the proposal.

Each class below becomes one table in PostgreSQL.
Each `Mapped[...] = mapped_column(...)` line becomes one column.

Step 2 covers CUSTOMER, MERCHANT and WALLET.
TRANSACTION and LEDGER_ENTRY are added in Step 3.
"""

from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), unique=True)  # no two customers share a number
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class Merchant(Base):
    __tablename__ = "merchants"

    merchant_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    business_code: Mapped[str] = mapped_column(String(10), unique=True)  # what customers type on USSD
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class Wallet(Base):
    __tablename__ = "wallets"

    wallet_id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(10))  # "CUSTOMER" or "MERCHANT"
    owner_id: Mapped[int] = mapped_column()              # customer_id or merchant_id
    # Numeric, not float: floats round money wrongly (0.1 + 0.2 != 0.3).
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    __table_args__ = (
        # Reliability rules enforced by the DATABASE itself, not just our Python code.
        # Even if our code has a bug, PostgreSQL will refuse to break these.
        CheckConstraint("balance >= 0", name="balance_not_negative"),
        CheckConstraint("owner_type IN ('CUSTOMER', 'MERCHANT')", name="valid_owner_type"),
        UniqueConstraint("owner_type", "owner_id", name="one_wallet_per_owner"),
    )
