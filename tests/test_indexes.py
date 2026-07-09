# Verifies the startup lifespan actually creates the performance indexes.
# The `client` fixture runs the lifespan against the in-memory DB, so after it
# yields, that DB carries the indexes and we can read their metadata.

import asyncio

import app.database as database


def indexed_fields(info):
    # index_information() returns {index_name: {"key": [(field, direction)], ...}}.
    # We pull out the first field of each index so we can assert which fields are
    # indexed, ignoring index names/direction.
    return {spec["key"][0][0] for spec in info.values()}


def test_startup_creates_all_indexes(client):
    # `client` already ran the lifespan; database.db is the fake DB (patched by
    # the fixture) with the indexes on it. index_information() is async.
    users = asyncio.run(database.db["users"].index_information())
    posts = asyncio.run(database.db["posts"].index_information())
    comments = asyncio.run(database.db["comments"].index_information())
    refresh_tokens = asyncio.run(database.db["refresh_tokens"].index_information())

    # The original unique email index (Day 4) is still there.
    assert "email" in indexed_fields(users)

    # The three performance indexes (Day 17).
    assert "author_id" in indexed_fields(posts)
    assert "created_at" in indexed_fields(posts)
    assert "post_id" in indexed_fields(comments)

    # The refresh-token allowlist index (Day 19).
    assert "jti" in indexed_fields(refresh_tokens)
