from contextlib import asynccontextmanager
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pymongo.errors import DuplicateKeyError

from app.database import db
from app.schemas import (
    UserCreate,
    UserOut,
    LoginRequest,
    Token,
    PostCreate,
    PostOut,
    PostUpdate,
    CommentCreate,
    CommentOut,
)
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


# Code that runs ONCE when the server starts (and shuts down).
# We use it to make sure the database rules we depend on are in place
# before any request is ever handled.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create a UNIQUE index on the "email" field of the users collection.
    # - "email" is the field to index.
    # - unique=True is the rule: two users can never share an email.
    # create_index is safe to call every startup; if the index already
    # exists, MongoDB just leaves it as-is.
    await db["users"].create_index("email", unique=True)

    # Everything before "yield" runs at startup; everything after it runs
    # at shutdown. We have no cleanup to do yet, so there's nothing below.
    yield


# Hand the lifespan function to FastAPI so it knows to run it.
app = FastAPI(lifespan=lifespan)


# Tells FastAPI to look for an "Authorization: Bearer <token>" header.
# It also adds the "Authorize" button to the /docs page so you can paste
# a token there and test protected routes. If the header is missing,
# FastAPI rejects the request itself ("Not authenticated") before our
# code even runs.
bearer_scheme = HTTPBearer()


# A "dependency": a function FastAPI runs BEFORE a protected route. Any
# route that lists `Depends(get_current_user)` will only run if this
# returns successfully — otherwise the 401 below stops the request here.
# Returns the logged-in user, so the route gets it for free.
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UserOut:
    # We use the same 401 for every failure so we never hint WHY a token
    # was rejected. WWW-Authenticate is the standard header that names the
    # auth scheme on a 401.
    invalid = HTTPException(
        status_code=401,
        detail="Could not validate your login token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # credentials.credentials is just the token string after "Bearer ".
    # Verify it and pull out the user id (or None if it's bad/expired).
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise invalid

    # The id inside the token should be a valid ObjectId shape. If someone
    # somehow forged a token with junk in "sub", this guards against it.
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        raise invalid

    # The user could have been deleted after the token was issued, so we
    # always confirm they still exist.
    document = await db["users"].find_one({"_id": object_id})
    if document is None:
        raise invalid

    return UserOut(
        id=str(document["_id"]),
        username=document["username"],
        email=document["email"],
    )


@app.get("/")
def read_root():
    return {"message": "Blog API is alive!"}


# Create a new user.
# - response_model=UserOut tells FastAPI to send back the "safe" shape
#   (id, username, email) and to strip anything else, like the password.
# - status_code=201 is the standard HTTP code for "a resource was created".
@app.post("/users", response_model=UserOut, status_code=201)
async def create_user(new_user: UserCreate):
    # new_user is already validated by Pydantic (valid email, lengths, etc.)
    # before this function even runs.

    # Turn the plain password into a hash. The plain one is never stored.
    hashed = hash_password(new_user.password)

    # Build the document (a plain dict) that we'll save into MongoDB.
    # Note we save "hashed_password", NOT the original password.
    user_document = {
        "username": new_user.username,
        "email": new_user.email,
        "hashed_password": hashed,
    }

    # Insert the document into the "users" collection. MongoDB creates the
    # collection (and the database) automatically on this first write.
    # await is needed because Motor talks to the database asynchronously.
    #
    # The unique index on "email" means this insert will FAIL if the email
    # is already taken. Mongo raises DuplicateKeyError; we catch it and turn
    # it into a clean HTTP 400 instead of an ugly 500 crash.
    try:
        result = await db["users"].insert_one(user_document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400,
            detail="That email is already registered.",
        )

    # MongoDB gave the new document a unique _id. It's an ObjectId, so we
    # convert it to a string to send back to the client.
    return UserOut(
        id=str(result.inserted_id),
        username=new_user.username,
        email=new_user.email,
    )


# Read all users back out.
# response_model=list[UserOut] means: send a JSON list, and force every
# item through the safe UserOut shape (so no hashed_password leaks out).
@app.get("/users", response_model=list[UserOut])
async def list_users():
    # We'll collect the cleaned-up users here.
    users = []

    # db["users"].find() with no filter means "every document".
    # It returns a cursor; "async for" walks through the results one by one,
    # awaiting the database as needed.
    async for document in db["users"].find():
        # Each document has an ObjectId _id; convert it to a string id,
        # and pull only the safe fields into UserOut.
        users.append(
            UserOut(
                id=str(document["_id"]),
                username=document["username"],
                email=document["email"],
            )
        )

    return users


# Who am I? A PROTECTED route: it requires a valid token.
# Depends(get_current_user) runs our dependency first; if the token is bad
# the request never reaches this function. If it's good, FastAPI hands us
# the logged-in user as `current_user`, and we just return it.
#
# ROUTE ORDER MATTERS: this must come BEFORE "/users/{user_id}" below.
# FastAPI checks routes top to bottom. If "/users/{user_id}" came first,
# a request to "/users/me" would match it with user_id="me" and try to
# look up a user with that id. Specific paths go above wildcard ones.
@app.get("/users/me", response_model=UserOut)
async def read_current_user(current_user: UserOut = Depends(get_current_user)):
    return current_user


# Read ONE user by their id.
# {user_id} in the path is a "path parameter": FastAPI grabs that piece of
# the URL and hands it to us as the user_id argument (a string).
@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str):
    # The client sends the id as text, but Mongo stores _id as an ObjectId.
    # Convert the text back into an ObjectId so the query can match.
    # If the text isn't a valid ObjectId shape (e.g. "hello"), ObjectId()
    # raises InvalidId; we turn that into a clean HTTP 400.
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid user id.")

    # find_one returns the first matching document, or None if nothing matches.
    document = await db["users"].find_one({"_id": object_id})

    # A valid-looking id that simply doesn't exist -> 404 Not Found.
    if document is None:
        raise HTTPException(status_code=404, detail="No user found with that id.")

    # Shape the document into the safe UserOut (no hashed_password leaks out).
    return UserOut(
        id=str(document["_id"]),
        username=document["username"],
        email=document["email"],
    )


# Log in: check email + password, and hand back a signed token on success.
# response_model=Token shapes the reply into {access_token, token_type}.
@app.post("/login", response_model=Token)
async def login(credentials: LoginRequest):
    # Find the user with this email. find_one returns the document or None.
    document = await db["users"].find_one({"email": credentials.email})

    # SECURITY: we deliberately give the SAME error whether the email
    # doesn't exist OR the password is wrong. If we said "no such email"
    # vs "wrong password", an attacker could probe which emails are
    # registered. One vague 401 reveals nothing.
    #
    # Python's "or" short-circuits: if document is None we never call
    # verify_password (which would crash on a missing user).
    if document is None or not verify_password(
        credentials.password, document["hashed_password"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )

    # Good login. Mint a token whose "subject" is this user's id (as a
    # string). That id is how a later request will prove who it is.
    token = create_access_token(str(document["_id"]))

    # token_type defaults to "bearer" in the Token schema, so we only
    # need to pass the token string itself.
    return Token(access_token=token)


# Create a new blog post. PROTECTED: requires a valid login token.
# - Depends(get_current_user) runs first; no/invalid token -> 401 and this
#   function never runs. On success, FastAPI hands us the logged-in user.
# - new_post (the request body) carries ONLY title + content. The author is
#   NOT trusted from the client — we take it from current_user.id, which
#   came from the verified token. That's how a post becomes "owned".
@app.post("/posts", response_model=PostOut, status_code=201)
async def create_post(
    new_post: PostCreate,
    current_user: UserOut = Depends(get_current_user),
):
    # The exact moment the post is created, in UTC. We compute it once and
    # reuse the same value for both the DB write and the response, so they
    # can never disagree.
    created_at = datetime.now(timezone.utc)

    # Build the document we'll save. author_id is the STRING id of the
    # logged-in user — stamped by us, not the client.
    post_document = {
        "title": new_post.title,
        "content": new_post.content,
        "author_id": current_user.id,
        "created_at": created_at,
    }

    # Insert into the "posts" collection (Mongo creates it on first write).
    result = await db["posts"].insert_one(post_document)

    # Shape the reply. The new _id becomes our string id.
    return PostOut(
        id=str(result.inserted_id),
        title=new_post.title,
        content=new_post.content,
        author_id=current_user.id,
        created_at=created_at,
    )


# Read ALL posts. PUBLIC: no token needed — anyone can read the blog.
# response_model=list[PostOut] forces every item through the safe shape.
@app.get("/posts", response_model=list[PostOut])
async def list_posts():
    posts = []

    # find() with no filter = every post. The cursor is async, so we walk
    # it with "async for". .sort("created_at", -1) returns NEWEST first
    # (-1 = descending); that's why we stored created_at.
    async for document in db["posts"].find().sort("created_at", -1):
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


# Read ONE post by its id. PUBLIC.
# Same id round-trip + error pattern as GET /users/{user_id}:
# bad id shape -> 400, valid shape but no match -> 404.
@app.get("/posts/{post_id}", response_model=PostOut)
async def get_post(post_id: str):
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    document = await db["posts"].find_one({"_id": object_id})

    if document is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    return PostOut(
        id=str(document["_id"]),
        title=document["title"],
        content=document["content"],
        author_id=document["author_id"],
        created_at=document["created_at"],
    )


# Edit a post. PROTECTED + AUTHOR-ONLY.
# - Depends(get_current_user): no/invalid token -> 401, route skipped.
# - updated_post (the body) carries a fresh title + content that REPLACE
#   the old ones. author_id and created_at are never touched.
# This route shows the three different "no" answers in one place:
#   400 = the id is junk, 404 = no such post, 403 = it's not YOUR post.
@app.put("/posts/{post_id}", response_model=PostOut)
async def update_post(
    post_id: str,
    updated_post: PostUpdate,
    current_user: UserOut = Depends(get_current_user),
):
    # Same id round-trip as the read route: bad shape -> 400.
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    # The post must exist before we can talk about who owns it.
    document = await db["posts"].find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    # THE OWNERSHIP CHECK. The post's author_id was stamped from a token at
    # creation; current_user.id comes from THIS request's token. If they
    # differ, the caller is logged in but editing someone else's post -> 403.
    # 403 (Forbidden) is different from 401 (not logged in): here we DO know
    # who you are, you're just not allowed to touch this one.
    if document["author_id"] != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own posts.",
        )

    # Apply the change. $set updates ONLY these two fields and leaves the
    # rest of the document (author_id, created_at) exactly as it was.
    await db["posts"].update_one(
        {"_id": object_id},
        {"$set": {"title": updated_post.title, "content": updated_post.content}},
    )

    # Return the post as it now stands. The new title/content come from the
    # request; author_id and created_at come from the document we already
    # fetched (they didn't change).
    return PostOut(
        id=str(document["_id"]),
        title=updated_post.title,
        content=updated_post.content,
        author_id=document["author_id"],
        created_at=document["created_at"],
    )


# Delete a post. PROTECTED + AUTHOR-ONLY.
# Same guard rails as editing (400 junk id / 404 missing / 403 not yours),
# because the rule is identical: you can only remove your OWN post.
# - status_code=204 ("No Content") is the standard reply for a successful
#   delete: it means "done, and there's nothing to send back". So this
#   function returns nothing, and there's no response_model.
@app.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    current_user: UserOut = Depends(get_current_user),
):
    # id junk -> 400.
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    # Must exist before we can own-check it -> 404 if not.
    document = await db["posts"].find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    # The same ownership check as update: not yours -> 403.
    if document["author_id"] != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own posts.",
        )

    # Actually remove it. We already confirmed it exists and is ours.
    await db["posts"].delete_one({"_id": object_id})

    # No return: a 204 response has an empty body by definition.


# Add a comment to a post. PROTECTED (any logged-in user may comment).
# The URL is NESTED: /posts/{post_id}/comments reads as "the comments that
# belong to this post". The comment links to TWO things, neither from the
# body: post_id (from the URL) and author_id (from the token).
@app.post(
    "/posts/{post_id}/comments",
    response_model=CommentOut,
    status_code=201,
)
async def create_comment(
    post_id: str,
    new_comment: CommentCreate,
    current_user: UserOut = Depends(get_current_user),
):
    # Same id round-trip: a junk post id -> 400.
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    # The post must EXIST before we can attach a comment to it. Without this
    # check we'd happily store comments pointing at a post that isn't there
    # ("orphan" comments). Valid-shaped id but no such post -> 404.
    post = await db["posts"].find_one({"_id": object_id})
    if post is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    # Note: we do NOT do an ownership check here. Commenting is open to ANY
    # logged-in user — you comment on OTHER people's posts, that's the point.
    # (Editing/deleting a post stayed author-only; commenting is not.)

    created_at = datetime.now(timezone.utc)

    # Build the comment. post_id is the string from the URL (the link to the
    # parent post); author_id is the logged-in user; both stamped by us.
    comment_document = {
        "post_id": post_id,
        "content": new_comment.content,
        "author_id": current_user.id,
        "created_at": created_at,
    }

    # First write auto-creates the "comments" collection.
    result = await db["comments"].insert_one(comment_document)

    return CommentOut(
        id=str(result.inserted_id),
        post_id=post_id,
        content=new_comment.content,
        author_id=current_user.id,
        created_at=created_at,
    )


# List all comments on a post. PUBLIC: anyone can read the discussion.
@app.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def list_comments(post_id: str):
    # Junk post id -> 400.
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    # Same as creating: the post must exist. Asking for the comments of a
    # post that isn't there -> 404 (rather than a silent empty list, which
    # would hide the fact that the post itself is missing).
    post = await db["posts"].find_one({"_id": object_id})
    if post is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    comments = []

    # THE RELATIONSHIP QUERY: find only the comments whose post_id matches
    # THIS post. The filter {"post_id": post_id} is how we "follow the link"
    # from a post to its comments. .sort("created_at", 1) = OLDEST first, so
    # the discussion reads top-to-bottom like a conversation (the opposite of
    # posts, which we showed newest-first).
    async for document in db["comments"].find({"post_id": post_id}).sort(
        "created_at", 1
    ):
        comments.append(
            CommentOut(
                id=str(document["_id"]),
                post_id=document["post_id"],
                content=document["content"],
                author_id=document["author_id"],
                created_at=document["created_at"],
            )
        )

    return comments
