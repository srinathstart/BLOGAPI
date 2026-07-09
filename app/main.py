from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the database MODULE so the lifespan reads `database.db` at call time —
# the same seam the routers use, so tests can swap in a fake DB by patching
# app.database.db in one place.
from app import database
from app.routers import auth, users, posts, comments


# Runs once at startup (before "yield") and shutdown (after). We use it to make
# sure the indexes we depend on exist before any request is handled.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Unique constraint: no two users can share an email.
    await database.db["users"].create_index("email", unique=True)

    # Performance indexes (non-unique) so these queries use index lookups
    # instead of collection scans:
    #   posts.author_id  -> GET /users/{id}/posts
    #   comments.post_id -> GET /posts/{id}/comments
    #   posts.created_at -> the newest-first sort on GET /posts
    await database.db["posts"].create_index("author_id")
    await database.db["comments"].create_index("post_id")
    await database.db["posts"].create_index("created_at")

    # The refresh-token allowlist. Each stored row is one still-valid refresh
    # token, keyed by its jti. UNIQUE so the same jti can never be stored twice,
    # and so /refresh's find_one({"jti": ...}) is an index lookup, not a scan.
    await database.db["refresh_tokens"].create_index("jti", unique=True)

    yield


app = FastAPI(lifespan=lifespan)


# CORS: let a browser frontend on another origin call this API and READ the
# custom X-Total-Count header (browser-only rule; curl/same-origin skip it).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


@app.get("/")
def read_root():
    return {"message": "Blog API is alive!"}


# Attach each router. Every route it defines is added to the app under the
# router's own prefix (/login, /users*, /posts*, /posts/{id}/comments*).
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)
