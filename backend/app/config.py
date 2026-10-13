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

# A separate database used only by the automated tests,
# so running pytest never touches your real sandbox data.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://payreliant:payreliant_dev@localhost:5432/payreliant_test",
)
