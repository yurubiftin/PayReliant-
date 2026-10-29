"""Step 6 tests: Scenario 4 (concurrent requests), table 4.6.

Idempotency (Step 5) stops the SAME payment being processed twice.
These tests are about DIFFERENT payments (different keys) hitting the SAME wallet
at the same instant. Without locking, two payments can both read the old balance
and one deduction gets lost ("lost update"), creating money out of nothing.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func

from app.main import app
from app.models import LedgerEntry, Transaction, Wallet

from tests.test_payments import AMINA, FAITH, MAMA_MBOGA, STARTING_TOTAL, balance, pay


def send_in_parallel(requests):
    """Fire all requests at the same moment, each from its own connection."""

    def send(req):
        key, phone, code, amount = req
        with TestClient(app) as c:
            return pay(c, key, phone, code, amount).json()["status"]

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(send, requests))


def test_twenty_simultaneous_payments_from_one_wallet_all_count(client, db):
    """20 different payments of 100 from Amina at once -> she must lose exactly 2,000."""
    requests = [(f"amina-{i}", AMINA, MAMA_MBOGA, "100.00") for i in range(20)]

    statuses = send_in_parallel(requests)

    assert statuses.count("SUCCESSFUL") == 20
    assert balance(client, 1) == Decimal("10450.00")  # 12,450 - 20 x 100
    assert balance(client, 4) == Decimal("2000.00")   # merchant received exactly 2,000


def test_simultaneous_payments_cannot_overspend(client, db):
    """Faith has 800. Ten payments of 100 at once -> exactly 8 succeed, 2 fail."""
    requests = [(f"faith-{i}", FAITH, MAMA_MBOGA, "100.00") for i in range(10)]

    statuses = send_in_parallel(requests)

    assert statuses.count("SUCCESSFUL") == 8
    assert statuses.count("FAILED") == 2
    assert balance(client, 3) == Decimal("0.00")
    assert balance(client, 4) == Decimal("800.00")


def test_money_is_conserved_under_concurrent_load(client, db):
    """Customers paying several merchants at once: no money created or destroyed."""
    requests = []
    for i in range(10):
        requests.append((f"a-{i}", AMINA, "52011", "250.00"))
        requests.append((f"b-{i}", "254712000218", "52012", "150.00"))
        requests.append((f"f-{i}", FAITH, "52013", "120.00"))

    send_in_parallel(requests)

    db.expire_all()
    assert db.query(func.sum(Wallet.balance)).scalar() == STARTING_TOTAL
    debits = db.query(func.sum(LedgerEntry.amount)).filter_by(entry_type="DEBIT").scalar()
    credits = db.query(func.sum(LedgerEntry.amount)).filter_by(entry_type="CREDIT").scalar()
    assert debits == credits
    # Every SUCCESSFUL transaction has exactly two ledger entries.
    successful = db.query(Transaction).filter_by(status="SUCCESSFUL").count()
    assert db.query(LedgerEntry).count() == successful * 2
