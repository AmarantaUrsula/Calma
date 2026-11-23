import os

# Cheaper password hashing in tests only (the cost setting is stored in each hash, so login still works).
os.environ.setdefault("CALMA_SCRYPT_N", "1024")
os.environ.setdefault("CALMA_SCHEDULER", "0")
