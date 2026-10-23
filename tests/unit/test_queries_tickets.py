from app.db.queries import tickets as ticket_queries
from app.helpers.enums import Category, Priority, TicketStatus


def test_get_by_source_id_returns_none_when_missing(db_session):
    assert ticket_queries.get_by_source_id(db_session, "nope") is None


def test_insert_pending_creates_ticket_with_server_columns(db_session):
    t = ticket_queries.insert_pending(db_session, "t-insert", "subj", "body")
    db_session.commit()

    assert t.id is not None
    assert t.source_id == "t-insert"
    assert t.subject == "subj"
    assert t.body == "body"
    assert t.status == TicketStatus.PENDING.value
    assert t.category is None
    assert t.priority is None
    assert t.summary is None
    assert t.failure_reason is None
    assert t.created_at is not None
    assert t.updated_at is not None


def test_get_by_source_id_finds_inserted_ticket(db_session):
    inserted = ticket_queries.insert_pending(db_session, "t-get", "s", "b")
    db_session.commit()

    found = ticket_queries.get_by_source_id(db_session, "t-get")
    assert found is not None
    assert found.id == inserted.id
    assert found.source_id == "t-get"


def _seed_variants(session):
    """
    Build a small, deterministic fixture:
      billing/high (classified), billing/low (classified),
      technical/high (classified), two pending (no cat/pri).
    """
    specs = [
        ("v-1", "billing", "high", "classified"),
        ("v-2", "billing", "low", "classified"),
        ("v-3", "technical", "high", "classified"),
        ("v-4", None, None, "pending"),
        ("v-5", None, None, "pending"),
    ]
    for sid, cat, pri, status in specs:
        t = ticket_queries.insert_pending(session, sid, f"s-{sid}", "b")
        t.category = cat
        t.priority = pri
        t.status = status
    session.commit()


def test_list_filtered_no_filters_returns_all(db_session):
    _seed_variants(db_session)
    items, total = ticket_queries.list_filtered(
        db_session, category=None, priority=None, limit=100, offset=0
    )
    assert total == 5
    assert len(items) == 5


def test_list_filtered_by_category(db_session):
    _seed_variants(db_session)
    items, total = ticket_queries.list_filtered(
        db_session, category=Category.BILLING, priority=None, limit=100, offset=0
    )
    assert total == 2
    assert {t.source_id for t in items} == {"v-1", "v-2"}


def test_list_filtered_by_priority(db_session):
    _seed_variants(db_session)
    items, total = ticket_queries.list_filtered(
        db_session, category=None, priority=Priority.HIGH, limit=100, offset=0
    )
    assert total == 2
    assert {t.source_id for t in items} == {"v-1", "v-3"}


def test_list_filtered_combined_filters(db_session):
    _seed_variants(db_session)
    items, total = ticket_queries.list_filtered(
        db_session,
        category=Category.BILLING,
        priority=Priority.HIGH,
        limit=100,
        offset=0,
    )
    assert total == 1
    assert items[0].source_id == "v-1"


def test_list_filtered_pagination(db_session):
    _seed_variants(db_session)
    page1, total = ticket_queries.list_filtered(
        db_session, category=None, priority=None, limit=2, offset=0
    )
    page2, _ = ticket_queries.list_filtered(
        db_session, category=None, priority=None, limit=2, offset=2
    )
    assert total == 5
    assert len(page1) == 2
    assert len(page2) == 2
    # No overlap between page 1 and page 2.
    assert {t.source_id for t in page1}.isdisjoint({t.source_id for t in page2})


def test_list_filtered_orders_newest_first(db_session):
    # Three separate commits so each row gets a distinct `NOW()`. The
    # tiny sleep guards against sub-millisecond collisions on fast boxes.
    import time

    for sid in ("o-1", "o-2", "o-3"):
        ticket_queries.insert_pending(db_session, sid, "s", "b")
        db_session.commit()
        time.sleep(0.005)

    items, _ = ticket_queries.list_filtered(
        db_session, category=None, priority=None, limit=10, offset=0
    )
    assert [t.source_id for t in items] == ["o-3", "o-2", "o-1"]
