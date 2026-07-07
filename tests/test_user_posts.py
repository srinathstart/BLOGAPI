# Tests for GET /users/{id}/posts — list one user's posts (Day 11). This is the
# flip side of ownership: posts are stamped with author_id on create, and here
# we follow that link the other way to gather a given user's posts.


def register_and_login(client, email, username):
    # Register + login, returning (auth header, the user's id).
    client.post(
        "/users",
        json={"username": username, "email": email, "password": "supersecret"},
    )
    token = client.post(
        "/login", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/users/me", headers=headers).json()["id"]
    return headers, user_id


def test_lists_only_that_users_posts(client):
    alice, alice_id = register_and_login(client, "alice@example.com", "alice")
    bob, bob_id = register_and_login(client, "bob@example.com", "bob")

    # Alice writes two posts; Bob writes one.
    client.post("/posts", json={"title": "a1", "content": "x"}, headers=alice)
    client.post("/posts", json={"title": "a2", "content": "x"}, headers=alice)
    client.post("/posts", json={"title": "b1", "content": "x"}, headers=bob)

    # GET Alice's posts -> only her two, never Bob's.
    response = client.get(f"/users/{alice_id}/posts")
    assert response.status_code == 200
    posts = response.json()
    assert len(posts) == 2
    # Every returned post really belongs to Alice.
    assert all(p["author_id"] == alice_id for p in posts)
    # The total header uses the same author filter -> 2, not 3.
    assert response.headers["X-Total-Count"] == "2"


def test_existing_user_with_no_posts_returns_empty_list(client):
    # Carol exists but has written nothing.
    _, carol_id = register_and_login(client, "carol@example.com", "carol")

    response = client.get(f"/users/{carol_id}/posts")
    # 200 with an EMPTY list — the user exists, they just have no posts.
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Total-Count"] == "0"


def test_missing_or_malformed_user_id(client):
    # A valid-shaped ObjectId that matches no user -> 404 (the user is missing,
    # which is different from "exists but has no posts" above).
    missing = client.get(f"/users/{'0' * 24}/posts")
    assert missing.status_code == 404

    # A malformed id -> 400 before the lookup.
    malformed = client.get("/users/not-a-valid-id/posts")
    assert malformed.status_code == 400
