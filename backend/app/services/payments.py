"""The transaction service: moves money from a customer wallet to a merchant wallet.

This follows "Core Transaction Processing Logic" (proposal section 4.5):

  1. Identify the customer and merchant           -> 404 if either is unknown
  2. Record the transaction as PENDING            -> saved immediately
  3. Move it to PROCESSING
  4. Check the customer has enough balance        -> FAILED if not, nothing moves
  5. Debit customer + credit merchant + write two ledger entries,
     all in ONE database transaction              -> all happen, or none happen
  6. Mark it SUCCESSFUL (or FAILED if anything went wrong)

Not yet handled (later steps):
  - A repeated idempotency key is rejected, not replayed      -> Step 5
  - Two payments from the same wallet at the same instant     -> Step 6
"""

from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Customer, LedgerEntry, Merchant, Transaction, Wallet


class NotFoundError(Exception):
    """The customer or merchant in the request doesn't exist."""


class DuplicateKeyError(Exception):
    """A transaction with this idempotency key already exists."""


def process_payment(
    db: Session, *, idempotency_key: str, customer_phone: str, merchant_code: str, amount: Decimal
) -> Transaction:
    # --- 1. Identify the customer and merchant --------------------------------
    customer = db.query(Customer).filter_by(phone=customer_phone).first()
    if customer is None or customer.status != "ACTIVE":
        raise NotFoundError(f"No active customer with phone {customer_phone}")

    merchant = db.query(Merchant).filter_by(business_code=merchant_code).first()
    if merchant is None or merchant.status != "ACTIVE":
        raise NotFoundError(f"No active merchant with code {merchant_code}")

    # --- 2. Record the transaction as PENDING ---------------------------------
    # Committed straight away, so there's a record even if something fails later.
    txn = Transaction(
        idempotency_key=idempotency_key,
        customer_id=customer.customer_id,
        merchant_id=merchant.merchant_id,
        amount=amount,
        status="PENDING",
    )
    db.add(txn)
    try:
        db.commit()
    except IntegrityError:
        # The UNIQUE rule on idempotency_key stopped a second insert.
        db.rollback()
        raise DuplicateKeyError(idempotency_key)

    # --- 3. PROCESSING --------------------------------------------------------
    txn.status = "PROCESSING"
    db.commit()

    try:
        customer_wallet = db.query(Wallet).filter_by(
            owner_type="CUSTOMER", owner_id=customer.customer_id
        ).one()
        merchant_wallet = db.query(Wallet).filter_by(
            owner_type="MERCHANT", owner_id=merchant.merchant_id
        ).one()

        # --- 4. Enough money? --------------------------------------------------
        if customer_wallet.balance < amount:
            txn.status = "FAILED"
            txn.failure_reason = "INSUFFICIENT_BALANCE"
            db.commit()
            return txn

        # --- 5. Move the money: everything below commits together, or not at all.
        customer_wallet.balance -= amount
        merchant_wallet.balance += amount
        db.add(LedgerEntry(transaction_id=txn.transaction_id, wallet_id=customer_wallet.wallet_id,
                           entry_type="DEBIT", amount=amount))
        db.add(LedgerEntry(transaction_id=txn.transaction_id, wallet_id=merchant_wallet.wallet_id,
                           entry_type="CREDIT", amount=amount))

        # --- 6. SUCCESSFUL -----------------------------------------------------
        txn.status = "SUCCESSFUL"
        db.commit()
        return txn

    except Exception:
        # Anything unexpected: undo every half-finished change, then record FAILED.
        db.rollback()
        txn.status = "FAILED"
        txn.failure_reason = "PROCESSING_ERROR"
        db.commit()
        raise
