# PayReliant — USSD Mobile Payment Reliability Sandbox & API Gateway

[![tests](https://github.com/yurubiftin/PayReliant-/actions/workflows/tests.yml/badge.svg)](https://github.com/yurubiftin/PayReliant-/actions/workflows/tests.yml)

Final-year Software Engineering project, USIU-Africa (APT 3090A, FS 2026).
Student: Yurub Ahmed (671438) · Supervisor: Fredrick Ogore

A controlled academic sandbox for simulating USSD mobile-money payments and testing
how a payment system stays correct when requests are **duplicated, fail, time out or
arrive concurrently**. No real money, telecom or bank systems are used.

## Stack

| Part | Technology |
|---|---|
| API / transaction service | Python + FastAPI |
| Database | PostgreSQL |
| Temporary state / control | Redis |
| Merchant dashboard | React + Vite |
| Testing | Pytest (unit/integration), Locust (load), GitHub Actions (CI) |

## Project layout

```
payreliant/
├── backend/          FastAPI app and its tests
│   ├── app/
│   ├── tests/
│   ├── experiments/  locks off/on race experiment
│   └── load_tests/   Locust load test + consistency checker
├── ussd-simulator/   USSD phone simulator (served by the API at /simulator/)
├── dashboard/        React + Vite merchant dashboard (http://localhost:5173)
├── docs/             Diagrams, test results, report notes
├── .github/workflows/  CI: runs the tests on every push
├── docker-compose.yml  PostgreSQL + Redis for local development
└── .env.example      Copy to .env
```

## Run it locally

```bash
# 1. Start PostgreSQL and Redis
docker compose up -d

# 2. Set up the Python environment (first time only)
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# 3. Create the tables and sample accounts (safe to re-run)
python -m app.seed

# 4. Run the API
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API docs.

Open http://localhost:8000/simulator/ for the **USSD simulator**: dial `*384#`, pay a merchant,
and switch the network condition (normal / sent twice / reply lost) to watch idempotency work.

## Run the merchant dashboard (React)

Needs Node.js (LTS). The API must be running too (step 4 above), so use a **second terminal**:

```bash
cd dashboard
npm install        # first time only
npm run dev
```

Open http://localhost:5173 and **sign in**. It refreshes every 3 seconds, so payments made in
the USSD simulator appear on their own.

## Logins and access (synthetic sandbox accounts)

| Who | Username | Password | Can see / do |
|---|---|---|---|
| Admin | `admin` | `Admin@2026` | Everything: all transactions, Accounts, Reliability Tests, Settings |
| Merchant | `mamamboga`, `kibanda`, `tukobooks` | `Merchant@2026` | Only their own transactions, wallet and stats |
| USSD gateway | API key `sk_sandbox_ussd_gateway` | — | Submit payments (`X-API-Key` header) |

There is no public sign-up: the admin onboards merchants on the **Accounts** page, as a real
payment provider would. Passwords are stored only as Argon2 hashes. Change all of these in `.env`
for anything beyond your own laptop.

## Run the tests

```bash
cd backend
pytest
```
Docker must be running. Tests use a separate `payreliant_test` database, so they never touch your sandbox data.

## Reliability Tests and Settings (dashboard, admin)

- **Reliability Tests**: four buttons, one per failure scenario (Table 4.6). Each fires
  `Maximum Requests per Test` real payments through the payment logic in parallel, then checks
  every shilling: one charge per key, wallets equal the ledger, no lost updates, nothing stuck.
  Click a result row to see each check.
- **Settings**: provider name and timeout/retries (used by the USSD simulator and the timeout test),
  session logging (one line per payment in the API terminal), and **failure injection**:
  make a percentage of real payments fail mid-way, or add latency, and watch them fail safely.

## Load test (Locust)

```bash
cd backend
python -m load_tests.check_consistency --top-up      # give demo customers plenty of money
locust -f load_tests/locustfile.py --host http://127.0.0.1:8000
# open http://localhost:8089 -> 50 users, spawn rate 10 -> Start
python -m load_tests.check_consistency               # afterwards: is the money still right?
```
Headless with CSV results: `locust -f load_tests/locustfile.py --host http://127.0.0.1:8000 --headless -u 50 -r 10 -t 60s --csv load_tests/results/peak`

## Concurrency experiment (Scenario 4)

```bash
cd backend
python -m experiments.race_demo                         # 50 payments, 3 rounds per mode
python -m experiments.race_demo --payments 100 --rounds 5
```
Runs the same burst of simultaneous payments with wallet locking OFF and then ON,
and prints a before/after table (lost updates, wallets vs ledger, time).

## Build progress

- [x] Step 1 — Project setup, health endpoint, first test
- [x] Step 2 — Database connection and models (customers, merchants, wallets)
- [x] Step 3 — Payment endpoint with atomic wallet + ledger updates
- [x] Step 4 — Transaction states (PENDING → PROCESSING → SUCCESSFUL / FAILED)
- [x] Step 5 — Idempotency (retries return the original result, never charge twice)
- [x] Step 6 — Concurrency control (row locks; before/after experiment in `backend/experiments/race_demo.py`)
- [x] Step 7 — USSD simulator (http://127.0.0.1:8000/simulator/)
- [x] Step 8 — Merchant dashboard: Dashboard, Transactions, Accounts
- [x] Step 9a — Authentication: admin/merchant logins, merchant data isolation, gateway API key
- [x] Step 9b — Settings + failure injection; Reliability Tests screen (4 scenarios)
- [x] Step 10 — Locust load test, consistency checker, GitHub Actions CI
