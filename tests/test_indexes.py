# Verifies the startup lifespan actually creates the performance indexes.
# The `client` fixture runs the lifespan against the in-memory DB, so after it
# yields, that DB carries the indexes and we can read their metadata.

import asyncio

import app.main as main_module


def indexed_fields(info):
    # index_information() returns {index_name: {"key": [(field, direction)], ...}}.
    # We pull out the first field of each index so we can assert which fields are
    # indexed, ignoring index names/direction.
    return {spec["key"][0][0] for spec in info.values()}


def test_startup_creates_all_indexes(client):
    # `client` already ran the lifespan; main_module.db is the fake DB with the
    # indexes on it. index_information() is async, so run it to completion.
    users = asyncio.run(main_module.db["users"].index_information())
    posts = asyncio.run(main_module.db["posts"].index_information())
    comments = asyncio.run(main_module.db["comments"].index_information())

    # The original unique email index (Day 4) is still there.
    assert "email" in indexed_fields(users)

    # The three new performance indexes (Day 17).
    assert "author_id" in indexed_fields(posts)
    assert "created_at" in indexed_fields(posts)
    assert "post_id" in indexed_fields(comments)
