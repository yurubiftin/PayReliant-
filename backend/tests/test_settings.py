"""Step 9b tests: the Settings screen, and failure / latency injection.

Failure injection makes a payment fail ON PURPOSE in the middle, after the customer has been
debited but before anything is saved. These tests prove that no money is lost when that happens.
"""

from decimal import Decimal

from tests.conftest import GATEWAY
from tests.test_payments import AMINA, MAMA_MBOGA, balance, pay


def test_default_settings(client):
    r = client.get("/settings")
    assert r.status_code == 200
    s = r.json()
    assert s["provider_name"] == "PayReliant Sandbox"
    assert s["currency"] == "KES"
    assert s["failure_rate_pct"] == 0
    assert s["max_requests_per_test"] == 100


def test_admin_can_change_settings(client):
    r = client.put("/settings", json={"provider_name": "Safari Sandbox", "retry_attempts": 5})
    assert r.status_code == 200
    assert client.get("/settings").json()["provider_name"] == "Safari Sandbox"
    assert client.get("/settings").json()["retry_attempts"] == 5
    # fields not sent are left as they were
    assert client.get("/settings").json()["max_requests_per_test"] == 100


def test_settings_are_validated(client):
    assert client.put("/settings", json={"failure_rate_pct": 150}).status_code == 422
    assert client.put("/settings", json={"max_requests_per_test": 5}).status_code == 422
    assert client.put("/settings", json={"added_latency_ms": -1}).status_code == 422


def test_merchant_cannot_see_or_change_settings(merchant_client):
    assert merchant_client.get("/settings").status_code == 403
    assert merchant_client.put("/settings", json={"failure_rate_pct": 100}).status_code == 403


def test_simulator_can_read_public_settings(anon_client):
    assert anon_client.get("/settings/public").status_code == 401  # no key, no login
    r = anon_client.get("/settings/public", headers=GATEWAY)
    assert r.status_code == 200
    assert set(r.json()) == {"provider_name", "client_timeout_s", "retry_attempts"}  # nothing else leaks


def test_injected_failure_rolls_back_and_loses_no_money(client):
    client.put("/settings", json={"failure_rate_pct": 100})
    amina_before, merchant_before = balance(client, 1), balance(client, 4)

    r = pay(client, "inject-1", AMINA, MAMA_MBOGA, "500.00")

    assert r.status_code == 422
    assert r.json()["status"] == "FAILED"
    assert r.json()["failure_reason"] == "SIMULATED_FAILURE"
    assert r.json()["ledger_entries"] == []                 # the debit/credit were rolled back
    assert balance(client, 1) == amina_before                 # customer not charged
    assert balance(client, 4) == merchant_before              # merchant not credited


def test_injected_failure_is_replayed_not_retried(client):
    """A retry of a failed payment returns the SAME failure; it doesn't get a second chance to charge."""
    client.put("/settings", json={"failure_rate_pct": 100})
    pay(client, "inject-2", AMINA, MAMA_MBOGA, "500.00")
    client.put("/settings", json={"failure_rate_pct": 0})

    retry = pay(client, "inject-2", AMINA, MAMA_MBOGA, "500.00")
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert retry.json()["failure_reason"] == "SIMULATED_FAILURE"
    assert balance(client, 1) == Decimal("12450.00")


def test_failure_rate_zero_means_normal_payments(client):
    r = pay(client, "normal-1", AMINA, MAMA_MBOGA, "500.00")
    assert r.status_code == 201


def test_added_latency_slows_payments(client):
    client.put("/settings", json={"added_latency_ms": 300})
    r = pay(client, "slow-1", AMINA, MAMA_MBOGA, "100.00")
    assert r.status_code == 201
    assert r.json()["processing_ms"] >= 300
