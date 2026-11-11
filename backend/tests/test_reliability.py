"""Step 9b tests: the Reliability Tests screen.

Each scenario must PASS on our system: every consistency check holds.
max_requests_per_test is lowered to keep the test suite quick.
"""

import pytest


@pytest.fixture
def quick(client):
    client.put("/settings", json={"max_requests_per_test": 20, "client_timeout_s": 0.2, "retry_attempts": 3})
    return client


@pytest.mark.parametrize("scenario", ["duplicate", "timeout", "failed", "concurrent"])
def test_scenario_passes(quick, scenario):
    r = quick.post(f"/reliability/run/{scenario}")
    assert r.status_code == 200, r.text
    run = r.json()
    failed_checks = [c for c in run["checks"] if not c["passed"]]
    assert failed_checks == []
    assert run["status"] == "PASSED"
    assert run["failed"] == 0
    assert run["requests"] > 0


def test_duplicate_scenario_sends_each_payment_five_times(quick):
    run = quick.post("/reliability/run/duplicate").json()
    assert run["requests"] == 20  # 4 payments x 5 copies


def test_runs_are_listed_newest_first(quick):
    quick.post("/reliability/run/concurrent")
    quick.post("/reliability/run/failed")
    runs = quick.get("/reliability/runs").json()
    assert [r["scenario"] for r in runs] == ["failed", "concurrent"]


def test_tests_do_not_touch_demo_customers(quick):
    before = quick.get("/wallets").json()[:6]
    quick.post("/reliability/run/concurrent")
    assert quick.get("/wallets").json()[:6] == before


def test_unknown_scenario(quick):
    assert quick.post("/reliability/run/banana").status_code == 404


def test_merchant_cannot_run_tests(merchant_client):
    assert merchant_client.post("/reliability/run/duplicate").status_code == 403
    assert merchant_client.get("/reliability/runs").status_code == 403
