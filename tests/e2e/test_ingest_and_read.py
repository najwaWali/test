"""
End-to-end tests exercising the HTTP surface against a real FastAPI
app + real Postgres. Phase 2 only — classification is not wired in
yet, so new tickets stay `pending` for the lifetime of these tests.
"""


def _create(client, source_id: str, subject: str = "s", body: str = "b"):
    return client.post(
        "/tickets",
        json={"id": source_id, "subject": subject, "body": body},
    )


def test_post_new_ticket_returns_201_pending(client):
    r = _create(client, "t-new", "Charged twice", "two charges on my card")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "t-new"
    assert body["subject"] == "Charged twice"
    assert body["status"] == "pending"
    assert body["category"] is None
    assert body["priority"] is None
    assert body["summary"] is None
    assert "created_at" in body and "updated_at" in body


def test_post_duplicate_source_id_returns_200_same_ticket(client):
    first = _create(client, "t-dup", "original", "original body").json()
    r = client.post(
        "/tickets",
        json={"id": "t-dup", "subject": "changed", "body": "changed body"},
    )
    assert r.status_code == 200
    body = r.json()
    # Returns the ORIGINAL ticket, not the duplicate payload.
    assert body["subject"] == "original"
    assert body["body"] == "original body"
    assert body["created_at"] == first["created_at"]

    listing = client.get("/tickets").json()
    assert listing["total"] == 1


def test_get_ticket_by_id_found(client):
    _create(client, "t-fetch")
    r = client.get("/tickets/t-fetch")
    assert r.status_code == 200
    assert r.json()["id"] == "t-fetch"


def test_get_ticket_not_found_returns_404_with_code(client):
    r = client.get("/tickets/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "ticket_not_found"
    assert "does-not-exist" in body["detail"]


def test_post_missing_field_returns_422_with_code(client):
    r = client.post("/tickets", json={"id": "t-x"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"


def test_post_id_too_long_returns_422(client):
    r = client.post(
        "/tickets",
        json={"id": "x" * 65, "subject": "s", "body": "b"},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_list_tickets_empty(client):
    r = client.get("/tickets")
    assert r.status_code == 200
    body = r.json()
    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_tickets_filters_and_pagination(client):
    # Seed via POST, then mutate category/priority/status directly
    # (classification isn't wired until phase 3).
    from app.db.queries import tickets as ticket_queries
    from app.db.session import SessionLocal

    for sid in ["a", "b", "c", "d", "e"]:
        _create(client, sid)

    with SessionLocal() as s:
        for sid, cat, pri, status in [
            ("a", "billing", "high", "classified"),
            ("b", "billing", "low", "classified"),
            ("c", "technical", "high", "classified"),
            ("d", None, None, "pending"),
            ("e", None, None, "pending"),
        ]:
            t = ticket_queries.get_by_source_id(s, sid)
            t.category = cat
            t.priority = pri
            t.status = status
        s.commit()

    # Filter: category=billing → 2 items
    r = client.get("/tickets?category=billing")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert {i["id"] for i in data["items"]} == {"a", "b"}

    # Combined filter
    r = client.get("/tickets?category=billing&priority=high")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == "a"

    # Pagination: limit=2, offset=0 then offset=2
    r1 = client.get("/tickets?limit=2&offset=0").json()
    r2 = client.get("/tickets?limit=2&offset=2").json()
    assert r1["total"] == 5
    assert len(r1["items"]) == 2
    assert len(r2["items"]) == 2
    assert {i["id"] for i in r1["items"]}.isdisjoint({i["id"] for i in r2["items"]})


def test_list_invalid_category_returns_422(client):
    r = client.get("/tickets?category=bogus")
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_list_invalid_limit_returns_422(client):
    r = client.get("/tickets?limit=0")
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
