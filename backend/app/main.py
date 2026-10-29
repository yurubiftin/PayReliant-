"""PayReliant API — entry point (the "API gateway" layer).

This file only defines the web addresses. The real payment logic lives in
app/services/payments.py, so it can be tested and changed on its own.

Step 1: /health
Step 2: /customers, /merchants, /wallets
Step 3: POST /payments, /transactions
Step 5: idempotent replay of repeated payment requests
Step 7: customer balance lookup + serves the USSD simulator at /simulator/
"""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Merchant, Transaction, Wallet
from app.schemas import (
    BalanceOut,
    CustomerOut,
    MerchantOut,
    PaymentRequest,
    TransactionOut,
    WalletOut,
)
from app.services.payments import (
    KeyReuseMismatchError,
    NotFoundError,
    PaymentInProgressError,
    process_payment,
)

app = FastAPI(
    title="PayReliant API",
    description="USSD Mobile Payment Reliability Sandbox & API Gateway (simulated money only).",
    version="0.5.0",
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


@app.get("/customers/{phone}/balance", response_model=BalanceOut)
def customer_balance(phone: str, db: Session = Depends(get_db)):
    """A customer's current wallet balance (used by the USSD 'Check balance' option)."""
    customer = db.query(Customer).filter_by(phone=phone).first()
    if customer is None:
        raise HTTPException(status_code=404, detail=f"No customer with phone {phone}")
    wallet = db.query(Wallet).filter_by(owner_type="CUSTOMER", owner_id=customer.customer_id).one()
    return BalanceOut(name=customer.name, phone=customer.phone, balance=wallet.balance)


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
        409: {"description": "A request with this key is still being processed. Retry shortly."},
        422: {
            "description": "Invalid request, payment FAILED (e.g. insufficient balance), "
            "or key reused for a different payment"
        },
    },
)
def create_payment(
    payment: PaymentRequest,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=100)],
    db: Session = Depends(get_db),
):
    """Pay a merchant from a customer's wallet.

    Send a unique **Idempotency-Key** header with every new payment
    (any unique text, e.g. `pay-0001`).

    If the same request is sent again with the same key (a retry), the customer is
    NOT charged again: the response is the original result, with the header
    `Idempotent-Replayed: true`.
    """
    try:
        result = process_payment(
            db,
            idempotency_key=idempotency_key,
            customer_phone=payment.customer_phone,
            merchant_code=payment.merchant_code,
            amount=payment.amount,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PaymentInProgressError:
        raise HTTPException(
            status_code=409,
            detail="A payment with this Idempotency-Key is still being processed. Retry shortly.",
            headers={"Retry-After": "1"},
        )
    except KeyReuseMismatchError:
        raise HTTPException(
            status_code=422,
            detail="This Idempotency-Key was already used for a different payment. "
            "Use a new key for a new payment.",
        )

    txn = result.transaction
    body = TransactionOut.model_validate(txn).model_dump(mode="json")
    # Same status code every time for the same key: 201 if it succeeded, 422 if it failed.
    status_code = 201 if txn.status == "SUCCESSFUL" else 422
    headers = {"Idempotent-Replayed": "true" if result.replayed else "false"}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


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


# --- USSD simulator (Step 7) ----------------------------------------------------
# The simulator is a plain web page (ussd-simulator/index.html at the project root).
# FastAPI serves it at http://127.0.0.1:8000/simulator/ so it can call this API directly.
SIMULATOR_DIR = Path(__file__).resolve().parents[2] / "ussd-simulator"
if SIMULATOR_DIR.is_dir():
    app.mount("/simulator", StaticFiles(directory=SIMULATOR_DIR, html=True), name="simulator")
