from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.config import JWT_SECRET, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


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
    claims = {
        "sub": user_id,
        "exp": expire,
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

    # "sub" is where we stored the user id when minting the token.
    # .get returns None if it's somehow missing, which the caller treats
    # as an invalid token.
    return claims.get("sub")
