# The login route. An APIRouter is a mini-app: we define routes on it here and
# main.py attaches it with app.include_router(). No prefix, so the path stays
# exactly "/login".

from fastapi import APIRouter, HTTPException

from app import database
from app.schemas import LoginRequest, Token
from app.security import verify_password, create_access_token

router = APIRouter(tags=["auth"])


# Log in: check email + password, hand back a signed token on success.
@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest):
    document = await database.db["users"].find_one({"email": credentials.email})

    # SECURITY: identical 401 whether the email is unknown OR the password is
    # wrong, so an attacker can't probe which emails exist. "or" short-circuits
    # so we never call verify_password on a missing user.
    if document is None or not verify_password(
        credentials.password, document["hashed_password"]
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    # Mint a token whose subject is this user's id (as a string).
    token = create_access_token(str(document["_id"]))
    return Token(access_token=token)
