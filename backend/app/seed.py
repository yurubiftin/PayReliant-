"""Creates the tables and fills them with synthetic test accounts and logins.

Run from the backend folder:
    python -m app.seed           create tables + sample data (safe to run again)
    python -m app.seed --reset   delete EVERYTHING and start fresh
"""

import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from app import config
from app.database import Base, SessionLocal, engine
from app.models import Customer, Merchant, User, Wallet
from app.security import hash_password

# Synthetic data only — no real people or phone numbers (proposal section 3.5).
SAMPLE_CUSTOMERS = [
    ("Amina W.", "254712000217", Decimal("12450.00")),
    ("Brian O.", "254712000218", Decimal("3020.00")),
    ("Faith K.", "254712000219", Decimal("800.00")),
]

# (name, business code, dashboard login username)
SAMPLE_MERCHANTS = [
    ("Mama Mboga Grocers", "52011", "mamamboga"),
    ("Kibanda Cafe", "52012", "kibanda"),
    ("Tuko Books", "52013", "tukobooks"),
]


def seed_sample_data(db: Session) -> None:
    """Add the sample customers and merchants, each with one wallet, plus the logins."""
    for name, phone, balance in SAMPLE_CUSTOMERS:
        customer = Customer(name=name, phone=phone)
        db.add(customer)
        db.flush()  # sends the INSERT so PostgreSQL gives us customer_id
        db.add(Wallet(owner_type="CUSTOMER", owner_id=customer.customer_id, balance=balance))

    for name, code, _ in SAMPLE_MERCHANTS:
        merchant = Merchant(name=name, business_code=code)
        db.add(merchant)
        db.flush()
        db.add(Wallet(owner_type="MERCHANT", owner_id=merchant.merchant_id, balance=Decimal("0.00")))

    db.commit()
    seed_logins(db)


def seed_logins(db: Session) -> None:
    """One admin login, and one login per sample merchant. Passwords are stored only as hashes."""
    admin_hash = hash_password(config.ADMIN_PASSWORD)
    merchant_hash = hash_password(config.DEMO_MERCHANT_PASSWORD)
    db.add(User(username="admin", password_hash=admin_hash, role="ADMIN"))
    for _, code, username in SAMPLE_MERCHANTS:
        merchant = db.query(Merchant).filter_by(business_code=code).first()
        if merchant:
            db.add(User(username=username, password_hash=merchant_hash, role="MERCHANT",
                        merchant_id=merchant.merchant_id))
    db.commit()


def main() -> None:
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")

    Base.metadata.create_all(engine)  # creates any tables that don't exist yet
    print("Tables ready: customers, merchants, wallets, transactions, ledger_entries, users, sandbox_settings, reliability_runs.")

    with SessionLocal() as db:
        if db.query(Customer).count() == 0:
            seed_sample_data(db)
            print(f"Added {len(SAMPLE_CUSTOMERS)} customers and {len(SAMPLE_MERCHANTS)} merchants, each with a wallet.")
        elif db.query(User).count() == 0:
            seed_logins(db)  # upgrading an older database: add the logins only
        else:
            print("Sample data already exists — nothing added.")
            return

    print("\nSandbox logins (synthetic, for local testing only):")
    print(f"  admin      / {config.ADMIN_PASSWORD}")
    for _, _, username in SAMPLE_MERCHANTS:
        print(f"  {username:<10} / {config.DEMO_MERCHANT_PASSWORD}")
    print(f"\nUSSD gateway API key: {config.GATEWAY_API_KEY}")


if __name__ == "__main__":
    main()
