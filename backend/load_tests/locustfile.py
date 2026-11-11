"""Load test (Step 10): many simulated USSD users paying at the same time.

Proposal 3.4.2: "Load testing - ensure the system works under normal and peak loads, such as
during the holidays when transactions are in excess."

Each simulated user behaves like a phone on the USSD gateway:
  - mostly makes payments (each with its own idempotency key),
  - sometimes RETRIES a payment with the same key (a dropped reply),
  - sometimes checks a balance.

Run it (API must be running, in a second terminal):
    cd backend
    locust -f load_tests/locustfile.py --host http://127.0.0.1:8000
then open http://localhost:8089, choose e.g. 50 users, spawn rate 10, and press Start.

Or without the web page, for a fixed 60-second run that saves results to CSV files:
    locust -f load_tests/locustfile.py --host http://127.0.0.1:8000 --headless -u 50 -r 10 -t 60s --csv load_tests/results/peak

After a run, check the money is still right:  python -m load_tests.check_consistency
"""

import os
import random
import uuid

from locust import HttpUser, between, task

API_KEY = os.getenv("GATEWAY_API_KEY", "sk_sandbox_ussd_gateway")
# Customers are the three demo customers; they get topped up by check_consistency --top-up.
CUSTOMERS = ["254712000217", "254712000218", "254712000219"]
MERCHANTS = ["52011", "52012", "52013"]


class UssdUser(HttpUser):
    wait_time = between(0.5, 2)  # a person takes a moment between USSD steps

    def on_start(self):
        self.client.headers.update({"X-API-Key": API_KEY})
        self.phone = random.choice(CUSTOMERS)
        self.last = None  # (key, payload) of the previous payment, to retry

    def _pay(self, key, payload, name):
        with self.client.post("/payments", json=payload, headers={"Idempotency-Key": key},
                              name=name, catch_response=True) as r:
            # 201 = paid; 422 FAILED = e.g. insufficient balance: both are CORRECT answers.
            # 409 = the same key is still in progress: also a correct, safe answer.
            if r.status_code in (201, 409) or (r.status_code == 422 and r.json().get("status") == "FAILED"):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}: {r.text[:120]}")

    @task(10)
    def pay(self):
        payload = {"customer_phone": self.phone, "merchant_code": random.choice(MERCHANTS),
                   "amount": f"{random.randint(1, 50)}.00"}
        key = f"load-{uuid.uuid4()}"
        self._pay(key, payload, "POST /payments (new)")
        self.last = (key, payload)

    @task(2)
    def retry_last_payment(self):
        """The reply to the last payment 'was lost', so the phone retries with the SAME key."""
        if self.last:
            self._pay(*self.last, "POST /payments (retry, same key)")

    @task(3)
    def check_balance(self):
        self.client.get(f"/customers/{self.phone}/balance", name="GET /customers/[phone]/balance")
