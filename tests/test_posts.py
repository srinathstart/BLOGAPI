# Tests for posts, focused on OWNERSHIP (the 403 rule). We need TWO different
# users here, so the helper takes an email/username and returns a ready-to-use
# Authorization header for that user.


def auth_headers(client, email, username):
    # Register the user...
    client.post(
        "/users",
        json={"username": username, "email": email, "password": "supersecret"},
    )
    # ...log in, grab the token, and wrap it as a Bearer header.
    token = client.post(
        "/login", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_post_stamps_author_from_token(client):
    headers = auth_headers(client, "alice@example.com", "alice")

    response = client.post(
        "/posts",
        json={"title": "My first post", "content": "Hello world"},
        headers=headers,
    )
    assert response.status_code == 201

    body = response.json()
    assert body["title"] == "My first post"
    assert body["content"] == "Hello world"
    # author_id was NOT in the request body — the route stamped it from the
    # token. It must match the id of the logged-in user (from /users/me).
    me = client.get("/users/me", headers=headers).json()
    assert body["author_id"] == me["id"]
    # And a server-side timestamp was added.
    assert "created_at" in body


def test_other_user_cannot_edit_or_delete_post(client):
    # Two DIFFERENT users, each with their own token.
    alice = auth_headers(client, "alice@example.com", "alice")
    bob = auth_headers(client, "bob@example.com", "bob")

    # Alice creates a post.
    post_id = client.post(
        "/posts",
        json={"title": "Alice's post", "content": "mine"},
        headers=alice,
    ).json()["id"]

    # Bob is logged in (so NOT a 401) but he doesn't own the post -> 403 on
    # every mutating verb: PUT, PATCH, DELETE.
    put = client.put(
        f"/posts/{post_id}",
        json={"title": "hacked", "content": "hacked"},
        headers=bob,
    )
    assert put.status_code == 403

    patch = client.patch(
        f"/posts/{post_id}", json={"title": "hacked"}, headers=bob
    )
    assert patch.status_code == 403

    delete = client.delete(f"/posts/{post_id}", headers=bob)
    assert delete.status_code == 403


def test_author_can_edit_and_delete_own_post(client):
    alice = auth_headers(client, "alice@example.com", "alice")

    post_id = client.post(
        "/posts",
        json={"title": "original", "content": "original body"},
        headers=alice,
    ).json()["id"]

    # Alice edits her OWN post -> 200, and the new text is returned.
    edited = client.put(
        f"/posts/{post_id}",
        json={"title": "edited", "content": "edited body"},
        headers=alice,
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "edited"
    assert edited.json()["content"] == "edited body"

    # Alice deletes her OWN post -> 204 No Content.
    deleted = client.delete(f"/posts/{post_id}", headers=alice)
    assert deleted.status_code == 204

    # ...and it's really gone: fetching it now -> 404.
    gone = client.get(f"/posts/{post_id}")
    assert gone.status_code == 404


def test_search_posts_by_title_is_case_insensitive(client):
    alice = auth_headers(client, "alice@example.com", "alice")

    # Three posts: two contain "hello" in the title (different cases), one not.
    for title in ["Hello World", "say hello loudly", "Goodbye Moon"]:
        client.post("/posts", json={"title": title, "content": "x"}, headers=alice)

    # ?q=hello matches both "Hello World" and "say hello loudly" (case-insensitive
    # substring), but NOT "Goodbye Moon".
    found = client.get("/posts?q=hello")
    assert found.status_code == 200
    assert len(found.json()) == 2
    # The Day-14 header uses the SAME filter as the search -> reports 2, not 3.
    assert found.headers["X-Total-Count"] == "2"

    # No ?q -> the filter is {}, so all three posts come back.
    all_posts = client.get("/posts")
    assert len(all_posts.json()) == 3
    assert all_posts.headers["X-Total-Count"] == "3"

    # A query that matches nothing -> empty list and a count of 0 (not an error).
    none = client.get("/posts?q=zzz-nothing")
    assert none.status_code == 200
    assert none.json() == []
    assert none.headers["X-Total-Count"] == "0"


def test_posts_pagination_windows(client):
    alice = auth_headers(client, "alice@example.com", "alice")

    # Create 5 posts.
    for n in range(5):
        client.post("/posts", json={"title": f"post {n}", "content": "x"}, headers=alice)

    # First page of 2.
    page1 = client.get("/posts?skip=0&limit=2")
    assert len(page1.json()) == 2
    # X-Total-Count is the FULL total (5), independent of the page size.
    assert page1.headers["X-Total-Count"] == "5"

    # Second page of 2 (skip the first 2).
    page2 = client.get("/posts?skip=2&limit=2")
    assert len(page2.json()) == 2
    assert page2.headers["X-Total-Count"] == "5"

    # The two pages must NOT overlap — skip/limit is a moving window over the
    # sorted list, so their ids are disjoint (this holds whatever the sort order).
    ids1 = {p["id"] for p in page1.json()}
    ids2 = {p["id"] for p in page2.json()}
    assert ids1.isdisjoint(ids2)

    # Last partial page: skip 4 -> only 1 left.
    page3 = client.get("/posts?skip=4&limit=2")
    assert len(page3.json()) == 1

    # Past the end -> empty list, NOT an error.
    beyond = client.get("/posts?skip=99&limit=2")
    assert beyond.status_code == 200
    assert beyond.json() == []


def test_posts_pagination_bounds_are_422(client):
    # limit must be >= 1 -> limit=0 is rejected by FastAPI before our code runs.
    assert client.get("/posts?limit=0").status_code == 422

    # skip must be >= 0 -> a negative offset is rejected.
    assert client.get("/posts?skip=-1").status_code == 422

    # limit must be <= 100 -> asking for 101 is rejected, so a client can't pull
    # the whole collection in one page.
    assert client.get("/posts?limit=101").status_code == 422


def test_get_single_post(client):
    alice = auth_headers(client, "alice@example.com", "alice")
    post_id = client.post(
        "/posts", json={"title": "solo", "content": "body"}, headers=alice
    ).json()["id"]

    # Real id -> 200 and the right post (public, no auth needed).
    ok = client.get(f"/posts/{post_id}")
    assert ok.status_code == 200
    assert ok.json()["title"] == "solo"

    # Malformed id -> 400.
    assert client.get("/posts/not-a-valid-id").status_code == 400

    # Valid-shaped but missing -> 404.
    assert client.get(f"/posts/{'0' * 24}").status_code == 404


def test_patch_partial_update_and_empty_body(client):
    alice = auth_headers(client, "alice@example.com", "alice")
    post_id = client.post(
        "/posts", json={"title": "orig title", "content": "orig body"}, headers=alice
    ).json()["id"]

    # PATCH only the title. exclude_unset means content is NOT touched.
    patched = client.patch(
        f"/posts/{post_id}", json={"title": "new title"}, headers=alice
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "new title"
    assert patched.json()["content"] == "orig body"  # unchanged

    # Empty body -> nothing to update -> 400 (an empty $set would error in Mongo,
    # so the route stops early with a clear message).
    empty = client.patch(f"/posts/{post_id}", json={}, headers=alice)
    assert empty.status_code == 400

    # Explicit null is dropped by the "if value is not None" safety net, so a
    # body of only nulls also has nothing to apply -> 400 (never nulls a field).
    only_null = client.patch(
        f"/posts/{post_id}", json={"title": None}, headers=alice
    )
    assert only_null.status_code == 400
