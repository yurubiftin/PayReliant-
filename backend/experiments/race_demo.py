"""Before/after experiment for Scenario 4 (concurrent requests).

Runs the SAME burst of simultaneous payments twice:
  1. with wallet locking OFF  (the "before": shows the lost-update bug)
  2. with wallet locking ON   (the "after": Step 6 fix)
and prints a results table for the report.

Uses the TEST database, so your sandbox data is never touched.

Run from the backend folder (Docker running, .venv active):
    python -m experiments.race_demo
    python -m experiments.race_demo --payments 100 --rounds 5
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app import config
from app.database import Base, get_db
from app.main import app
from app.models import LedgerEntry, Wallet
from app.seed import seed_sample_data

AMINA_PHONE = "254712000217"
AMINA_START = Decimal("12450.00")
AMOUNT = Decimal("100.00")


def prepare_test_database():
    name = make_url(config.TEST_DATABASE_URL).database
    admin = create_engine(config.DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).scalar():
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    engine = create_engine(config.TEST_DATABASE_URL, pool_size=40, max_overflow=20)
    return engine, sessionmaker(bind=engine, autoflush=False)


def run_once(engine, Session, n_payments: int, lock: bool) -> dict:
    config.LOCK_WALLETS = lock

    # Fresh tables + sample accounts for every run.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as s:
        seed_sample_data(s)

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db

    def send(i):
        with TestClient(app) as c:
            r = c.post(
                "/payments",
                json={"customer_phone": AMINA_PHONE, "merchant_code": "52011", "amount": str(AMOUNT)},
                headers={"Idempotency-Key": f"race-{i}"},
            )
            return r.json().get("status")

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(n_payments, 25)) as pool:
        statuses = list(pool.map(send, range(n_payments)))
    elapsed = time.perf_counter() - start

    with Session() as s:
        amina = s.query(Wallet).filter_by(owner_type="CUSTOMER", owner_id=1).one().balance
        merchant = s.query(Wallet).filter_by(owner_type="MERCHANT", owner_id=1).one().balance
        ledger_moved = s.query(func.sum(LedgerEntry.amount)).filter_by(entry_type="DEBIT").scalar() \
            or Decimal("0.00")

    successful = statuses.count("SUCCESSFUL")
    expected_amina = AMINA_START - AMOUNT * successful
    wallets_moved = AMINA_START - amina
    return {
        "successful": successful,
        "amina_expected": expected_amina,
        "amina_actual": amina,
        "merchant_actual": merchant,
        "lost_updates": int((amina - expected_amina) / AMOUNT),
        "ledger_matches": "yes" if ledger_moved == wallets_moved == merchant else "NO",
        "seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--payments", type=int, default=50, help="simultaneous payments per round")
    parser.add_argument("--rounds", type=int, default=3, help="repeat each mode this many times")
    args = parser.parse_args()

    engine, Session = prepare_test_database()
    print(f"\nScenario 4: {args.payments} simultaneous payments of KES {AMOUNT} from ONE wallet "
          f"(Amina, KES {AMINA_START}), {args.rounds} rounds per mode\n")
    header = f"{'Mode':<11}{'Round':>6}{'OK':>5}{'Amina expected':>16}{'Amina actual':>14}" \
             f"{'Merchant got':>14}{'Lost updates':>14}{'Wallets = ledger':>18}{'Time (s)':>10}"
    print(header)
    print("-" * len(header))

    for lock in (False, True):
        mode = "locks ON" if lock else "locks OFF"
        for r in range(1, args.rounds + 1):
            res = run_once(engine, Session, args.payments, lock)
            print(f"{mode:<11}{r:>6}{res['successful']:>5}{res['amina_expected']:>16}"
                  f"{res['amina_actual']:>14}{res['merchant_actual']:>14}{res['lost_updates']:>14}"
                  f"{res['ledger_matches']:>18}{res['seconds']:>10.2f}")
        print()

    config.LOCK_WALLETS = True
    app.dependency_overrides.clear()
    print("OK               = payments the API reported as SUCCESSFUL.")
    print("Lost updates     = deductions silently overwritten by another payment.")
    print("Wallets = ledger = do the wallet balances agree with what the ledger says moved?\n")


if __name__ == "__main__":
    main()
