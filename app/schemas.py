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
