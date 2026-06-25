from fastapi import FastAPI

from app.database import db
from app.schemas import UserCreate, UserOut
from app.security import hash_password

app = FastAPI()


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
    result = await db["users"].insert_one(user_document)

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
