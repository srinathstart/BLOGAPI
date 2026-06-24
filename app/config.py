import os
from dotenv import load_dotenv

# Read the .env file and load its NAME=value pairs into the environment.
load_dotenv()

# Pull the two values we need out of the environment.
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

# Fail loudly at startup if a secret is missing, instead of crashing
# later with a confusing error deep inside the database code.
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing — check your .env file")
if not DB_NAME:
    raise RuntimeError("DB_NAME is missing — check your .env file")
