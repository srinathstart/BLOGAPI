# The login route. An APIRouter is a mini-app: we define routes on it here and
# main.py attaches it with app.include_router(). No prefix, so the path stays
# exactly "/login".

from fastapi import APIRouter, HTTPException

from app import database
from app.schemas import LoginRequest, Token, AccessToken, RefreshRequest
from app.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)

router = APIRouter(tags=["auth"])


# Log in: check email + password, hand back a token PAIR on success.
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

    user_id = str(document["_id"])

    # A short-lived access token (used on every request) + a long-lived refresh
    # token (used only to mint new access tokens).
    access_token = create_access_token(user_id)
    refresh_token, jti, expires_at = create_refresh_token(user_id)

    # Add this refresh token's jti to the allowlist. We store the jti (an id),
    # NOT the token itself (a credential). Its presence here is what makes the
    # token usable; deleting it (logout) revokes the token.
    await database.db["refresh_tokens"].insert_one(
        {"jti": jti, "user_id": user_id, "expires_at": expires_at}
    )

    return Token(access_token=access_token, refresh_token=refresh_token)


# Exchange a valid refresh token for a fresh access token. This is how a client
# stays logged in past the 15-minute access-token expiry WITHOUT re-entering a
# password.
@router.post("/refresh", response_model=AccessToken)
async def refresh(body: RefreshRequest):
    # One vague 401 for every failure, same discipline as get_current_user.
    invalid = HTTPException(
        status_code=401,
        detail="Could not validate your refresh token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Checks signature + expiry + that it's really a REFRESH token.
    claims = decode_refresh_token(body.refresh_token)
    if claims is None:
        raise invalid

    # The final gate is REVOCATION: even a perfectly valid, unexpired JWT is
    # rejected if its jti is no longer in the allowlist (i.e. it was logged out).
    stored = await database.db["refresh_tokens"].find_one({"jti": claims["jti"]})
    if stored is None:
        raise invalid

    # All good -> a brand-new short-lived access token. We do NOT rotate the
    # refresh token; it stays valid until logout or its own 7-day expiry.
    access_token = create_access_token(claims["sub"])
    return AccessToken(access_token=access_token)


# Log out: REVOKE a refresh token by removing its jti from the allowlist. After
# this, /refresh with the same token returns 401 even though the JWT hasn't
# expired — revocation is the whole reason we keep a server-side record.
@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest):
    # Decode first so we only act on a genuine token of ours. If it's garbage we
    # simply do nothing — logout is idempotent, and we never reveal whether the
    # token was real. Either way the client ends up logged out -> 204.
    claims = decode_refresh_token(body.refresh_token)
    if claims is not None:
        await database.db["refresh_tokens"].delete_one({"jti": claims["jti"]})
