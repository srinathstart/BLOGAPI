import os
from dotenv import load_dotenv

# Read the .env file and load its NAME=value pairs into the environment.
load_dotenv()

# Pull the values we need out of the environment.
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

# The secret used to SIGN login tokens. Anyone who knows this can forge
# tokens, so it lives in .env (a secret), never in code.
JWT_SECRET = os.getenv("JWT_SECRET")

# These are settings, not secrets, so they're fine to keep in code:
# - ALGORITHM: the signing method JWTs use. HS256 = sign with a shared secret.
# - ACCESS_TOKEN_EXPIRE_MINUTES: how long an ACCESS token stays valid. Kept
#   SHORT (15 min) on purpose: if one leaks, it dies fast. The user doesn't have
#   to log in again though — the client silently swaps the refresh token for a
#   new access token (see POST /refresh).
# - REFRESH_TOKEN_EXPIRE_DAYS: how long the LONG-lived refresh token lasts. This
#   is the "stay logged in for a week" token; it can be revoked early via logout.
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Fail loudly at startup if a secret is missing, instead of crashing
# later with a confusing error deep inside the code.
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing — check your .env file")
if not DB_NAME:
    raise RuntimeError("DB_NAME is missing — check your .env file")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is missing — check your .env file")
