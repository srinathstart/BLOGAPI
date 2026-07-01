from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# What the CLIENT sends us when creating a user (the "input" shape).
# Anything here is data we receive and must validate before trusting it.
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(min_length=8)


# What WE send back to the client (the "output" shape).
# Notice: there is NO password field here. We never return passwords,
# not even the hashed version.
class UserOut(BaseModel):
    id: str
    username: str
    email: EmailStr


# What the client sends to log in (the "input" shape for /login).
# Just the two things needed to prove who they are.
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# What WE send back after a successful login (the "output" shape).
# - access_token: the signed JWT string the client will store and reuse.
# - token_type: "bearer" is the standard label that tells the client how
#   to send it back later: in a header "Authorization: Bearer <token>".
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# What the CLIENT sends us to create a post (the "input" shape).
# Notice: there is NO author_id here. We do NOT let the client say who
# wrote the post — if we did, anyone could post as anyone else. The author
# is taken from the login token instead (see POST /posts in main.py).
class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


# What WE send back to the client (the "output" shape).
# - author_id: the id of the user who created it (filled in from the token).
# - created_at: when it was written, in UTC. Useful later for sorting
#   posts newest-first.
class PostOut(BaseModel):
    id: str
    title: str
    content: str
    author_id: str
    created_at: datetime


# What the CLIENT sends us to EDIT an existing post (the "input" shape).
# Same fields and rules as creating: a fresh title + content that REPLACE
# the old ones. Like PostCreate, there is NO author_id (the author never
# changes and is never client-controlled) and NO id (that's in the URL).
# It's a separate class from PostCreate so the two can diverge later.
class PostUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


# What the CLIENT sends us to PARTIALLY edit a post (the "input" shape).
# The contrast with PostUpdate (PUT) IS the whole lesson:
#   - PUT replaces the WHOLE post, so title AND content are both required.
#   - PATCH changes only the fields you name, so BOTH are now OPTIONAL.
# "str | None = None" is what makes a field optional: the "= None" default
# means "if the client leaves this out, fill in None". We'll later treat a
# left-out field as "don't touch it".
# The Field rules (min/max length) still apply, but ONLY when a real value is
# given — a missing field is None, so validation is skipped for it. That's
# why we can't accidentally save an empty title: if it's present, it must be
# 1..200 chars; if it's absent, it isn't changed at all.
class PostPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)


# What the CLIENT sends us to add a comment (the "input" shape).
# Only the comment text. NOT post_id (that comes from the URL) and NOT
# author_id (that comes from the login token) — the client never chooses
# which post a comment lands on or who wrote it.
class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


# What WE send back (the "output" shape).
# - post_id: which post this comment belongs to (the "relationship" link).
# - author_id: which user wrote it (filled from the token).
# - created_at: when, in UTC (used to sort comments oldest-first).
class CommentOut(BaseModel):
    id: str
    post_id: str
    content: str
    author_id: str
    created_at: datetime
