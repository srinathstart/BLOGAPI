import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.config import (
    JWT_SECRET,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


# Turn a plain-text password into a safe, irreversible hash for storage.
# We NEVER store the password itself — only this hash.
def hash_password(plain_password: str) -> str:
    # bcrypt works on raw bytes, so encode the string to UTF-8 bytes first.
    password_bytes = plain_password.encode("utf-8")

    # A "salt" is random data mixed into the hash so that two identical
    # passwords produce different hashes. gensalt() makes a fresh one each time.
    salt = bcrypt.gensalt()

    # Hash the password with the salt. The salt is stored INSIDE the result,
    # so we don't need to save it separately.
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)

    # Decode the hash bytes back to a string so it's easy to store in MongoDB.
    return hashed_bytes.decode("utf-8")


# Check a plain password (typed at login) against the stored hash.
# Returns True if they match, False if not.
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# Build a signed login token (a JWT) that says "this user is logged in,
# until this expiry time". We hand this to the client after a good login.
def create_access_token(user_id: str) -> str:
    # Work out the exact moment the token should stop being valid:
    # right now (in UTC) plus the minutes from our config.
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    # The "claims" = the facts we pack inside the token.
    # - "sub" (subject): WHO the token is about. We store the user id.
    # - "exp" (expiry): WHEN it dies. jose reads this automatically later
    #   and rejects the token once this time has passed.
    # - "type": WHAT KIND of token this is. We now mint two kinds (access +
    #   refresh); labelling each lets decode_* reject the wrong kind, so a
    #   refresh token can never be replayed at a protected route.
    claims = {
        "sub": user_id,
        "exp": expire,
        "type": "access",
    }

    # Pack the claims and SIGN them with our secret. The result is one long
    # string. Because it's signed, nobody can change the claims without us
    # noticing — but note the claims are READABLE (not encrypted), so we
    # never put anything sensitive (like a password) inside.
    token = jwt.encode(claims, JWT_SECRET, algorithm=ALGORITHM)
    return token


# The reverse of create_access_token: take a token string, check it's
# genuine and not expired, and return the user id stored inside it.
# Returns None if the token is missing/forged/expired/garbage.
def decode_access_token(token: str) -> str | None:
    try:
        # jwt.decode does three jobs at once:
        #   1. checks the signature with our secret (proves WE issued it),
        #   2. checks the "exp" claim (rejects expired tokens),
        #   3. unpacks the claims back into a dict.
        # If ANY of that fails, jose raises a JWTError.
        claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None

    # Reject anything that isn't specifically an ACCESS token. Without this a
    # long-lived refresh token could be handed straight to a protected route.
    if claims.get("type") != "access":
        return None

    # "sub" is where we stored the user id when minting the token.
    # .get returns None if it's somehow missing, which the caller treats
    # as an invalid token.
    return claims.get("sub")


# Build a signed REFRESH token — the long-lived "stay logged in" token. Unlike
# the access token, we also stamp a "jti" (a unique id for THIS token). We hand
# the jti back to the caller so it can be stored server-side: that stored row is
# the switch that lets us REVOKE the token later (logout). A stateless JWT alone
# can't be un-issued; the jti + a DB record is exactly what buys us revocation.
def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # jti = "JWT ID": a fresh random id, unique per token. uuid4() is random
    # (not sequential), so one jti tells you nothing about any other.
    jti = str(uuid.uuid4())

    claims = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
        "jti": jti,
    }
    token = jwt.encode(claims, JWT_SECRET, algorithm=ALGORITHM)

    # Return all three: the token to hand the client, the jti to STORE (so we can
    # revoke it), and the expiry so the stored row can carry its own deadline.
    return token, jti, expire


# The reverse of create_refresh_token. Checks signature + expiry + that it really
# IS a refresh token, then returns the whole claims dict (the caller needs BOTH
# "sub" to mint a new access token AND "jti" to check it hasn't been revoked).
# Returns None on any problem.
def decode_refresh_token(token: str) -> dict | None:
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None

    # Must be a refresh token — not an access token replayed at /refresh.
    if claims.get("type") != "refresh":
        return None

    # Both fields are required to do anything useful; missing either = malformed.
    if "sub" not in claims or "jti" not in claims:
        return None

    return claims
