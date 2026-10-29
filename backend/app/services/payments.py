"""The transaction service: moves money from a customer wallet to a merchant wallet.

This follows "Core Transaction Processing Logic" (proposal section 4.5):

  0. Idempotency check: has this key been seen before?
       - finished before       -> return the ORIGINAL result (no second charge)
       - still being processed -> tell the client to retry shortly
       - same key, different payment details -> reject (client bug)
  1. Identify the customer and merchant           -> 404 if either is unknown
  2. Record the transaction as PENDING            -> saved immediately
  3. Move it to PROCESSING
  4. LOCK both wallets, then check the customer has enough balance
                                                  -> FAILED if not, nothing moves
  5. Debit customer + credit merchant + write two ledger entries,
     all in ONE database transaction              -> all happen, or none happen
  6. Mark it SUCCESSFUL (or FAILED if anything went wrong)

Concurrency (Step 6):
  Two DIFFERENT payments from the same wallet at the same instant would both read
  the same old balance, and one deduction would be lost. Step 4 prevents this with
  SELECT ... FOR UPDATE: the second payment WAITS until the first one commits, then
  reads the new balance.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
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
        customer_wallet, merchant_wallet = _lock_wallets(db, customer, merchant)

        # --- 4. Enough money? (the balance read here is the latest, because we hold the lock)
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


def _lock_wallets(db: Session, customer: Customer, merchant: Merchant) -> tuple[Wallet, Wallet]:
    """Fetch both wallets, LOCKING their rows until this payment commits or rolls back.

    SELECT ... FOR UPDATE tells PostgreSQL: "I'm about to change these rows; anyone else
    who wants to lock them must wait until I'm finished."

    Both rows are locked in ONE query, ordered by wallet_id. Every payment therefore locks
    wallets in the same order, which prevents deadlocks (payment A holding wallet 1 and
    waiting for 4, while payment B holds 4 and waits for 1).
    """
    query = db.query(Wallet).filter(
        ((Wallet.owner_type == "CUSTOMER") & (Wallet.owner_id == customer.customer_id))
        | ((Wallet.owner_type == "MERCHANT") & (Wallet.owner_id == merchant.merchant_id))
    ).order_by(Wallet.wallet_id)

    if config.LOCK_WALLETS:
        query = query.with_for_update()

    wallets = query.all()
    customer_wallet = next(w for w in wallets if w.owner_type == "CUSTOMER")
    merchant_wallet = next(w for w in wallets if w.owner_type == "MERCHANT")
    return customer_wallet, merchant_wallet


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
