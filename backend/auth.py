"""Staff accounts: password hashing, password rules, and login rate limiting.

Patients never have accounts; they use the private link from their clinic.

How passwords are protected:
  * Never stored or logged as text. Only a salted scrypt hash is kept in the users table:
    a slow, memory-hard one-way function, so even a full copy of the database can't be turned
    back into passwords, and guessing at scale is very expensive.
  * A unique random salt per password, so identical passwords look different.
  * Optional pepper (CALMA_PASSWORD_PEPPER) kept outside the database.
  * The hash never leaves the server: no API response, log, audit entry or AI call includes it.
  * Login failures give one generic message (the form never reveals whether an email has an
    account), take the same time either way, and lock an email for 15 minutes after 5 misses.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from . import clock

# scrypt cost settings (about 16 MB of memory per hash, a few tens of milliseconds).
# The settings are saved inside every hash string ("scrypt$N$r$p$salt$hash"), so login always
# re-hashes with exactly the settings and salt that were used at sign-up.
# Tests may lower N with CALMA_SCRYPT_N to run faster; production uses the default.
_N, _R, _P = int(os.environ.get("CALMA_SCRYPT_N", 2**14)), 8, 1
MIN_PASSWORD = 10
COMMON = {"password12", "password123", "1234567890", "qwertyuiop", "calmacalma", "letmein123", "iloveyou12"}


def _peppered(password: str) -> bytes:
    """Optional server secret ("pepper") kept OUTSIDE the database (an environment variable).
    With it set, a stolen copy of the database isn't enough to even start guessing passwords.
    Changing or losing it invalidates every password, so set it once and keep it."""
    pepper = os.environ.get("CALMA_PASSWORD_PEPPER", "")
    if not pepper:
        return password.encode()
    return hmac.new(pepper.encode(), password.encode(), hashlib.sha256).digest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(_peppered(password), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        test = hashlib.scrypt(_peppered(password), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                              dklen=len(base64.b64decode(digest)))
        return hmac.compare_digest(test, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


# A real hash to compare against when the email doesn't exist, so timing doesn't reveal it.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def check_login(password: str, stored: str | None) -> bool:
    return verify_password(password, stored or _DUMMY_HASH) and stored is not None


def password_problem(password: str, email: str, first: str, last: str) -> str | None:
    """Return a plain-English problem with the password, or None if it's OK."""
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if len(password) > 200:
        return "Password is too long."
    low = password.lower()
    if low in COMMON or len(set(low)) < 4:
        return "That password is too easy to guess. Try a short phrase of a few words."
    for part in (email.split("@")[0], first, last):
        if part and len(part) >= 3 and part.lower() in low:
            return "Password shouldn't contain your name or email."
    return None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


# ---------- login rate limiting (per email, in memory) ----------

MAX_FAILS = 5
LOCK_WINDOW = timedelta(minutes=15)
_fails: dict[str, list[datetime]] = {}


def locked_out(email: str) -> bool:
    recent = [t for t in _fails.get(email, []) if clock.now() - t < LOCK_WINDOW]
    _fails[email] = recent
    return len(recent) >= MAX_FAILS


def record_failure(email: str) -> None:
    _fails.setdefault(email, []).append(clock.now())


def clear_failures(email: str) -> None:
    _fails.pop(email, None)
