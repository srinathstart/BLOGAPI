# Shared dependencies used across routers. Kept in its own module so that any
# router can import get_current_user without importing main.py (which would
# create a circular import: main imports the routers).

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import the database MODULE (not the `db` object) so that `database.db` is
# resolved at call time — this is what lets tests swap in a fake DB by patching
# app.database.db in one place.
from app import database
from app.schemas import UserOut
from app.security import decode_access_token


# Tells FastAPI to look for an "Authorization: Bearer <token>" header, and adds
# the Authorize button to /docs. Missing header -> FastAPI rejects it itself.
bearer_scheme = HTTPBearer()


# The dependency every protected route lists via Depends(get_current_user).
# Validates the token and returns the logged-in user, or raises one vague 401.
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UserOut:
    # Same vague 401 for every failure, so we never hint WHY a token was rejected.
    invalid = HTTPException(
        status_code=401,
        detail="Could not validate your login token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # credentials.credentials is the token string after "Bearer ".
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise invalid

    # The id inside the token should be a valid ObjectId shape.
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        raise invalid

    # The user could have been deleted after the token was issued.
    document = await database.db["users"].find_one({"_id": object_id})
    if document is None:
        raise invalid

    return UserOut(
        id=str(document["_id"]),
        username=document["username"],
        email=document["email"],
        # Read the stored role, defaulting to "user" for pre-roles documents.
        # This is the value the admin-bypass check downstream relies on.
        role=document.get("role", "user"),
    )
