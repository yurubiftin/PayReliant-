"""Database tables, matching Figure 4.3 (ER diagram) in the proposal.

Each class below becomes one table in PostgreSQL.
Each `Mapped[...] = mapped_column(...)` line becomes one column.

Step 2: CUSTOMER, MERCHANT, WALLET
Step 3: TRANSACTION, LEDGER_ENTRY
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


# The states a transaction moves through (proposal section 4.1):
#   PENDING -> PROCESSING -> SUCCESSFUL
#                        \-> FAILED
TRANSACTION_STATES = ("PENDING", "PROCESSING", "SUCCESSFUL", "FAILED")


class Transaction(Base):
    """One payment request from a customer to a merchant."""

    __tablename__ = "transactions"

    transaction_id: Mapped[int] = mapped_column(primary_key=True)
    # The unique key the client sends with each payment. unique=True means the
    # database will never store two transactions with the same key.
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id"))
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.merchant_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    failure_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="transaction", order_by="LedgerEntry.entry_id"
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCESSFUL', 'FAILED')", name="valid_status"
        ),
    )


class LedgerEntry(Base):
    """A permanent record of money moving in or out of one wallet.

    Every successful payment creates exactly two entries:
      DEBIT  on the customer's wallet (money out)
      CREDIT on the merchant's wallet (money in)
    So across the whole ledger, total DEBITs always equal total CREDITs.
    """

    __tablename__ = "ledger_entries"

    entry_id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.transaction_id"))
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.wallet_id"))
    entry_type: Mapped[str] = mapped_column(String(10))  # "DEBIT" or "CREDIT"
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped[Transaction] = relationship(back_populates="ledger_entries")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ledger_amount_positive"),
        CheckConstraint("entry_type IN ('DEBIT', 'CREDIT')", name="valid_entry_type"),
    )
