"""Step 2 tests: accounts and wallets exist, and the database protects them."""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Wallet


def test_list_customers(client):
    response = client.get("/customers")
    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Amina W.", "Brian O.", "Faith K."]


def test_list_merchants(client):
    response = client.get("/merchants")
    assert response.status_code == 200
    assert [m["business_code"] for m in response.json()] == ["52011", "52012", "52013"]


def test_every_account_has_a_wallet(client):
    wallets = client.get("/wallets").json()
    assert len(wallets) == 6  # 3 customers + 3 merchants
    assert Decimal(wallets[0]["balance"]) == Decimal("12450.00")


def test_database_rejects_negative_balance(db):
    """Even if our Python code had a bug, PostgreSQL refuses a negative balance."""
    wallet = db.query(Wallet).first()
    wallet.balance = Decimal("-1.00")
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_second_wallet_for_same_owner(db):
    """One owner, one wallet — money can't hide in a duplicate wallet."""
    db.add(Wallet(owner_type="CUSTOMER", owner_id=1, balance=Decimal("100.00")))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
