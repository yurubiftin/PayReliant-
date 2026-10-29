"""Step 7 tests: the balance endpoint and the simulator page."""

from decimal import Decimal

from tests.test_payments import AMINA, MAMA_MBOGA, pay


def test_customer_balance(client):
    response = client.get(f"/customers/{AMINA}/balance")
    assert response.status_code == 200
    assert response.json()["name"] == "Amina W."
    assert Decimal(response.json()["balance"]) == Decimal("12450.00")


def test_customer_balance_after_payment(client):
    pay(client, "k1", AMINA, MAMA_MBOGA, "450.00")
    assert Decimal(client.get(f"/customers/{AMINA}/balance").json()["balance"]) == Decimal("12000.00")


def test_unknown_customer_balance_is_404(client):
    assert client.get("/customers/254700000000/balance").status_code == 404


def test_simulator_page_is_served(client):
    response = client.get("/simulator/")
    assert response.status_code == 200
    assert "USSD Simulator" in response.text
