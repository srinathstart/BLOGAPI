from motor.motor_asyncio import AsyncIOMotorClient

from app.config import MONGO_URI, DB_NAME

# Open a connection to the MongoDB Atlas cluster using our secret URI.
client = AsyncIOMotorClient(MONGO_URI)

# Pick the specific database inside the cluster that we'll work with.
db = client[DB_NAME]
