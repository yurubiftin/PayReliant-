"""PayReliant API — entry point.

Step 1: /health proves the server runs.
Step 2: read customers, merchants and wallets from PostgreSQL.
"""

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Merchant, Wallet
from app.schemas import CustomerOut, MerchantOut, WalletOut

app = FastAPI(
    title="PayReliant API",
    description="USSD Mobile Payment Reliability Sandbox & API Gateway (simulated money only).",
    version="0.2.0",
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
