"""Settings for the app, read from the .env file (or defaults for local development)."""

import os

from dotenv import load_dotenv

# Looks for a .env file in this folder or any parent folder and loads it.
load_dotenv()

# Where the database lives. The default matches docker-compose.yml,
# so it works out of the box even if you never create a .env file.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://payreliant:payreliant_dev@localhost:5432/payreliant",
)

# --- Security (authentication) ----------------------------------------------------
# Secret used to sign login tokens. MUST be changed via .env for anything beyond local testing.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-secret-change-me-in-env-file")
TOKEN_MINUTES = int(os.getenv("TOKEN_MINUTES", "480"))  # a login lasts 8 hours

# The key a USSD gateway (here: the simulator) must send to submit payments.
GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY", "sk_sandbox_ussd_gateway")

# Passwords for the sandbox's seeded logins (synthetic accounts only).
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@2026")
DEMO_MERCHANT_PASSWORD = os.getenv("DEMO_MERCHANT_PASSWORD", "Merchant@2026")

# Concurrency control (Step 6). "true" = lock wallet rows during a payment (correct).
# "false" = no locking: ONLY for the before/after experiment in experiments/race_demo.py.
LOCK_WALLETS = os.getenv("LOCK_WALLETS", "true").lower() == "true"

# A separate database used only by the automated tests,
# so running pytest never touches your real sandbox data.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://payreliant:payreliant_dev@localhost:5432/payreliant_test",
)
