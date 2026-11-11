"""Step 9a tests: authentication and authorization (proposal 3.1.3 "Security", 3.5).

Checks that every protected operation is refused without the right credentials,
and that a merchant can only ever see their OWN data.
"""

from decimal import Decimal

from app import config
from app.models import User
from tests.conftest import GATEWAY, login
from tests.test_payments import AMINA, MAMA_MBOGA, pay

# --- Logging in --------------------------------------------------------------------


def test_admin_can_log_in(anon_client):
    r = anon_client.post("/auth/login", data={"username": "admin", "password": config.ADMIN_PASSWORD})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "ADMIN"
    assert r.json()["access_token"]


def test_wrong_password_is_rejected(anon_client):
    r = anon_client.post("/auth/login", data={"username": "admin", "password": "wrong-password"})
    assert r.status_code == 401


def test_unknown_user_gets_the_same_error_as_wrong_password(anon_client):
    r = anon_client.post("/auth/login", data={"username": "nobody", "password": "whatever"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect username or password."


def test_passwords_are_stored_only_as_hashes(db):
    admin = db.query(User).filter_by(username="admin").one()
    assert admin.password_hash != config.ADMIN_PASSWORD
    assert admin.password_hash.startswith("$argon2")


def test_me_returns_the_logged_in_merchant(merchant_client):
    me = merchant_client.get("/auth/me").json()
    assert me == {"username": "mamamboga", "role": "MERCHANT", "merchant_id": 1,
                  "merchant_name": "Mama Mboga Grocers"}


def test_forged_token_is_rejected(anon_client):
    r = anon_client.get("/stats", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


# --- Nothing protected works without credentials -----------------------------------


def test_protected_endpoints_require_login(anon_client):
    for path in ["/stats", "/transactions", "/transactions/1", "/wallets", "/customers", "/merchants", "/auth/me"]:
        assert anon_client.get(path).status_code == 401, path


def test_payments_require_the_gateway_api_key(anon_client):
    no_key = pay(anon_client, "k1", AMINA, MAMA_MBOGA, "100.00")
    wrong_key = anon_client.post(
        "/payments", json={"customer_phone": AMINA, "merchant_code": MAMA_MBOGA, "amount": "100.00"},
        headers={"Idempotency-Key": "k2", "X-API-Key": "wrong"})
    assert no_key.status_code == 401
    assert wrong_key.status_code == 401


def test_gateway_key_cannot_read_monitoring_data(anon_client):
    """The USSD gateway may submit payments, but it is not a dashboard user."""
    assert anon_client.get("/transactions", headers=GATEWAY).status_code == 401


def test_health_stays_public(anon_client):
    assert anon_client.get("/health").status_code == 200


# --- A merchant sees ONLY their own data --------------------------------------------


def test_merchant_sees_only_their_own_transactions(client, merchant_client):
    pay(client, "k1", AMINA, "52011", "100.00")  # to Mama Mboga (the logged-in merchant)
    pay(client, "k2", AMINA, "52012", "200.00")  # to Kibanda Cafe (someone else)

    theirs = merchant_client.get("/transactions").json()
    assert [t["merchant_id"] for t in theirs] == [1]

    other = client.get("/transactions").json()[0]  # the Kibanda payment (newest)
    assert merchant_client.get(f"/transactions/{other['transaction_id']}").status_code == 404


def test_merchant_stats_cover_only_their_business(client, merchant_client):
    pay(client, "k1", AMINA, "52011", "100.00")
    pay(client, "k2", AMINA, "52012", "200.00")
    s = merchant_client.get("/stats").json()
    assert s["total_transactions"] == 1
    assert Decimal(s["volume_successful"]) == Decimal("100.00")
    assert client.get("/stats").json()["total_transactions"] == 2  # admin sees both


def test_merchant_sees_only_their_own_wallet(merchant_client):
    wallets = merchant_client.get("/wallets").json()
    assert [(w["owner_type"], w["owner_id"]) for w in wallets] == [("MERCHANT", 1)]


def test_merchant_cannot_do_admin_operations(merchant_client):
    assert merchant_client.get("/customers").status_code == 403
    assert merchant_client.post("/customers", json={
        "name": "X", "phone": "254712999999", "initial_balance": "10.00"}).status_code == 403
    assert merchant_client.patch("/merchants/2", json={"status": "SUSPENDED"}).status_code == 403


def test_merchant_list_hides_login_usernames_from_non_admins(client, merchant_client):
    assert merchant_client.get("/merchants").json()[0]["login_username"] is None
    assert client.get("/merchants").json()[0]["login_username"] == "mamamboga"


# --- Account management (admin) -----------------------------------------------------


def test_admin_creates_customer_with_wallet(client):
    r = client.post("/customers", json={"name": "Wanjiku M.", "phone": "254712000220", "initial_balance": "5000.00"})
    assert r.status_code == 201
    assert Decimal(client.get("/customers/254712000220/balance").json()["balance"]) == Decimal("5000.00")


def test_customer_phone_must_be_kenyan_format(client):
    r = client.post("/customers", json={"name": "Bad", "phone": "0712000220", "initial_balance": "1.00"})
    assert r.status_code == 422


def test_duplicate_customer_phone_is_rejected(client):
    r = client.post("/customers", json={"name": "Copy", "phone": AMINA, "initial_balance": "1.00"})
    assert r.status_code == 409


def test_admin_onboards_merchant_who_can_then_log_in(client, anon_client):
    r = client.post("/merchants", json={"name": "Duka La Mama", "business_code": "52014",
                                         "username": "dukalamama", "password": "Duka@2026!"})
    assert r.status_code == 201
    assert r.json()["login_username"] == "dukalamama"
    headers = login(anon_client, "dukalamama", "Duka@2026!")
    assert anon_client.get("/auth/me", headers=headers).json()["merchant_name"] == "Duka La Mama"


def test_suspended_merchant_cannot_receive_payments_or_log_in(client, anon_client):
    client.patch("/merchants/1", json={"status": "SUSPENDED"})

    assert pay(client, "k1", AMINA, "52011", "100.00").status_code == 404
    r = anon_client.post("/auth/login", data={"username": "mamamboga", "password": config.DEMO_MERCHANT_PASSWORD})
    assert r.status_code == 401

    client.patch("/merchants/1", json={"status": "ACTIVE"})  # re-activate: works again
    assert pay(client, "k2", AMINA, "52011", "100.00").status_code == 201


def test_suspended_customer_cannot_pay(client):
    client.patch("/customers/1", json={"status": "SUSPENDED"})
    assert pay(client, "k1", AMINA, MAMA_MBOGA, "100.00").status_code == 404
