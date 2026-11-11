"""PayReliant API — entry point (the "API gateway" layer).

This file only defines the web addresses and WHO may call each one.
The payment logic lives in app/services/payments.py; login logic in app/security.py.

Who can call what (proposal 3.1.3 "Security"):
  public          /health, /auth/login, /simulator/
  USSD gateway    POST /payments (needs the X-API-Key header)
  admin           everything, including creating and suspending accounts
  merchant        only their OWN transactions, wallet and stats
"""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, LedgerEntry, Merchant, Transaction, User, Wallet
from app.schemas import (
    BalanceOut,
    CustomerCreate,
    CustomerOut,
    LoginOut,
    MerchantCreate,
    MerchantOut,
    PaymentRequest,
    StatsOut,
    StatusUpdate,
    TransactionOut,
    UserOut,
    WalletOut,
)
from app.security import (
    admin_user,
    authenticate,
    create_token,
    current_user,
    gateway,
    gateway_or_admin,
    gateway_or_user,
    hash_password,
)
from app.services.payments import (
    KeyReuseMismatchError,
    NotFoundError,
    PaymentInProgressError,
    process_payment,
)

app = FastAPI(
    title="PayReliant API",
    description=(
        "USSD Mobile Payment Reliability Sandbox & API Gateway (simulated money only).\n\n"
        "**To try protected endpoints here:** click **Authorize**, log in with a username and "
        "password (e.g. `admin`), and/or enter the gateway API key for `/payments`."
    ),
    version="0.9.0",
)

# The dashboard runs on its own address (http://localhost:5173 during development).
# Browsers block a page from calling a DIFFERENT address unless that server allows it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-API-Key"],
    expose_headers=["Idempotent-Replayed", "Retry-After"],
)

AdminUser = Annotated[User, Depends(admin_user)]
AnyUser = Annotated[User, Depends(current_user)]


def scope_to_user(query, user: User | None):
    """A merchant only ever sees their own transactions; admins (and the gateway) see all."""
    if user is not None and user.role == "MERCHANT":
        return query.filter(Transaction.merchant_id == user.merchant_id)
    return query


def user_out(db: Session, user: User) -> UserOut:
    merchant = db.get(Merchant, user.merchant_id) if user.merchant_id else None
    return UserOut(username=user.username, role=user.role, merchant_id=user.merchant_id,
                   merchant_name=merchant.name if merchant else None)


# --- Public ----------------------------------------------------------------------

@app.get("/health", tags=["system"])
def health() -> dict:
    """Simple liveness check. Load tests and the dashboard will call this."""
    return {"status": "ok", "service": "payreliant-api"}


@app.post("/auth/login", response_model=LoginOut, tags=["auth"])
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    """Log in with username + password. Returns a token to send as `Authorization: Bearer <token>`."""
    user = authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    return LoginOut(access_token=create_token(user), user=user_out(db, user))


@app.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: AnyUser, db: Session = Depends(get_db)):
    """Who is currently logged in."""
    return user_out(db, user)


# --- Accounts --------------------------------------------------------------------

@app.get("/customers", response_model=list[CustomerOut], tags=["accounts"],
         dependencies=[Depends(gateway_or_admin)])
def list_customers(db: Session = Depends(get_db)):
    """All simulated customers. (Admin, or the USSD gateway.)"""
    return db.query(Customer).order_by(Customer.customer_id).all()


@app.post("/customers", response_model=CustomerOut, status_code=201, tags=["accounts"])
def create_customer(body: CustomerCreate, _: AdminUser, db: Session = Depends(get_db)):
    """Create a simulated customer and their wallet. (Admin only.)"""
    if db.query(Customer).filter_by(phone=body.phone).first():
        raise HTTPException(status_code=409, detail="A customer with this phone number already exists.")
    customer = Customer(name=body.name, phone=body.phone)
    db.add(customer)
    db.flush()  # get customer_id
    db.add(Wallet(owner_type="CUSTOMER", owner_id=customer.customer_id, balance=body.initial_balance))
    db.commit()
    return customer


@app.patch("/customers/{customer_id}", response_model=CustomerOut, tags=["accounts"])
def update_customer_status(customer_id: int, body: StatusUpdate, _: AdminUser, db: Session = Depends(get_db)):
    """Suspend or re-activate a customer. A suspended customer cannot make payments. (Admin only.)"""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.status = body.status
    db.commit()
    return customer


@app.get("/customers/{phone}/balance", response_model=BalanceOut, tags=["accounts"],
         dependencies=[Depends(gateway_or_admin)])
def customer_balance(phone: str, db: Session = Depends(get_db)):
    """A customer's wallet balance (the USSD 'Check balance' option). (Admin, or the USSD gateway.)"""
    customer = db.query(Customer).filter_by(phone=phone).first()
    if customer is None:
        raise HTTPException(status_code=404, detail=f"No customer with phone {phone}")
    wallet = db.query(Wallet).filter_by(owner_type="CUSTOMER", owner_id=customer.customer_id).one()
    return BalanceOut(name=customer.name, phone=customer.phone, balance=wallet.balance)


@app.get("/merchants", response_model=list[MerchantOut], tags=["accounts"])
def list_merchants(user: Annotated[User | None, Depends(gateway_or_user)], db: Session = Depends(get_db)):
    """All merchants (names and codes). Admins also see each merchant's login username."""
    merchants = db.query(Merchant).order_by(Merchant.merchant_id).all()
    result = [MerchantOut.model_validate(m) for m in merchants]
    if user is not None and user.role == "ADMIN":
        logins = {u.merchant_id: u.username for u in db.query(User).filter_by(role="MERCHANT")}
        for m in result:
            m.login_username = logins.get(m.merchant_id)
    return result


@app.post("/merchants", response_model=MerchantOut, status_code=201, tags=["accounts"])
def create_merchant(body: MerchantCreate, _: AdminUser, db: Session = Depends(get_db)):
    """Onboard a merchant: creates the merchant, their wallet, and their dashboard login. (Admin only.)"""
    if db.query(Merchant).filter_by(business_code=body.business_code).first():
        raise HTTPException(status_code=409, detail="A merchant with this business code already exists.")
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(status_code=409, detail="This username is already taken.")
    merchant = Merchant(name=body.name, business_code=body.business_code)
    db.add(merchant)
    db.flush()
    db.add(Wallet(owner_type="MERCHANT", owner_id=merchant.merchant_id))
    db.add(User(username=body.username, password_hash=hash_password(body.password),
                role="MERCHANT", merchant_id=merchant.merchant_id))
    db.commit()
    out = MerchantOut.model_validate(merchant)
    out.login_username = body.username
    return out


@app.patch("/merchants/{merchant_id}", response_model=MerchantOut, tags=["accounts"])
def update_merchant_status(merchant_id: int, body: StatusUpdate, _: AdminUser, db: Session = Depends(get_db)):
    """Suspend or re-activate a merchant: blocks payments to them AND their dashboard login. (Admin only.)"""
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    merchant.status = body.status
    for login_user in db.query(User).filter_by(merchant_id=merchant_id):
        login_user.is_active = body.status == "ACTIVE"
    db.commit()
    return merchant


@app.get("/wallets", response_model=list[WalletOut], tags=["accounts"])
def list_wallets(user: AnyUser, db: Session = Depends(get_db)):
    """Wallet balances. Admins see all; a merchant sees only their own wallet."""
    query = db.query(Wallet).order_by(Wallet.wallet_id)
    if user.role == "MERCHANT":
        query = query.filter_by(owner_type="MERCHANT", owner_id=user.merchant_id)
    return query.all()


# --- Payments --------------------------------------------------------------------

@app.post(
    "/payments",
    response_model=TransactionOut,
    status_code=201,
    tags=["payments"],
    dependencies=[Depends(gateway)],
    responses={
        401: {"description": "Missing or invalid gateway API key"},
        404: {"description": "Unknown or suspended customer or merchant"},
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
    """Pay a merchant from a customer's wallet. **Requires the gateway API key** (`X-API-Key`).

    Send a unique **Idempotency-Key** header with every new payment (e.g. `pay-0001`).
    A retry with the same key is NOT charged again: the response is the original result,
    with the header `Idempotent-Replayed: true`.
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


# --- Monitoring (dashboard) ------------------------------------------------------

@app.get("/transactions", response_model=list[TransactionOut], tags=["monitoring"])
def list_transactions(
    user: AnyUser,
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
    db: Session = Depends(get_db),
):
    """Transactions, newest first. A merchant sees only their own. Use `limit` for the latest few."""
    query = scope_to_user(db.query(Transaction), user).order_by(Transaction.transaction_id.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


@app.get("/transactions/{transaction_id}", response_model=TransactionOut, tags=["monitoring"])
def get_transaction(transaction_id: int, user: AnyUser, db: Session = Depends(get_db)):
    """One transaction with its ledger entries. A merchant can only open their own."""
    txn = scope_to_user(db.query(Transaction), user).filter(
        Transaction.transaction_id == transaction_id).first()
    if txn is None:
        # Same answer whether it doesn't exist or belongs to another merchant: reveal nothing.
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@app.get("/stats", response_model=StatsOut, tags=["monitoring"])
def stats(user: AnyUser, db: Session = Depends(get_db)):
    """Headline numbers for the dashboard, calculated live. A merchant gets numbers for their own business."""
    txns = scope_to_user(db.query(Transaction), user)
    counts = dict(scope_to_user(db.query(Transaction.status, func.count()), user)
                  .group_by(Transaction.status).all())
    successful = counts.get("SUCCESSFUL", 0)
    failed = counts.get("FAILED", 0)
    pending = counts.get("PENDING", 0) + counts.get("PROCESSING", 0)
    finished = successful + failed

    ledger = scope_to_user(db.query(func.sum(LedgerEntry.amount)).join(Transaction), user)
    debits = ledger.filter(LedgerEntry.entry_type == "DEBIT").scalar() or 0
    credits = ledger.filter(LedgerEntry.entry_type == "CREDIT").scalar() or 0
    avg_ms = scope_to_user(db.query(func.avg(Transaction.processing_ms)), user).scalar()

    return StatsOut(
        total_transactions=successful + failed + pending,
        successful=successful,
        failed=failed,
        pending=pending,
        success_rate=round(successful / finished * 100, 1) if finished else None,
        avg_processing_ms=round(float(avg_ms), 1) if avg_ms is not None else None,
        duplicates_blocked=txns.with_entities(func.coalesce(func.sum(Transaction.replay_count), 0)).scalar(),
        volume_successful=txns.filter(Transaction.status == "SUCCESSFUL")
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar(),
        ledger_balanced=debits == credits,
    )


# --- USSD simulator (Step 7) ----------------------------------------------------
# The simulator is a plain web page (ussd-simulator/index.html at the project root).
# FastAPI serves it at http://127.0.0.1:8000/simulator/ so it can call this API directly.
SIMULATOR_DIR = Path(__file__).resolve().parents[2] / "ussd-simulator"
if SIMULATOR_DIR.is_dir():
    app.mount("/simulator", StaticFiles(directory=SIMULATOR_DIR, html=True), name="simulator")
