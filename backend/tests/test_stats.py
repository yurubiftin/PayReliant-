"""Step 8 tests: the numbers the dashboard shows are calculated correctly."""

from decimal import Decimal

from tests.test_payments import AMINA, FAITH, MAMA_MBOGA, pay


def test_stats_on_empty_database(client):
    s = client.get("/stats").json()
    assert s["total_transactions"] == 0
    assert s["success_rate"] is None
    assert s["avg_processing_ms"] is None
    assert s["duplicates_blocked"] == 0
    assert s["ledger_balanced"] is True


def test_stats_after_payments(client):
    pay(client, "k1", AMINA, MAMA_MBOGA, "100.00")       # success
    pay(client, "k2", AMINA, MAMA_MBOGA, "250.00")       # success
    pay(client, "k3", FAITH, MAMA_MBOGA, "15000.00")     # fails: insufficient balance
    pay(client, "k1", AMINA, MAMA_MBOGA, "100.00")       # duplicate -> blocked
    pay(client, "k1", AMINA, MAMA_MBOGA, "100.00")       # duplicate -> blocked

    s = client.get("/stats").json()
    assert s["total_transactions"] == 3
    assert s["successful"] == 2
    assert s["failed"] == 1
    assert s["success_rate"] == 66.7
    assert s["duplicates_blocked"] == 2
    assert Decimal(s["volume_successful"]) == Decimal("350.00")
    assert s["avg_processing_ms"] > 0
    assert s["ledger_balanced"] is True


def test_each_transaction_records_processing_time_and_replays(client):
    first = pay(client, "k1", AMINA, MAMA_MBOGA, "100.00").json()
    assert first["processing_ms"] > 0
    assert first["replay_count"] == 0

    retry = pay(client, "k1", AMINA, MAMA_MBOGA, "100.00").json()
    assert retry["replay_count"] == 1


def test_transactions_limit(client):
    for i in range(4):
        pay(client, f"k{i}", AMINA, MAMA_MBOGA, "10.00")
    latest = client.get("/transactions?limit=2").json()
    assert [t["idempotency_key"] for t in latest] == ["k3", "k2"]


def test_cors_allows_the_dashboard(client):
    r = client.get("/stats", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
