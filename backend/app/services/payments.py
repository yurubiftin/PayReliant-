"""The transaction service: moves money from a customer wallet to a merchant wallet.

This follows "Core Transaction Processing Logic" (proposal section 4.5):

  0. Idempotency check: has this key been seen before?
       - finished before       -> return the ORIGINAL result (no second charge)
       - still being processed -> tell the client to retry shortly
       - same key, different payment details -> reject (client bug)
  1. Identify the customer and merchant           -> 404 if either is unknown
  2. Record the transaction as PENDING            -> saved immediately
  3. Move it to PROCESSING
  4. Check the customer has enough balance        -> FAILED if not, nothing moves
  5. Debit customer + credit merchant + write two ledger entries,
     all in ONE database transaction              -> all happen, or none happen
  6. Mark it SUCCESSFUL (or FAILED if anything went wrong)

Not yet handled:
  - Two DIFFERENT payments from the same wallet at the same instant -> Step 6
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Customer, LedgerEntry, Merchant, Transaction, Wallet


class NotFoundError(Exception):
    """The customer or merchant in the request doesn't exist."""


class PaymentInProgressError(Exception):
    """The same key is being processed right now; the client should retry shortly."""


class KeyReuseMismatchError(Exception):
    """The key was already used for a DIFFERENT payment (other amount/customer/merchant)."""


@dataclass
class PaymentResult:
    transaction: Transaction
    replayed: bool  # True = this is the stored result of an earlier request with the same key


def process_payment(
    db: Session, *, idempotency_key: str, customer_phone: str, merchant_code: str, amount: Decimal
) -> PaymentResult:
    # --- 0. Idempotency check --------------------------------------------------
    existing = db.query(Transaction).filter_by(idempotency_key=idempotency_key).first()
    if existing is not None:
        return _replay(db, existing, customer_phone, merchant_code, amount)

    # --- 1. Identify the customer and merchant --------------------------------
    customer = db.query(Customer).filter_by(phone=customer_phone).first()
    if customer is None or customer.status != "ACTIVE":
        raise NotFoundError(f"No active customer with phone {customer_phone}")

    merchant = db.query(Merchant).filter_by(business_code=merchant_code).first()
    if merchant is None or merchant.status != "ACTIVE":
        raise NotFoundError(f"No active merchant with code {merchant_code}")

    # --- 2. Record the transaction as PENDING ---------------------------------
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
        # Two identical requests arrived at the same moment: both passed step 0,
        # but the UNIQUE rule on idempotency_key let only ONE insert succeed.
        # We lost the race, so we treat ourselves as the retry.
        db.rollback()
        winner = db.query(Transaction).filter_by(idempotency_key=idempotency_key).one()
        return _replay(db, winner, customer_phone, merchant_code, amount)

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
            return PaymentResult(txn, replayed=False)

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
        return PaymentResult(txn, replayed=False)

    except Exception:
        # Anything unexpected: undo every half-finished change, then record FAILED.
        db.rollback()
        txn.status = "FAILED"
        txn.failure_reason = "PROCESSING_ERROR"
        db.commit()
        raise


def _replay(
    db: Session, existing: Transaction, customer_phone: str, merchant_code: str, amount: Decimal
) -> PaymentResult:
    """Handle a request whose idempotency key we've already seen."""
    # A key identifies ONE specific payment. Reusing it for a different payment is a client bug,
    # and silently returning the old result would hide that bug.
    original_customer = db.get(Customer, existing.customer_id)
    original_merchant = db.get(Merchant, existing.merchant_id)
    if (
        original_customer.phone != customer_phone
        or original_merchant.business_code != merchant_code
        or existing.amount != amount
    ):
        raise KeyReuseMismatchError(existing.idempotency_key)

    # The first request hasn't finished yet. Don't start a second one; ask the client to wait.
    if existing.status in ("PENDING", "PROCESSING"):
        raise PaymentInProgressError(existing.idempotency_key)

    # Finished (SUCCESSFUL or FAILED): hand back exactly what the first request got.
    return PaymentResult(existing, replayed=True)
