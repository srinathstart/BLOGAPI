# Tests for the refresh-token flow (Day 19): login hands back an access + refresh
# PAIR, /refresh swaps a valid refresh token for a fresh access token, the wrong
# token TYPE is rejected, and /logout REVOKES a refresh token (the whole point of
# keeping a server-side jti allowlist). Same `client` fixture -> fresh DB per test.


def register_and_login(client, email="alice@example.com", password="supersecret"):
    # Register, then log in, returning the FULL login body (both tokens).
    client.post(
        "/users",
        json={"username": "alice", "email": email, "password": password},
    )
    return client.post("/login", json={"email": email, "password": password}).json()


def test_login_returns_a_token_pair(client):
    body = register_and_login(client)

    # Both tokens are present, non-empty strings; token_type still "bearer".
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 0
    assert isinstance(body["refresh_token"], str) and len(body["refresh_token"]) > 0
    # The two are genuinely different tokens, not the same string echoed twice.
    assert body["access_token"] != body["refresh_token"]


def test_refresh_issues_a_working_access_token(client):
    tokens = register_and_login(client)

    # Swap the refresh token for a fresh access token.
    refreshed = client.post(
        "/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_access = refreshed.json()["access_token"]
    assert isinstance(new_access, str) and len(new_access) > 0

    # And it REALLY works: use it on a protected route -> 200, right user.
    me = client.get("/users/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_refresh_rejects_an_access_token(client):
    # An ACCESS token posted to /refresh must be rejected: decode_refresh_token
    # checks type == "refresh", so a type-"access" token -> 401. This stops the
    # two token kinds from being used interchangeably.
    tokens = register_and_login(client)
    wrong = client.post(
        "/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert wrong.status_code == 401


def test_refresh_rejects_garbage(client):
    # A nonsense string fails the signature check -> 401.
    bad = client.post("/refresh", json={"refresh_token": "not-a-real-token"})
    assert bad.status_code == 401


def test_logout_revokes_the_refresh_token(client):
    tokens = register_and_login(client)
    refresh_token = tokens["refresh_token"]

    # It works before logout.
    assert (
        client.post("/refresh", json={"refresh_token": refresh_token}).status_code
        == 200
    )

    # Log out -> 204 No Content. This deletes the jti from the allowlist.
    assert (
        client.post("/logout", json={"refresh_token": refresh_token}).status_code
        == 204
    )

    # Now the SAME (still unexpired, still validly-signed) refresh token is dead:
    # its jti is gone from the allowlist -> 401. That's revocation working.
    assert (
        client.post("/refresh", json={"refresh_token": refresh_token}).status_code
        == 401
    )


def test_logout_is_idempotent_and_quiet(client):
    # Logging out a garbage token is a harmless no-op: still 204, never an error
    # and never a hint about whether the token was real.
    assert (
        client.post("/logout", json={"refresh_token": "not-a-real-token"}).status_code
        == 204
    )

    # Logging the SAME real token out twice is also fine (already gone -> no-op).
    tokens = register_and_login(client)
    rt = tokens["refresh_token"]
    assert client.post("/logout", json={"refresh_token": rt}).status_code == 204
    assert client.post("/logout", json={"refresh_token": rt}).status_code == 204
