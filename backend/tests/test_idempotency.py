"""Step 5 tests: Scenario 2 (duplicate request) and Scenario 3 (timeout / retry), table 4.6.

The promise: sending the same request again with the same Idempotency-Key
NEVER charges the customer twice, and the client gets the original result back.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models import LedgerEntry, Transaction

from tests.test_payments import AMINA, FAITH, MAMA_MBOGA, balance, pay


def test_retry_returns_original_result_and_charges_once(client):
    first = pay(client, "retry-key", AMINA, MAMA_MBOGA, "500.00")
    retry = pay(client, "retry-key", AMINA, MAMA_MBOGA, "500.00")

    assert first.status_code == retry.status_code == 201
    assert retry.json()["transaction_id"] == first.json()["transaction_id"]  # same transaction
    assert first.headers["Idempotent-Replayed"] == "false"
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert balance(client, 1) == Decimal("11950.00")  # 12,450 - 500, charged ONCE


def test_many_retries_still_charge_once(client, db):
    for _ in range(5):
        pay(client, "retry-key", AMINA, MAMA_MBOGA, "500.00")

    assert db.query(Transaction).count() == 1
    assert db.query(LedgerEntry).count() == 2
    assert balance(client, 1) == Decimal("11950.00")


def test_retry_of_failed_payment_returns_same_failure(client, db):
    first = pay(client, "fail-key", FAITH, MAMA_MBOGA, "15000.00")
    retry = pay(client, "fail-key", FAITH, MAMA_MBOGA, "15000.00")

    assert first.status_code == retry.status_code == 422
    assert retry.json()["status"] == "FAILED"
    assert retry.json()["transaction_id"] == first.json()["transaction_id"]
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert db.query(Transaction).count() == 1


def test_same_key_for_different_payment_is_rejected(client):
    pay(client, "key-A", AMINA, MAMA_MBOGA, "500.00")
    different = pay(client, "key-A", AMINA, MAMA_MBOGA, "900.00")  # different amount!

    assert different.status_code == 422
    assert "different payment" in different.json()["detail"]
    assert balance(client, 1) == Decimal("11950.00")  # the 900 was NOT charged


def test_retry_while_first_request_still_processing_is_told_to_wait(client, db):
    # Simulate a first request that is still mid-way (e.g. slow network, server busy).
    db.add(Transaction(idempotency_key="slow-key", customer_id=1, merchant_id=1,
                       amount=Decimal("500.00"), status="PROCESSING"))
    db.commit()

    retry = pay(client, "slow-key", AMINA, MAMA_MBOGA, "500.00")

    assert retry.status_code == 409
    assert retry.headers["Retry-After"] == "1"
    assert balance(client, 1) == Decimal("12450.00")  # nothing charged by the retry


def test_ten_identical_requests_at_the_same_instant_charge_once(client, db):
    """The hardest case: duplicates arriving simultaneously, not one after another."""

    def send(_):
        with TestClient(app) as c:  # each thread acts as a separate phone/connection
            return pay(c, "burst-key", AMINA, MAMA_MBOGA, "500.00").status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(send, range(10)))

    # Each request either got the result (201) or was told "still processing, retry" (409).
    assert set(codes) <= {201, 409}
    assert db.query(Transaction).count() == 1
    assert db.query(LedgerEntry).count() == 2
    assert balance(client, 1) == Decimal("11950.00")
