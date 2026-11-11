"""Reliability test runner (Step 9b): the "Run test" buttons on the Reliability Tests screen.

Each scenario fires many payments through the REAL payment logic (process_payment), in parallel,
then checks that the money is still correct. They map to Table 4.6 of the proposal:

  duplicate   Scenario 2: the same payment sent 5 times at once         -> charged once
  timeout     Scenario 3: the server is slower than the client's timeout,
                          so the client retries with the same key         -> charged once
  failed      Scenario 5 + failure injection: insufficient balance, and a
                          failure in the MIDDLE of a payment              -> no money moves
  concurrent  Scenario 4: many different payments from one wallet at once -> every one counted

The tests use two dedicated sandbox accounts ("Reliability Test Customer" / merchant 59999),
so they never touch the demo customers' money. Each run gets fresh idempotency keys.
"""

import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.models import Customer, LedgerEntry, Merchant, ReliabilityRun, Transaction, Wallet
from app.services.payments import (
    KeyReuseMismatchError,
    NotFoundError,
    PaymentInProgressError,
    process_payment,
)
from app.services.sandbox_settings import get_settings

SCENARIOS = ("duplicate", "timeout", "failed", "concurrent")
TEST_PHONE = "254700000999"
TEST_MERCHANT_CODE = "59999"
AMOUNT = Decimal("100.00")
WORKERS = 10  # payments in flight at the same time


# --- Helpers -----------------------------------------------------------------------

def _ensure_test_accounts(db: Session, customer_balance: Decimal) -> None:
    """Create the dedicated test accounts if needed, and give the test customer a fresh balance.

    (A balance top-up is a sandbox adjustment, not a payment, so it has no ledger entry.
    Checks below compare BEFORE/AFTER differences, so the top-up doesn't affect them.)
    """
    customer = db.query(Customer).filter_by(phone=TEST_PHONE).first()
    if customer is None:
        customer = Customer(name="Reliability Test Customer", phone=TEST_PHONE)
        db.add(customer)
        db.flush()
        db.add(Wallet(owner_type="CUSTOMER", owner_id=customer.customer_id))
    customer.status = "ACTIVE"
    merchant = db.query(Merchant).filter_by(business_code=TEST_MERCHANT_CODE).first()
    if merchant is None:
        merchant = Merchant(name="Reliability Test Merchant", business_code=TEST_MERCHANT_CODE)
        db.add(merchant)
        db.flush()
        db.add(Wallet(owner_type="MERCHANT", owner_id=merchant.merchant_id))
    merchant.status = "ACTIVE"
    db.flush()
    _wallet(db, "CUSTOMER", customer.customer_id).balance = customer_balance
    db.commit()


def _wallet(db: Session, owner_type: str, owner_id: int) -> Wallet:
    return db.query(Wallet).filter_by(owner_type=owner_type, owner_id=owner_id).one()


def _balances(db: Session) -> tuple[Decimal, Decimal]:
    db.expire_all()
    customer = db.query(Customer).filter_by(phone=TEST_PHONE).one()
    merchant = db.query(Merchant).filter_by(business_code=TEST_MERCHANT_CODE).one()
    return (_wallet(db, "CUSTOMER", customer.customer_id).balance,
            _wallet(db, "MERCHANT", merchant.merchant_id).balance)


def _pay(factory, key, amount=AMOUNT, **inject) -> tuple[str, bool, float]:
    """One payment in its own database session. Returns (outcome, replayed, milliseconds)."""
    started = time.perf_counter()
    with factory() as db:
        try:
            result = process_payment(db, idempotency_key=key, customer_phone=TEST_PHONE,
                                     merchant_code=TEST_MERCHANT_CODE, amount=amount, **inject)
            t = result.transaction
            outcome = t.status if t.status == "SUCCESSFUL" else f"FAILED:{t.failure_reason}"
            replayed = result.replayed
        except PaymentInProgressError:
            outcome, replayed = "IN_PROGRESS", False
        except KeyReuseMismatchError:
            outcome, replayed = "KEY_MISMATCH", False
        except NotFoundError:
            outcome, replayed = "NOT_FOUND", False
    return outcome, replayed, (time.perf_counter() - started) * 1000


def _ledger_and_txns(db: Session, prefix: str):
    txns = db.query(Transaction).filter(Transaction.idempotency_key.like(f"{prefix}%"))
    debits = (db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).join(Transaction)
              .filter(Transaction.idempotency_key.like(f"{prefix}%"), LedgerEntry.entry_type == "DEBIT").scalar())
    return txns, Decimal(debits)


def _lost(charged: Decimal, expected: Decimal) -> int:
    """How many payments' worth of money is unaccounted for (a lost update loses one payment)."""
    return int(abs(expected - charged) / AMOUNT)


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(ok), "detail": detail}


def _p95(times: list[float]) -> float | None:
    if not times:
        return None
    return round(statistics.quantiles(times, n=20)[-1], 1) if len(times) >= 2 else round(times[0], 1)


# --- Scenarios ---------------------------------------------------------------------

def _duplicate(db, factory, n, prefix, settings):
    payments = max(1, n // 5)
    _ensure_test_accounts(db, Decimal(payments) * AMOUNT + 1000)
    c0, m0 = _balances(db)
    requests = [f"{prefix}{i}" for i in range(payments) for _ in range(5)]  # each key 5 times
    random.shuffle(requests)
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda k: _pay(factory, k, inject_failure=False, inject_latency_ms=0), requests))
    c1, m1 = _balances(db)
    txns, ledger = _ledger_and_txns(db, prefix)
    charged, expected = c0 - c1, Decimal(payments) * AMOUNT
    safe = sum(r[0] in ("SUCCESSFUL", "IN_PROGRESS") for r in results)  # charged-or-told-to-wait
    checks = [
        _check("One transaction per idempotency key", txns.count() == payments,
               f"{txns.count()} transactions for {payments} keys"),
        _check("Customer charged once per payment", charged == expected, f"charged KES {charged}, expected {expected}"),
        _check("Merchant received exactly that amount", m1 - m0 == expected, f"received KES {m1 - m0}"),
        _check("Wallets agree with the ledger", ledger == charged, f"ledger debits KES {ledger}"),
    ]
    summary = (f"{payments} payments were each sent 5 times at once ({len(requests)} requests): "
               f"{sum(r[1] for r in results)} replayed, {sum(r[0] == 'IN_PROGRESS' for r in results)} told to retry.")
    passed = max(0, safe - _lost(charged, expected) * 5)  # each lost payment = its 5 requests wrong
    return len(requests), passed, checks, [r[2] for r in results], summary


def _timeout(db, factory, n, prefix, settings):
    payments = max(1, n // 10)
    _ensure_test_accounts(db, Decimal(payments) * AMOUNT + 1000)
    c0, _ = _balances(db)
    timeout_s = settings.client_timeout_s
    server_delay_ms = timeout_s * 2000  # the server is twice as slow as the client is willing to wait

    def client(i):
        """A client that gives up after timeout_s, then retries with the SAME key."""
        key = f"{prefix}{i}"
        sent, times = 1, []
        with ThreadPoolExecutor(1) as one:
            first = one.submit(_pay, factory, key, inject_failure=False, inject_latency_ms=server_delay_ms)
            try:
                outcome = first.result(timeout=timeout_s)[0]  # the reply arrives in time? (it won't)
                return sent, outcome == "SUCCESSFUL", times
            except FutureTimeout:
                pass  # timed out: the client doesn't know whether the payment happened
            for _ in range(settings.retry_attempts):
                time.sleep(timeout_s)
                outcome, replayed, ms = _pay(factory, key, inject_failure=False, inject_latency_ms=0)
                sent += 1
                times.append(ms)
                if outcome == "SUCCESSFUL":
                    return sent, replayed, times  # correct only if it was the ORIGINAL result replayed
            return sent, False, times  # retries exhausted without an answer

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(client, range(payments)))
    c1, _ = _balances(db)
    txns, ledger = _ledger_and_txns(db, prefix)
    charged, expected = c0 - c1, Decimal(payments) * AMOUNT
    requests = sum(r[0] for r in results)
    resolved = sum(r[1] for r in results)
    stuck = txns.filter(Transaction.status.in_(("PENDING", "PROCESSING"))).count()
    checks = [
        _check("Every timed-out payment resolved by a retry", resolved == payments,
               f"{resolved} of {payments} clients got the original result back"),
        _check("Customer charged once per payment", charged == expected, f"charged KES {charged}, expected {expected}"),
        _check("No transactions left stuck in PROCESSING", stuck == 0, f"{stuck} stuck"),
        _check("Wallets agree with the ledger", ledger == charged, f"ledger debits KES {ledger}"),
    ]
    summary = (f"Server delayed {server_delay_ms / 1000:.1f} s vs client timeout {timeout_s} s; "
               f"{payments} clients retried up to {settings.retry_attempts} times with the same key.")
    times = [t for r in results for t in r[2]]
    wrong_clients = max(payments - resolved, _lost(charged, expected), stuck)
    passed = requests - min(requests, wrong_clients * (settings.retry_attempts + 1))
    return requests, passed, checks, times, summary


def _failed(db, factory, n, prefix, settings):
    half = max(1, n // 4)
    _ensure_test_accounts(db, Decimal("1000.00"))  # less than one 5,000 payment
    c0, m0 = _balances(db)
    jobs = ([(f"{prefix}low{i}", Decimal("5000.00"), False, "FAILED:INSUFFICIENT_BALANCE") for i in range(half)]
            + [(f"{prefix}sim{i}", AMOUNT, True, "FAILED:SIMULATED_FAILURE") for i in range(half)])
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(
            lambda j: (_pay(factory, j[0], j[1], inject_failure=j[2], inject_latency_ms=0), j[3]), jobs))
    c1, m1 = _balances(db)
    txns, ledger = _ledger_and_txns(db, prefix)
    correct = sum(outcome[0] == expected for outcome, expected in results)
    without_reason = txns.filter(Transaction.failure_reason.is_(None)).count()
    checks = [
        _check("Every payment failed with the right reason", correct == len(jobs), f"{correct} of {len(jobs)}"),
        _check("No money moved (customer balance unchanged)", c1 == c0, f"KES {c0} -> {c1}"),
        _check("Merchant balance unchanged", m1 == m0, f"KES {m0} -> {m1}"),
        _check("Mid-payment failures rolled back (no ledger entries)", ledger == 0, f"ledger debits KES {ledger}"),
        _check("Every failure recorded with a reason", without_reason == 0, f"{without_reason} without a reason"),
    ]
    summary = (f"{half} payments above the balance, and {half} payments made to fail ON PURPOSE after the "
               f"customer was debited (before commit): all must fail with no money lost.")
    return len(jobs), correct, checks, [r[0][2] for r in results], summary


def _concurrent(db, factory, n, prefix, settings):
    _ensure_test_accounts(db, Decimal(n) * AMOUNT)
    c0, m0 = _balances(db)
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda i: _pay(factory, f"{prefix}{i}", inject_failure=False, inject_latency_ms=0),
                                range(n)))
    c1, m1 = _balances(db)
    _, ledger = _ledger_and_txns(db, prefix)
    ok = sum(r[0] == "SUCCESSFUL" for r in results)
    expected = Decimal(n) * AMOUNT
    checks = [
        _check("Every payment succeeded", ok == n, f"{ok} of {n}"),
        _check("Customer debited exactly once per payment (no lost updates)", c0 - c1 == expected,
               f"debited KES {c0 - c1}, expected {expected}"),
        _check("Merchant credited exactly", m1 - m0 == expected, f"credited KES {m1 - m0}"),
        _check("Wallets agree with the ledger", ledger == c0 - c1, f"ledger debits KES {ledger}"),
    ]
    ok = max(0, ok - _lost(c0 - c1, expected))
    summary = f"{n} different payments from ONE wallet, {WORKERS} at a time, all competing for the same balance."
    return n, ok, checks, [r[2] for r in results], summary


RUNNERS = {"duplicate": _duplicate, "timeout": _timeout, "failed": _failed, "concurrent": _concurrent}


def run_scenario(db: Session, factory: sessionmaker, scenario: str) -> ReliabilityRun:
    settings = get_settings(db)
    n = max(10, min(settings.max_requests_per_test, 500))
    prefix = f"rt-{scenario}-{uuid4().hex[:8]}-"
    started = time.perf_counter()
    requests, passed, checks, times, summary = RUNNERS[scenario](db, factory, n, prefix, settings)
    run = ReliabilityRun(
        scenario=scenario,
        requests=requests,
        passed=passed,
        failed=requests - passed,
        status="PASSED" if all(c["passed"] for c in checks) else "FAILED",
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        p95_ms=_p95(times),
        checks=checks,
        summary=summary,
    )
    db.add(run)
    db.commit()
    return run
