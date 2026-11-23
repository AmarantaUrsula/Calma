import os

# Cheaper password hashing in tests only (the cost setting is stored in each hash, so login still works).
os.environ.setdefault("CALMA_SCRYPT_N", "1024")
os.environ.setdefault("CALMA_SCHEDULER", "0")

import pytest


@pytest.fixture(autouse=True)
def _reset_login_lockouts():
    """Login lockouts live in memory; don't let one test's failed logins lock accounts in the next."""
    from backend import auth
    auth._fails.clear()
    yield
    auth._fails.clear()
