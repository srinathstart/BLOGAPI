# Post routes. prefix="/posts".

import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app import database
from app.deps import get_current_user
from app.schemas import PostCreate, PostOut, PostUpdate, PostPatch, UserOut

router = APIRouter(prefix="/posts", tags=["posts"])


# Create a post. PROTECTED. author_id is stamped from the token, not the body.
@router.post("", response_model=PostOut, status_code=201)
async def create_post(
    new_post: PostCreate,
    current_user: UserOut = Depends(get_current_user),
):
    created_at = datetime.now(timezone.utc)
    post_document = {
        "title": new_post.title,
        "content": new_post.content,
        "author_id": current_user.id,
        "created_at": created_at,
    }
    result = await database.db["posts"].insert_one(post_document)
    return PostOut(
        id=str(result.inserted_id),
        title=new_post.title,
        content=new_post.content,
        author_id=current_user.id,
        created_at=created_at,
    )


# List posts, one page at a time, with optional ?q= title search. PUBLIC.
@router.get("", response_model=list[PostOut])
async def list_posts(
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    q: str | None = Query(default=None),
):
    # Build ONE filter, feed it to both count_documents and find so the total
    # matches the (possibly searched) result. re.escape makes q a literal,
    # case-insensitive substring match on the title.
    query_filter = {}
    if q:
        query_filter = {"title": {"$regex": re.escape(q), "$options": "i"}}

    total = await database.db["posts"].count_documents(query_filter)
    response.headers["X-Total-Count"] = str(total)

    posts = []
    async for document in (
        database.db["posts"].find(query_filter).sort("created_at", -1).skip(skip).limit(limit)
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


# Read ONE post by id. PUBLIC.
@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: str):
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    document = await database.db["posts"].find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    return PostOut(
        id=str(document["_id"]),
        title=document["title"],
        content=document["content"],
        author_id=document["author_id"],
        created_at=document["created_at"],
    )


# Edit a post (full replace). PROTECTED + AUTHOR-ONLY.
@router.put("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: str,
    updated_post: PostUpdate,
    current_user: UserOut = Depends(get_current_user),
):
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    document = await database.db["posts"].find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    # Ownership check: author OR admin may edit; anyone else -> 403. That extra
    # "and not admin" clause IS the moderator power — an admin bypasses ownership.
    if document["author_id"] != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You can only edit your own posts.")

    await database.db["posts"].update_one(
        {"_id": object_id},
        {"$set": {"title": updated_post.title, "content": updated_post.content}},
    )
    return PostOut(
        id=str(document["_id"]),
        title=updated_post.title,
        content=updated_post.content,
        author_id=document["author_id"],
        created_at=document["created_at"],
    )


# Partially edit a post. PROTECTED + AUTHOR-ONLY.
@router.patch("/{post_id}", response_model=PostOut)
async def patch_post(
    post_id: str,
    changes: PostPatch,
    current_user: UserOut = Depends(get_current_user),
):
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    document = await database.db["posts"].find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    # Author OR admin may edit; anyone else -> 403 (admin bypasses ownership).
    if document["author_id"] != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You can only edit your own posts.")

    # Only the fields the client actually sent, dropping any explicit nulls.
    fields_to_update = {
        key: value
        for key, value in changes.model_dump(exclude_unset=True).items()
        if value is not None
    }
    if not fields_to_update:
        raise HTTPException(
            status_code=400,
            detail="Send at least one field (title or content) to update.",
        )

    await database.db["posts"].update_one({"_id": object_id}, {"$set": fields_to_update})

    # Merge old doc + changes to return fresh state without a second read.
    merged = {**document, **fields_to_update}
    return PostOut(
        id=str(merged["_id"]),
        title=merged["title"],
        content=merged["content"],
        author_id=merged["author_id"],
        created_at=merged["created_at"],
    )


# Delete a post. PROTECTED + AUTHOR-ONLY. 204 No Content on success.
@router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    current_user: UserOut = Depends(get_current_user),
):
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    document = await database.db["posts"].find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    # Author OR admin may delete; anyone else -> 403 (admin bypasses ownership).
    if document["author_id"] != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You can only delete your own posts.")

    await database.db["posts"].delete_one({"_id": object_id})
