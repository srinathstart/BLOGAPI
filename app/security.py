import bcrypt


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
