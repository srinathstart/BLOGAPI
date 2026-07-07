# User routes. prefix="/users" is prepended to every path below, so a path of
# "" is exactly "/users" and "/me" is "/users/me".

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pymongo.errors import DuplicateKeyError

from app import database
from app.deps import get_current_user
from app.schemas import UserCreate, UserOut, PostOut
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


# Create a new user.
@router.post("", response_model=UserOut, status_code=201)
async def create_user(new_user: UserCreate):
    hashed = hash_password(new_user.password)
    user_document = {
        "username": new_user.username,
        "email": new_user.email,
        "hashed_password": hashed,
    }
    # The unique email index makes this fail on a duplicate; catch it -> 400.
    try:
        result = await database.db["users"].insert_one(user_document)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="That email is already registered.")

    return UserOut(
        id=str(result.inserted_id),
        username=new_user.username,
        email=new_user.email,
    )


# List users, one page at a time.
@router.get("", response_model=list[UserOut])
async def list_users(
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
):
    total = await database.db["users"].count_documents({})
    response.headers["X-Total-Count"] = str(total)

    users = []
    async for document in database.db["users"].find().skip(skip).limit(limit):
        users.append(
            UserOut(
                id=str(document["_id"]),
                username=document["username"],
                email=document["email"],
            )
        )
    return users


# Who am I? PROTECTED. MUST be defined BEFORE "/{user_id}" so "me" isn't matched
# as a user id.
@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: UserOut = Depends(get_current_user)):
    return current_user


# Read ONE user by id.
@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str):
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid user id.")

    document = await database.db["users"].find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="No user found with that id.")

    return UserOut(
        id=str(document["_id"]),
        username=document["username"],
        email=document["email"],
    )


# List every post written by ONE user. PUBLIC.
@router.get("/{user_id}/posts", response_model=list[PostOut])
async def list_user_posts(
    user_id: str,
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
):
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid user id.")

    # The user must EXIST first -> 404 (rather than a silent empty list).
    user = await database.db["users"].find_one({"_id": object_id})
    if user is None:
        raise HTTPException(status_code=404, detail="No user found with that id.")

    # author_id was stored as the user's STRING id, so filter by the string.
    total = await database.db["posts"].count_documents({"author_id": user_id})
    response.headers["X-Total-Count"] = str(total)

    posts = []
    async for document in (
        database.db["posts"]
        .find({"author_id": user_id})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    ):
        posts.append(
            PostOut(
                id=str(document["_id"]),
                title=document["title"],
                content=document["content"],
                author_id=document["author_id"],
                created_at=document["created_at"],
            )
        )
    return posts
