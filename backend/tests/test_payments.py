"""Step 3 tests: payments move money correctly, or not at all.

Sample accounts (from seed.py):
  Amina  254712000217  KES 12,450.00   -> wallet 1
  Brian  254712000218  KES  3,020.00   -> wallet 2
  Faith  254712000219  KES    800.00   -> wallet 3
  Mama Mboga 52011, Kibanda Cafe 52012, Tuko Books 52013 -> wallets 4, 5, 6 (KES 0)
"""

from decimal import Decimal

from sqlalchemy import func

from app.models import LedgerEntry, Transaction, Wallet

AMINA = "254712000217"
FAITH = "254712000219"
MAMA_MBOGA = "52011"
STARTING_TOTAL = Decimal("16270.00")  # 12,450 + 3,020 + 800


def pay(client, key, phone, code, amount):
    return client.post(
        "/payments",
        json={"customer_phone": phone, "merchant_code": code, "amount": amount},
        headers={"Idempotency-Key": key},
    )


def balance(client, wallet_id):
    wallets = {w["wallet_id"]: w for w in client.get("/wallets").json()}
    return Decimal(wallets[wallet_id]["balance"])


# --- Scenario 1 (table 4.6): normal payment -----------------------------------

def test_successful_payment_moves_money(client):
    response = pay(client, "key-1", AMINA, MAMA_MBOGA, "500.00")

    assert response.status_code == 201
    txn = response.json()
    assert txn["status"] == "SUCCESSFUL"
    assert balance(client, 1) == Decimal("11950.00")  # Amina: 12,450 - 500
    assert balance(client, 4) == Decimal("500.00")    # Mama Mboga: 0 + 500


def test_successful_payment_writes_two_ledger_entries(client):
    txn = pay(client, "key-1", AMINA, MAMA_MBOGA, "500.00").json()

    entries = txn["ledger_entries"]
    assert [(e["entry_type"], e["wallet_id"], e["amount"]) for e in entries] == [
        ("DEBIT", 1, "500.00"),
        ("CREDIT", 4, "500.00"),
    ]


# --- Scenario 5 (table 4.6): insufficient balance -----------------------------

def test_insufficient_balance_fails_without_moving_money(client):
    response = pay(client, "key-1", FAITH, MAMA_MBOGA, "15000.00")  # Faith has 800

    assert response.status_code == 422
    txn = response.json()
    assert txn["status"] == "FAILED"
    assert txn["failure_reason"] == "INSUFFICIENT_BALANCE"
    assert txn["ledger_entries"] == []
    assert balance(client, 3) == Decimal("800.00")  # unchanged
    assert balance(client, 4) == Decimal("0.00")    # unchanged


def test_paying_exact_balance_is_allowed(client):
    response = pay(client, "key-1", FAITH, MAMA_MBOGA, "800.00")
    assert response.json()["status"] == "SUCCESSFUL"
    assert balance(client, 3) == Decimal("0.00")


# --- Bad requests are rejected before anything is saved -----------------------

def test_unknown_merchant_is_rejected(client, db):
    response = pay(client, "key-1", AMINA, "99999", "100.00")
    assert response.status_code == 404
    assert db.query(Transaction).count() == 0


def test_invalid_amounts_are_rejected(client, db):
    for bad_amount in ["0", "-50.00", "10.555", "abc"]:
        response = pay(client, f"key-{bad_amount}", AMINA, MAMA_MBOGA, bad_amount)
        assert response.status_code == 422, bad_amount
    assert db.query(Transaction).count() == 0


def test_missing_idempotency_key_is_rejected(client):
    response = client.post(
        "/payments",
        json={"customer_phone": AMINA, "merchant_code": MAMA_MBOGA, "amount": "100.00"},
    )
    assert response.status_code == 422


# (Repeated keys / retries are tested in test_idempotency.py)


# --- The two rules that must ALWAYS hold ---------------------------------------

def test_money_is_never_created_or_destroyed(client, db):
    pay(client, "k1", AMINA, MAMA_MBOGA, "1250.00")
    pay(client, "k2", AMINA, "52012", "480.00")
    pay(client, "k3", FAITH, "52013", "15000.00")  # fails
    pay(client, "k4", "254712000218", MAMA_MBOGA, "2100.00")

    db.expire_all()
    total = db.query(func.sum(Wallet.balance)).scalar()
    assert total == STARTING_TOTAL


def test_ledger_debits_equal_credits(client, db):
    pay(client, "k1", AMINA, MAMA_MBOGA, "1250.00")
    pay(client, "k2", AMINA, "52012", "480.00")

    debits = db.query(func.sum(LedgerEntry.amount)).filter_by(entry_type="DEBIT").scalar()
    credits = db.query(func.sum(LedgerEntry.amount)).filter_by(entry_type="CREDIT").scalar()
    assert debits == credits == Decimal("1730.00")


# --- Reading transactions back --------------------------------------------------

def test_list_and_get_transactions(client):
    first = pay(client, "k1", AMINA, MAMA_MBOGA, "100.00").json()
    pay(client, "k2", AMINA, MAMA_MBOGA, "200.00")

    listed = client.get("/transactions").json()
    assert [t["idempotency_key"] for t in listed] == ["k2", "k1"]  # newest first

    one = client.get(f"/transactions/{first['transaction_id']}")
    assert one.status_code == 200
    assert one.json()["amount"] == "100.00"

    assert client.get("/transactions/9999").status_code == 404
