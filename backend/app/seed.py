"""Creates the tables and fills them with synthetic test accounts.

Run from the backend folder:
    python -m app.seed           create tables + sample data (safe to run again)
    python -m app.seed --reset   delete EVERYTHING and start fresh
"""

import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import Customer, Merchant, Wallet

# Synthetic data only — no real people or phone numbers (proposal section 3.6).
SAMPLE_CUSTOMERS = [
    ("Amina W.", "254712000217", Decimal("12450.00")),
    ("Brian O.", "254712000218", Decimal("3020.00")),
    ("Faith K.", "254712000219", Decimal("800.00")),
]

SAMPLE_MERCHANTS = [
    ("Mama Mboga Grocers", "52011"),
    ("Kibanda Cafe", "52012"),
    ("Tuko Books", "52013"),
]


def seed_sample_data(db: Session) -> None:
    """Add the sample customers and merchants, each with one wallet."""
    for name, phone, balance in SAMPLE_CUSTOMERS:
        customer = Customer(name=name, phone=phone)
        db.add(customer)
        db.flush()  # sends the INSERT so PostgreSQL gives us customer_id
        db.add(Wallet(owner_type="CUSTOMER", owner_id=customer.customer_id, balance=balance))

    for name, code in SAMPLE_MERCHANTS:
        merchant = Merchant(name=name, business_code=code)
        db.add(merchant)
        db.flush()
        db.add(Wallet(owner_type="MERCHANT", owner_id=merchant.merchant_id, balance=Decimal("0.00")))

    db.commit()


def main() -> None:
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")

    Base.metadata.create_all(engine)  # creates any tables that don't exist yet
    print("Tables ready: customers, merchants, wallets, transactions, ledger_entries.")

    with SessionLocal() as db:
        if db.query(Customer).count() > 0:
            print("Sample data already exists — nothing added.")
            return
        seed_sample_data(db)
        print(f"Added {len(SAMPLE_CUSTOMERS)} customers and {len(SAMPLE_MERCHANTS)} merchants, each with a wallet.")


if __name__ == "__main__":
    main()
