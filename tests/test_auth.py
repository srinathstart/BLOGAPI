# Tests for the login + token flow. Uses the same `client` fixture from
# conftest.py, so each test runs against a fresh in-memory database.


# You must exist before you can log in, so most tests here first register a
# user. This helper does that and returns the credentials for reuse.
def register(client, email="alice@example.com", password="supersecret"):
    client.post(
        "/users",
        json={"username": "alice", "email": email, "password": password},
    )
    return {"email": email, "password": password}


def test_login_returns_a_token(client):
    creds = register(client)

    # POST the right email + password to /login.
    response = client.post("/login", json=creds)
    assert response.status_code == 200

    body = response.json()
    # The reply is the Token shape: a non-empty access_token string, and
    # token_type defaulting to "bearer" (how the client sends it back later).
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert len(body["access_token"]) > 0


def test_wrong_password_is_rejected_401(client):
    register(client)  # real user exists

    # Right email, WRONG password -> 401.
    response = client.post(
        "/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_unknown_email_is_rejected_401(client):
    # No user registered at all. Logging in with an email that doesn't exist
    # must return the SAME 401 (and, we check, the same detail message) as a
    # wrong password — so the API never reveals which emails are registered.
    response = client.post(
        "/login",
        json={"email": "ghost@example.com", "password": "supersecret"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


def test_users_me_with_valid_token(client):
    creds = register(client)

    # Log in and pull the token out of the response.
    token = client.post("/login", json=creds).json()["access_token"]

    # Send it exactly how a real client does: "Authorization: Bearer <token>".
    # get_current_user decodes it, looks the user up, and hands them to the route.
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    # /users/me returns the user the token belongs to.
    assert response.json()["email"] == "alice@example.com"


def test_users_me_without_token_is_401(client):
    # No Authorization header at all. HTTPBearer rejects it with 401 before our
    # get_current_user even runs. (Older FastAPI returned 403 here; this version
    # returns 401 — verified against the installed source.)
    response = client.get("/users/me")
    assert response.status_code == 401


def test_users_me_with_garbage_token_is_401(client):
    # A header IS present with the bearer scheme, so HTTPBearer lets it through —
    # but the token is nonsense, so decode_access_token fails and OUR
    # get_current_user raises its own 401 with the vague detail.
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate your login token."
