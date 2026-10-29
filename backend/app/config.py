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

# Concurrency control (Step 6). "true" = lock wallet rows during a payment (correct).
# "false" = no locking: ONLY for the before/after experiment in experiments/race_demo.py.
LOCK_WALLETS = os.getenv("LOCK_WALLETS", "true").lower() == "true"

# A separate database used only by the automated tests,
# so running pytest never touches your real sandbox data.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://payreliant:payreliant_dev@localhost:5432/payreliant_test",
)
