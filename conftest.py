# pytest automatically loads this file first and makes every fixture below
# available to ALL test files — they never import it. Because it sits in the
# project root, pytest also puts the root on the import path, so tests can do
# "from app.main import app".

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

# Import the MODULE (not just `app`) so we can reach into it and swap out its
# `db` global for a fake one before any request runs.
import app.main as main_module


# A fixture named `client`. Any test that takes a `client` argument gets
# whatever this yields. Default scope is "function": pytest re-runs this for
# EACH test, so every test starts from a brand-new, empty database — perfect
# isolation, no test can leak data into another.
@pytest.fixture()
def client(monkeypatch):
    # AsyncMongoMockClient is an in-memory stand-in for Motor's real client:
    # same async API (find/insert_one/sort/skip/limit/count_documents/…), but
    # nothing touches the network or your real Atlas. [...] picks a database
    # name, just like the real code does.
    mock_db = AsyncMongoMockClient()["blogapi_test"]

    # THE SWAP. main.py does `from app.database import db` and then uses `db`
    # as a module global inside every route and the lifespan. monkeypatch
    # rebinds that global to our fake for the duration of ONE test, then undoes
    # it automatically afterward. So the app talks to the fake DB, unaware.
    monkeypatch.setattr(main_module, "db", mock_db)

    # Using TestClient as a context manager (`with ...`) runs the app's startup
    # lifespan — which creates the unique index on users.email. That now runs
    # against the fake DB (no network), so the duplicate-email rule is enforced
    # in tests exactly like in production. `c` is a fake HTTP client that calls
    # the app in-process (no real server, no ports).
    with TestClient(main_module.app) as c:
        yield c
    # After the test, `with` tears the client down and monkeypatch restores the
    # real `db`. The in-memory database is simply discarded.
