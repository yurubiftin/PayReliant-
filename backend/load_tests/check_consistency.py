"""Check that the money is still correct after a load test (or any time).

    python -m load_tests.check_consistency            # check only
    python -m load_tests.check_consistency --top-up   # BEFORE a load test: give each demo customer KES 1,000,000

Checks:
  1. Total DEBITs == total CREDITs in the ledger (double-entry holds)
  2. Each successful transaction has exactly 2 ledger entries; failed ones have none
  3. No two transactions share an idempotency key (guaranteed by the UNIQUE rule)
  4. Every merchant wallet == the sum of its CREDIT ledger entries
  5. No transaction is stuck in PENDING/PROCESSING
"""

import sys
from decimal import Decimal

from sqlalchemy import func

from app.database import SessionLocal
from app.models import Customer, LedgerEntry, Merchant, Transaction, Wallet

LOAD_TEST_CUSTOMERS = ["254712000217", "254712000218", "254712000219"]


def top_up(db):
    for phone in LOAD_TEST_CUSTOMERS:
        c = db.query(Customer).filter_by(phone=phone).one()
        db.query(Wallet).filter_by(owner_type="CUSTOMER", owner_id=c.customer_id).one().balance = Decimal("1000000.00")
    db.commit()
    print("Demo customers topped up to KES 1,000,000 each (sandbox adjustment, not a payment).")


def main():
    db = SessionLocal()
    if "--top-up" in sys.argv:
        top_up(db)
        return

    total = lambda t: db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).filter(LedgerEntry.entry_type == t).scalar()
    debits, credits = total("DEBIT"), total("CREDIT")

    entries = dict(db.query(Transaction.status, func.count(LedgerEntry.entry_id))
                   .outerjoin(LedgerEntry).group_by(Transaction.status).all())
    counts = dict(db.query(Transaction.status, func.count()).group_by(Transaction.status).all())
    duplicate_keys = (db.query(Transaction.idempotency_key).group_by(Transaction.idempotency_key)
                      .having(func.count() > 1).count())

    bad_merchants = []
    for m in db.query(Merchant):
        w = db.query(Wallet).filter_by(owner_type="MERCHANT", owner_id=m.merchant_id).one()
        credited = (db.query(func.coalesce(func.sum(LedgerEntry.amount), 0))
                    .filter(LedgerEntry.wallet_id == w.wallet_id, LedgerEntry.entry_type == "CREDIT").scalar())
        if w.balance != credited:
            bad_merchants.append(f"{m.name}: wallet {w.balance} vs ledger {credited}")

    stuck = counts.get("PENDING", 0) + counts.get("PROCESSING", 0)
    checks = [
        ("Ledger balanced (debits == credits)", debits == credits, f"KES {debits} vs {credits}"),
        ("2 ledger entries per successful payment", entries.get("SUCCESSFUL", 0) == 2 * counts.get("SUCCESSFUL", 0),
         f"{entries.get('SUCCESSFUL', 0)} entries for {counts.get('SUCCESSFUL', 0)} payments"),
        ("No ledger entries for failed payments", entries.get("FAILED", 0) == 0, f"{entries.get('FAILED', 0)} entries"),
        ("No duplicate idempotency keys", duplicate_keys == 0, f"{duplicate_keys} duplicates"),
        ("Merchant wallets match the ledger", not bad_merchants, "; ".join(bad_merchants) or "all match"),
        ("No transactions stuck in progress", stuck == 0, f"{stuck} stuck"),
    ]
    print(f"Transactions: {sum(counts.values())}  ({counts})\n")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:45} {detail}")
    ok = all(c[1] for c in checks)
    print("\nAll consistency checks passed." if ok else "\nSOME CHECKS FAILED.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
