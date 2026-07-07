# Tests for comments. Two behaviours matter here:
#   1) CREATING a comment has NO ownership check (comment on anyone's post).
#   2) EDITING/DELETING a comment DOES (author-only), plus nested integrity
#      (the comment must belong to the post named in the URL).


def auth_headers(client, email, username):
    client.post(
        "/users",
        json={"username": username, "email": email, "password": "supersecret"},
    )
    token = client.post(
        "/login", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_post(client, headers, title="a post"):
    # Helper: create a post and return its id.
    return client.post(
        "/posts", json={"title": title, "content": "body"}, headers=headers
    ).json()["id"]


def test_any_user_can_comment_on_others_post(client):
    alice = auth_headers(client, "alice@example.com", "alice")
    bob = auth_headers(client, "bob@example.com", "bob")

    # Alice writes a post; Bob (a DIFFERENT user) comments on it.
    post_id = make_post(client, alice)
    response = client.post(
        f"/posts/{post_id}/comments",
        json={"content": "nice post!"},
        headers=bob,
    )
    # 201 — no 403 here, because commenting is open to any logged-in user.
    assert response.status_code == 201

    body = response.json()
    assert body["content"] == "nice post!"
    # post_id (from the URL) and author_id (from Bob's token) are stamped by the
    # server, not sent in the body.
    assert body["post_id"] == post_id
    bob_me = client.get("/users/me", headers=bob).json()
    assert body["author_id"] == bob_me["id"]


def test_comment_requires_existing_post(client):
    alice = auth_headers(client, "alice@example.com", "alice")

    # A VALID-shaped ObjectId (24 hex chars) that doesn't exist -> 404. This is
    # the referential-integrity guard: no attaching comments to a ghost post.
    missing_id = "0" * 24
    not_found = client.post(
        f"/posts/{missing_id}/comments",
        json={"content": "hi"},
        headers=alice,
    )
    assert not_found.status_code == 404

    # A malformed id (not a valid ObjectId shape) -> 400, before the lookup.
    bad_id = client.post(
        "/posts/not-a-valid-id/comments",
        json={"content": "hi"},
        headers=alice,
    )
    assert bad_id.status_code == 400


def test_comment_edit_delete_is_author_only(client):
    alice = auth_headers(client, "alice@example.com", "alice")
    bob = auth_headers(client, "bob@example.com", "bob")

    # Alice owns the POST; Bob writes the COMMENT.
    post_id = make_post(client, alice)
    comment_id = client.post(
        f"/posts/{post_id}/comments", json={"content": "bob's comment"}, headers=bob
    ).json()["id"]

    # Alice owns the post but NOT the comment -> she cannot edit or delete it.
    # (Post ownership is irrelevant here; comments are author-only.)
    assert client.put(
        f"/posts/{post_id}/comments/{comment_id}",
        json={"content": "hacked"},
        headers=alice,
    ).status_code == 403
    assert client.delete(
        f"/posts/{post_id}/comments/{comment_id}", headers=alice
    ).status_code == 403

    # Bob, the author, CAN edit his own comment -> 200 with the new text...
    edited = client.put(
        f"/posts/{post_id}/comments/{comment_id}",
        json={"content": "edited by bob"},
        headers=bob,
    )
    assert edited.status_code == 200
    assert edited.json()["content"] == "edited by bob"

    # ...and delete it -> 204.
    assert client.delete(
        f"/posts/{post_id}/comments/{comment_id}", headers=bob
    ).status_code == 204


def test_comment_must_belong_to_the_post_in_the_url(client):
    alice = auth_headers(client, "alice@example.com", "alice")

    # Two posts. The comment goes on post A.
    post_a = make_post(client, alice, title="post A")
    post_b = make_post(client, alice, title="post B")
    comment_id = client.post(
        f"/posts/{post_a}/comments", json={"content": "on A"}, headers=alice
    ).json()["id"]

    # Try to edit that comment through post B's URL. Alice IS the author (so it's
    # not a 403) — but the comment doesn't belong to post B, so the combined
    # lookup {_id, post_id} finds nothing -> 404. This stops one post's URL from
    # reaching into another post's comments.
    wrong_post = client.put(
        f"/posts/{post_b}/comments/{comment_id}",
        json={"content": "moved?"},
        headers=alice,
    )
    assert wrong_post.status_code == 404

    # Same integrity check on delete.
    wrong_delete = client.delete(
        f"/posts/{post_b}/comments/{comment_id}", headers=alice
    )
    assert wrong_delete.status_code == 404


def test_list_comments_is_public_and_oldest_first(client):
    alice = auth_headers(client, "alice@example.com", "alice")
    post_id = make_post(client, alice)

    # Add three comments in order.
    for text in ["first", "second", "third"]:
        client.post(
            f"/posts/{post_id}/comments", json={"content": text}, headers=alice
        )

    # Listing is PUBLIC — no Authorization header needed.
    listed = client.get(f"/posts/{post_id}/comments")
    assert listed.status_code == 200

    contents = [c["content"] for c in listed.json()]
    # OLDEST-first (sort created_at ascending) so a thread reads top-to-bottom —
    # the opposite of posts, which are newest-first.
    assert contents == ["first", "second", "third"]
    # X-Total-Count reports the number of comments on this post.
    assert listed.headers["X-Total-Count"] == "3"


def test_comments_pagination(client):
    alice = auth_headers(client, "alice@example.com", "alice")
    post_id = make_post(client, alice)

    # Five comments, in order c0..c4.
    for n in range(5):
        client.post(
            f"/posts/{post_id}/comments", json={"content": f"c{n}"}, headers=alice
        )

    # Page 1 (oldest-first): the two earliest comments.
    page1 = client.get(f"/posts/{post_id}/comments?skip=0&limit=2")
    assert [c["content"] for c in page1.json()] == ["c0", "c1"]
    # Full total on every page, regardless of the page window.
    assert page1.headers["X-Total-Count"] == "5"

    # Page 2 continues DOWN the thread (not overlapping page 1).
    page2 = client.get(f"/posts/{post_id}/comments?skip=2&limit=2")
    assert [c["content"] for c in page2.json()] == ["c2", "c3"]

    # Last partial page.
    page3 = client.get(f"/posts/{post_id}/comments?skip=4&limit=2")
    assert [c["content"] for c in page3.json()] == ["c4"]

    # Same bounds as every list route: limit=0 -> 422 before the handler runs.
    assert client.get(f"/posts/{post_id}/comments?limit=0").status_code == 422
