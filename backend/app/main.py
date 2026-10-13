"""PayReliant API — entry point (the "API gateway" layer).

This file only defines the web addresses. The real payment logic lives in
app/services/payments.py, so it can be tested and changed on its own.

Step 1: /health
Step 2: /customers, /merchants, /wallets
Step 3: POST /payments, /transactions
"""

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Merchant, Transaction, Wallet
from app.schemas import CustomerOut, MerchantOut, PaymentRequest, TransactionOut, WalletOut
from app.services.payments import DuplicateKeyError, NotFoundError, process_payment

app = FastAPI(
    title="PayReliant API",
    description="USSD Mobile Payment Reliability Sandbox & API Gateway (simulated money only).",
    version="0.3.0",
)


@app.get("/health")
def health() -> dict:
    """Simple liveness check. Load tests and the dashboard will call this."""
    return {"status": "ok", "service": "payreliant-api"}


# `db: Session = Depends(get_db)` means: "FastAPI, open a database session
# for this request, hand it to me as `db`, and close it when I'm done."


@app.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    """All simulated customers."""
    return db.query(Customer).order_by(Customer.customer_id).all()


@app.get("/merchants", response_model=list[MerchantOut])
def list_merchants(db: Session = Depends(get_db)):
    """All simulated merchants."""
    return db.query(Merchant).order_by(Merchant.merchant_id).all()


@app.get("/wallets", response_model=list[WalletOut])
def list_wallets(db: Session = Depends(get_db)):
    """All wallets and their current balances."""
    return db.query(Wallet).order_by(Wallet.wallet_id).all()


@app.post(
    "/payments",
    response_model=TransactionOut,
    status_code=201,
    responses={
        404: {"description": "Unknown customer or merchant"},
        409: {"description": "Idempotency key already used"},
        422: {"description": "Invalid request, or payment FAILED (e.g. insufficient balance)"},
    },
)
def create_payment(
    payment: PaymentRequest,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=100)],
    db: Session = Depends(get_db),
):
    """Pay a merchant from a customer's wallet.

    Send a unique **Idempotency-Key** header with every new payment
    (any unique text, e.g. `pay-0001`). Retrying with the same key must never
    charge the customer twice.
    """
    try:
        txn = process_payment(
            db,
            idempotency_key=idempotency_key,
            customer_phone=payment.customer_phone,
            merchant_code=payment.merchant_code,
            amount=payment.amount,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="This Idempotency-Key was already used. Use a new key for a new payment.",
        )

    body = TransactionOut.model_validate(txn).model_dump(mode="json")
    if txn.status == "FAILED":
        return JSONResponse(status_code=422, content=body)
    return body


@app.get("/transactions", response_model=list[TransactionOut])
def list_transactions(db: Session = Depends(get_db)):
    """All transactions, newest first."""
    return db.query(Transaction).order_by(Transaction.transaction_id.desc()).all()


@app.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """One transaction, including its ledger entries."""
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn
