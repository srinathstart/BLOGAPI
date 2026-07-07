# Comment routes. These are NESTED under a post, so prefix="/posts" and the
# paths carry "/{post_id}/comments". Sharing the "/posts" prefix with the posts
# router is fine — FastAPI merges them; the deeper paths never collide with
# "/posts/{post_id}".

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app import database
from app.deps import get_current_user
from app.schemas import CommentCreate, CommentOut, CommentUpdate, UserOut

router = APIRouter(prefix="/posts", tags=["comments"])


# Add a comment to a post. PROTECTED (any logged-in user may comment).
@router.post("/{post_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(
    post_id: str,
    new_comment: CommentCreate,
    current_user: UserOut = Depends(get_current_user),
):
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    # The parent post must exist -> no orphan comments.
    post = await database.db["posts"].find_one({"_id": object_id})
    if post is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    # No ownership check: commenting on OTHERS' posts is the point.
    created_at = datetime.now(timezone.utc)
    comment_document = {
        "post_id": post_id,
        "content": new_comment.content,
        "author_id": current_user.id,
        "created_at": created_at,
    }
    result = await database.db["comments"].insert_one(comment_document)
    return CommentOut(
        id=str(result.inserted_id),
        post_id=post_id,
        content=new_comment.content,
        author_id=current_user.id,
        created_at=created_at,
    )


# List all comments on a post. PUBLIC. Oldest-first (conversation order).
@router.get("/{post_id}/comments", response_model=list[CommentOut])
async def list_comments(
    post_id: str,
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
):
    try:
        object_id = ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    post = await database.db["posts"].find_one({"_id": object_id})
    if post is None:
        raise HTTPException(status_code=404, detail="No post found with that id.")

    total = await database.db["comments"].count_documents({"post_id": post_id})
    response.headers["X-Total-Count"] = str(total)

    comments = []
    async for document in (
        database.db["comments"]
        .find({"post_id": post_id})
        .sort("created_at", 1)
        .skip(skip)
        .limit(limit)
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


# Edit a comment. PROTECTED + AUTHOR-ONLY.
@router.put("/{post_id}/comments/{comment_id}", response_model=CommentOut)
async def update_comment(
    post_id: str,
    comment_id: str,
    updated_comment: CommentUpdate,
    current_user: UserOut = Depends(get_current_user),
):
    try:
        ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    try:
        comment_object_id = ObjectId(comment_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid comment id.")

    # Look up by BOTH ids: the comment must belong to THIS post -> 404 otherwise.
    comment = await database.db["comments"].find_one(
        {"_id": comment_object_id, "post_id": post_id}
    )
    if comment is None:
        raise HTTPException(
            status_code=404, detail="No comment found on that post with that id."
        )

    # Ownership check: not yours -> 403.
    if comment["author_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own comments.")

    await database.db["comments"].update_one(
        {"_id": comment_object_id},
        {"$set": {"content": updated_comment.content}},
    )
    return CommentOut(
        id=str(comment["_id"]),
        post_id=comment["post_id"],
        content=updated_comment.content,
        author_id=comment["author_id"],
        created_at=comment["created_at"],
    )


# Delete a comment. PROTECTED + AUTHOR-ONLY. 204 No Content on success.
@router.delete("/{post_id}/comments/{comment_id}", status_code=204)
async def delete_comment(
    post_id: str,
    comment_id: str,
    current_user: UserOut = Depends(get_current_user),
):
    try:
        ObjectId(post_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid post id.")

    try:
        comment_object_id = ObjectId(comment_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="That is not a valid comment id.")

    comment = await database.db["comments"].find_one(
        {"_id": comment_object_id, "post_id": post_id}
    )
    if comment is None:
        raise HTTPException(
            status_code=404, detail="No comment found on that post with that id."
        )

    if comment["author_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own comments.")

    await database.db["comments"].delete_one({"_id": comment_object_id})
