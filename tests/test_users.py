# Tests for the user routes. pytest auto-discovers this file (name starts with
# "test_") and every function named test_* inside it. Each test takes `client`,
# the fixture from conftest.py, so it runs against a FRESH in-memory database.


def test_root_health(client):
    # The simplest possible test: GET / should return 200 and the alive message.
    # If this passes, the app boots and the whole test wiring (fake DB swap +
    # TestClient) works end to end — the foundation for every test after it.
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Blog API is alive!"}


def test_create_user_returns_safe_shape(client):
    # POST a valid new user. json=... sends it as a JSON request body, exactly
    # like a real client would.
    response = client.post(
        "/users",
        json={"username": "alice", "email": "alice@example.com", "password": "supersecret"},
    )
    # 201 Created is the success code the route declares for a new resource.
    assert response.status_code == 201

    body = response.json()
    # The response must carry the safe fields back...
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert "id" in body  # Mongo assigned an _id, returned to us as a string

    # ...and must NEVER leak the password in any form. response_model=UserOut is
    # what enforces this; the test guarantees it can't silently regress later.
    assert "password" not in body
    assert "hashed_password" not in body


def test_list_users_and_total_count_header(client):
    # Fresh DB (the fixture gives each test its own): no users yet, so the list
    # is empty and the Day-14 header reports 0.
    empty = client.get("/users")
    assert empty.status_code == 200
    assert empty.json() == []
    # Headers are always strings, so we compare against "0", not 0.
    assert empty.headers["X-Total-Count"] == "0"

    # Create one user, then it should show up and the header should say 1.
    client.post(
        "/users",
        json={"username": "alice", "email": "alice@example.com", "password": "supersecret"},
    )
    listed = client.get("/users")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.headers["X-Total-Count"] == "1"


def test_duplicate_email_is_rejected(client):
    user = {"username": "alice", "email": "alice@example.com", "password": "supersecret"}

    # First create succeeds.
    first = client.post("/users", json=user)
    assert first.status_code == 201

    # Same email again -> the UNIQUE index on users.email makes Mongo raise
    # DuplicateKeyError, which the route catches and turns into a clean 400.
    # If the index hadn't been built (lifespan not run), this would wrongly
    # succeed with a 201 — so this test guards that whole mechanism.
    second = client.post("/users", json=user)
    assert second.status_code == 400


def test_invalid_user_is_rejected_with_422(client):
    # A malformed email -> Pydantic's EmailStr rejects it with 422 BEFORE the
    # route body runs (nothing is written to the DB).
    bad_email = client.post(
        "/users",
        json={"username": "alice", "email": "not-an-email", "password": "supersecret"},
    )
    assert bad_email.status_code == 422

    # A too-short password (schema says min_length=8) -> also 422.
    short_pw = client.post(
        "/users",
        json={"username": "bob", "email": "bob@example.com", "password": "x"},
    )
    assert short_pw.status_code == 422


def test_get_single_user(client):
    # Create a user and grab the id from the response.
    user_id = client.post(
        "/users",
        json={"username": "alice", "email": "alice@example.com", "password": "supersecret"},
    ).json()["id"]

    # Real id -> 200, correct user, and still no password leak.
    ok = client.get(f"/users/{user_id}")
    assert ok.status_code == 200
    assert ok.json()["email"] == "alice@example.com"
    assert "hashed_password" not in ok.json()

    # Malformed id -> 400.
    assert client.get("/users/not-a-valid-id").status_code == 400

    # Valid-shaped but missing -> 404.
    assert client.get(f"/users/{'0' * 24}").status_code == 404
