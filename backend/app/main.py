"""PayReliant API — entry point.

Step 1: just prove the server runs. Later steps add the database,
wallets, transactions and idempotency.
"""

from fastapi import FastAPI

app = FastAPI(
    title="PayReliant API",
    description="USSD Mobile Payment Reliability Sandbox & API Gateway (simulated money only).",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    """Simple liveness check. Load tests and the dashboard will call this."""
    return {"status": "ok", "service": "payreliant-api"}
