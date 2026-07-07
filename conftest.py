# pytest automatically loads this file first and makes every fixture below
# available to ALL test files — they never import it. Because it sits in the
# project root, pytest also puts the root on the import path, so tests can do
# "from app.main import app".

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

# Import the database module (whose `db` attribute every router + the lifespan
# read at call time) and the app itself.
import app.database as database_module
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

    # THE SWAP. Every router and the lifespan read the DB as `database.db`
    # (resolved at call time), so patching this ONE attribute redirects the
    # whole app to the fake DB for the duration of ONE test. monkeypatch undoes
    # it automatically afterward.
    monkeypatch.setattr(database_module, "db", mock_db)

    # Using TestClient as a context manager (`with ...`) runs the app's startup
    # lifespan — which creates the unique index on users.email. That now runs
    # against the fake DB (no network), so the duplicate-email rule is enforced
    # in tests exactly like in production. `c` is a fake HTTP client that calls
    # the app in-process (no real server, no ports).
    with TestClient(main_module.app) as c:
        yield c
    # After the test, `with` tears the client down and monkeypatch restores the
    # real `db`. The in-memory database is simply discarded.
