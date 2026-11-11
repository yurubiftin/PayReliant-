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
    JSON,
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
    # Step 8 (dashboard metrics):
    # how long the server took to process this payment, in milliseconds
    processing_ms: Mapped[float | None] = mapped_column(default=None)
    # how many duplicate requests with this key were blocked (replayed or told to wait)
    replay_count: Mapped[int] = mapped_column(default=0, server_default="0")
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


class User(Base):
    """A dashboard login (Step 9a: authentication).

    Two roles:
      ADMIN    - operates the sandbox: sees everything, manages accounts and settings
      MERCHANT - sees only their own merchant's transactions and wallet (merchant_id is set)

    Passwords are NEVER stored. Only a one-way Argon2 hash is kept, so even someone who
    reads the database cannot recover the password.
    """

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10))  # "ADMIN" or "MERCHANT"
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.merchant_id"), default=None)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'MERCHANT')", name="valid_role"),
        # A merchant login must belong to a merchant; an admin must not.
        CheckConstraint(
            "(role = 'MERCHANT' AND merchant_id IS NOT NULL) OR (role = 'ADMIN' AND merchant_id IS NULL)",
            name="merchant_link_matches_role",
        ),
    )


class SandboxSettings(Base):
    """Sandbox settings (Step 9b), edited by the admin on the Settings screen. Always exactly one row (id 1).

    Every value here really changes behaviour:
      provider_name          shown on the USSD simulator's menu screen
      client_timeout_s       how long a client waits for a reply before retrying (timeout test, simulator)
      session_logging        when on, the API prints one line per payment to its terminal
      max_requests_per_test  how many requests each reliability test sends
      retry_attempts         how many times a client retries after a timeout (timeout test, simulator)
      failure_rate_pct       % of real payments that fail ON PURPOSE mid-transaction (failure injection)
      added_latency_ms       extra delay added to every real payment (latency injection)
    """

    __tablename__ = "sandbox_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(60), default="PayReliant Sandbox")
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    client_timeout_s: Mapped[float] = mapped_column(default=0.5)
    session_logging: Mapped[bool] = mapped_column(default=True)
    max_requests_per_test: Mapped[int] = mapped_column(default=100)
    retry_attempts: Mapped[int] = mapped_column(default=3)
    failure_rate_pct: Mapped[float] = mapped_column(default=0.0)
    added_latency_ms: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReliabilityRun(Base):
    """The result of one reliability test run from the Reliability Tests screen (Step 9b)."""

    __tablename__ = "reliability_runs"

    run_id: Mapped[int] = mapped_column(primary_key=True)
    scenario: Mapped[str] = mapped_column(String(20))  # duplicate | timeout | failed | concurrent
    requests: Mapped[int] = mapped_column()
    passed: Mapped[int] = mapped_column()   # requests whose outcome was correct and safe
    failed: Mapped[int] = mapped_column()   # requests whose outcome was wrong or unsafe
    status: Mapped[str] = mapped_column(String(10))  # PASSED if every consistency check held
    duration_ms: Mapped[float] = mapped_column()
    p95_ms: Mapped[float | None] = mapped_column(default=None)
    checks: Mapped[list] = mapped_column(JSON)  # [{"name": ..., "passed": bool, "detail": ...}]
    summary: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
