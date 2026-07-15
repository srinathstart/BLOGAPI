# Tests for role-based access (Day 20): a new user defaults to role "user"; an
# "admin" can moderate ANYONE's post/comment (bypassing the author-only 403);
# a normal user still cannot. Same `client` fixture -> fresh in-memory DB.

import asyncio

import app.database as database


def auth_headers(client, email, username):
    client.post(
        "/users",
        json={"username": username, "email": email, "password": "supersecret"},
    )
    token = client.post(
        "/login", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_admin(email):
    # Mirror the real manual step: flip the stored role directly in the DB. No
    # in-app route does this on purpose. get_current_user re-reads the user on
    # every request, so the change takes effect immediately — no re-login needed.
    asyncio.run(
        database.db["users"].update_one({"email": email}, {"$set": {"role": "admin"}})
    )


def test_new_user_defaults_to_role_user(client):
    headers = auth_headers(client, "alice@example.com", "alice")
    me = client.get("/users/me", headers=headers).json()
    # Registration stamps role "user"; nobody is an admin by signing up.
    assert me["role"] == "user"


def test_admin_can_moderate_any_post(client):
    author = auth_headers(client, "alice@example.com", "alice")
    admin = auth_headers(client, "mod@example.com", "mod")
    make_admin("mod@example.com")

    # Alice (a normal user) writes a post.
    post_id = client.post(
        "/posts", json={"title": "orig", "content": "orig body"}, headers=author
    ).json()["id"]

    # The admin, who is NOT the author, may edit it (PUT) -> 200.
    put = client.put(
        f"/posts/{post_id}",
        json={"title": "moderated", "content": "moderated body"},
        headers=admin,
    )
    assert put.status_code == 200
    assert put.json()["title"] == "moderated"
    # author_id is unchanged — moderating doesn't steal authorship.
    author_id = client.get("/users/me", headers=author).json()["id"]
    assert put.json()["author_id"] == author_id

    # ...PATCH it -> 200...
    patch = client.patch(
        f"/posts/{post_id}", json={"title": "patched by mod"}, headers=admin
    )
    assert patch.status_code == 200
    assert patch.json()["title"] == "patched by mod"

    # ...and DELETE it -> 204. Then it's really gone.
    assert client.delete(f"/posts/{post_id}", headers=admin).status_code == 204
    assert client.get(f"/posts/{post_id}").status_code == 404


def test_admin_can_moderate_any_comment(client):
    author = auth_headers(client, "alice@example.com", "alice")
    admin = auth_headers(client, "mod@example.com", "mod")
    make_admin("mod@example.com")

    post_id = client.post(
        "/posts", json={"title": "p", "content": "b"}, headers=author
    ).json()["id"]
    comment_id = client.post(
        f"/posts/{post_id}/comments", json={"content": "alice's comment"}, headers=author
    ).json()["id"]

    # Admin edits someone else's comment -> 200...
    edited = client.put(
        f"/posts/{post_id}/comments/{comment_id}",
        json={"content": "moderated comment"},
        headers=admin,
    )
    assert edited.status_code == 200
    assert edited.json()["content"] == "moderated comment"

    # ...and deletes it -> 204.
    assert client.delete(
        f"/posts/{post_id}/comments/{comment_id}", headers=admin
    ).status_code == 204


def test_non_admin_still_blocked(client):
    # Regression: without the admin role, the author-only 403 still holds — the
    # bypass must NOT leak to ordinary users.
    author = auth_headers(client, "alice@example.com", "alice")
    stranger = auth_headers(client, "bob@example.com", "bob")  # plain "user"

    post_id = client.post(
        "/posts", json={"title": "mine", "content": "body"}, headers=author
    ).json()["id"]
    comment_id = client.post(
        f"/posts/{post_id}/comments", json={"content": "hi"}, headers=author
    ).json()["id"]

    assert client.put(
        f"/posts/{post_id}", json={"title": "x", "content": "x"}, headers=stranger
    ).status_code == 403
    assert client.delete(f"/posts/{post_id}", headers=stranger).status_code == 403
    assert client.put(
        f"/posts/{post_id}/comments/{comment_id}",
        json={"content": "x"},
        headers=stranger,
    ).status_code == 403
    assert client.delete(
        f"/posts/{post_id}/comments/{comment_id}", headers=stranger
    ).status_code == 403
