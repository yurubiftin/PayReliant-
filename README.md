# PayReliant — USSD Mobile Payment Reliability Sandbox & API Gateway

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
| Testing | Pytest, Locust / k6 |

## Project layout

```
payreliant/
├── backend/          FastAPI app and its tests
│   ├── app/
│   └── tests/
├── dashboard/        React + Vite merchant dashboard (later)
├── docs/             Diagrams, test results, report notes
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

# 3. Run the API
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API docs.

## Run the tests

```bash
cd backend
pytest
```

## Build progress

- [x] Step 1 — Project setup, health endpoint, first test
- [ ] Step 2 — Database connection and models (customers, merchants, wallets)
- [ ] Step 3 — Payment endpoint with atomic wallet + ledger updates
- [ ] Step 4 — Transaction states
- [ ] Step 5 — Idempotency (duplicate prevention)
- [ ] Step 6 — Concurrency control
- [ ] Step 7 — USSD simulator
- [ ] Step 8 — Merchant dashboard
- [ ] Step 9 — Reliability and load tests
