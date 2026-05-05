import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app

# Use a single in-memory DB with shared cache so the test engine and all connections see the same tables
engine = create_engine(
    "sqlite:///file:test?mode=memory&cache=shared&uri=true",
    connect_args={"check_same_thread": False},
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def db():
    Base.metadata.create_all(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db):
    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, name="Alice", email="alice@example.com", password="secret123"):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def _login(client, email="alice@example.com", password="secret123"):
    """Login and return the client (cookies are set automatically on the TestClient)."""
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp


class TestHealth:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}


class TestAuth:
    def test_register_and_login(self, client):
        resp = _register(client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert data["role"] == "user"

        # Registration auto-logs in (sets cookie)
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "alice@example.com"

    def test_login_sets_cookie(self, client):
        _register(client)
        # Clear cookies to test login flow
        client.cookies.clear()
        _login(client)
        me = client.get("/api/auth/me")
        assert me.status_code == 200

    def test_logout(self, client):
        _register(client)
        _login(client)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 204
        me = client.get("/api/auth/me")
        assert me.status_code == 401

    def test_duplicate_email(self, client):
        _register(client)
        resp = _register(client)
        assert resp.status_code == 409

    def test_bad_login(self, client):
        _register(client)
        resp = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong"})
        assert resp.status_code == 401

    def test_unauthenticated_access(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestApiKeys:
    def test_create_and_use(self, client):
        _register(client)
        _login(client)

        # Create API key
        resp = client.post("/api/auth/api-keys", json={"name": "Test Key"})
        assert resp.status_code == 201
        key_data = resp.json()
        assert key_data["name"] == "Test Key"
        raw_key = key_data["key"]
        assert raw_key.startswith("labo_")

        # List keys
        resp = client.get("/api/auth/api-keys")
        assert len(resp.json()) == 1

        # Use API key (clear cookies first)
        client.cookies.clear()
        me = client.get("/api/auth/me", headers={"X-API-Key": raw_key})
        assert me.status_code == 200
        assert me.json()["email"] == "alice@example.com"

    def test_revoke_key(self, client):
        _register(client)
        _login(client)

        resp = client.post("/api/auth/api-keys", json={"name": "Temp"})
        key_id = resp.json()["id"]
        raw_key = resp.json()["key"]

        # Revoke
        resp = client.delete(f"/api/auth/api-keys/{key_id}")
        assert resp.status_code == 204

        # Key no longer works
        client.cookies.clear()
        me = client.get("/api/auth/me", headers={"X-API-Key": raw_key})
        assert me.status_code == 401


class TestNotebooks:
    def test_crud(self, client):
        _register(client)
        _login(client)

        # Create
        resp = client.post("/api/notebooks/", json={"title": "Lab 1"})
        assert resp.status_code == 201
        nb = resp.json()
        nb_id = nb["id"]

        # List
        resp = client.get("/api/notebooks/")
        assert len(resp.json()) == 1

        # Get
        resp = client.get(f"/api/notebooks/{nb_id}")
        assert resp.json()["title"] == "Lab 1"

        # Update
        resp = client.patch(f"/api/notebooks/{nb_id}", json={"title": "Lab 1 (updated)"})
        assert resp.json()["title"] == "Lab 1 (updated)"

        # Delete
        resp = client.delete(f"/api/notebooks/{nb_id}")
        assert resp.status_code == 204


class TestEntries:
    def test_create_and_revisions(self, client):
        _register(client)
        _login(client)

        nb = client.post("/api/notebooks/", json={"title": "NB"}).json()
        nb_id = nb["id"]

        # Create entry
        resp = client.post(
            "/api/entries/",
            json={"notebook_id": nb_id, "title": "Exp 1", "content_blocks": [{"type": "text", "text": "hello"}]},
        )
        assert resp.status_code == 201
        entry = resp.json()
        entry_id = entry["id"]
        assert entry["version"] == 1

        # Auto-save (no checkpoint) → no revision
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "hello v2"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

        resp = client.get(f"/api/entries/{entry_id}/revisions")
        assert len(resp.json()) == 0

        # Title-only update → no revision even with checkpoint
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={"title": "Exp 1 (v2)", "checkpoint": True},
        )
        assert resp.json()["title"] == "Exp 1 (v2)"
        assert resp.json()["version"] == 3

        resp = client.get(f"/api/entries/{entry_id}/revisions")
        assert len(resp.json()) == 0

        # Checkpoint save with content → creates revision
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={
                "content_blocks": [{"type": "text", "text": "hello v3"}],
                "checkpoint": True,
                "change_summary": "manual save",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 4

        resp = client.get(f"/api/entries/{entry_id}/revisions")
        revisions = resp.json()
        assert len(revisions) == 1
        assert revisions[0]["change_summary"] == "manual save"
        # Revision stores the state *before* the checkpoint
        assert revisions[0]["content_blocks"] == [{"type": "text", "text": "hello v2"}]

    def test_auto_checkpoint_after_idle_gap(self, client, db):
        from datetime import timedelta
        from app.models import Entry, _utcnow

        _register(client)
        _login(client)

        nb = client.post("/api/notebooks/", json={"title": "NB"}).json()
        entry = client.post(
            "/api/entries/",
            json={
                "notebook_id": nb["id"],
                "title": "E",
                "content_blocks": [{"type": "text", "text": "v1"}],
            },
        ).json()
        entry_id = entry["id"]

        # Two back-to-back autosaves: continuous editing, no idle gap → no revisions.
        client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "v2"}]},
        )
        client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "v3"}]},
        )
        assert client.get(f"/api/entries/{entry_id}/revisions").json() == []

        # Simulate the user stepping away by backdating updated_at past the threshold.
        db_entry = db.query(Entry).filter(Entry.id == entry_id).first()
        db_entry.updated_at = _utcnow() - timedelta(minutes=15)
        db.commit()

        # Next autosave should snapshot the pre-update state ("v3") as an auto checkpoint.
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "v4"}]},
        )
        assert resp.status_code == 200

        revisions = client.get(f"/api/entries/{entry_id}/revisions").json()
        assert len(revisions) == 1
        assert revisions[0]["change_summary"] == "Auto checkpoint"
        assert revisions[0]["content_blocks"] == [{"type": "text", "text": "v3"}]

        # The autosave that just landed advanced updated_at, so an immediate
        # follow-up autosave must NOT create another revision.
        client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "v5"}]},
        )
        assert len(client.get(f"/api/entries/{entry_id}/revisions").json()) == 1

    def test_auto_checkpoint_does_not_double_with_explicit_checkpoint(self, client, db):
        from datetime import timedelta
        from app.models import Entry, _utcnow

        _register(client)
        _login(client)

        nb = client.post("/api/notebooks/", json={"title": "NB"}).json()
        entry = client.post(
            "/api/entries/",
            json={
                "notebook_id": nb["id"],
                "title": "E",
                "content_blocks": [{"type": "text", "text": "v1"}],
            },
        ).json()
        entry_id = entry["id"]

        # Idle gap, then an explicit checkpoint — should yield exactly one
        # revision (with the user's summary), not one auto + one explicit.
        db_entry = db.query(Entry).filter(Entry.id == entry_id).first()
        db_entry.updated_at = _utcnow() - timedelta(minutes=15)
        db.commit()

        client.put(
            f"/api/entries/{entry_id}",
            json={
                "content_blocks": [{"type": "text", "text": "v2"}],
                "checkpoint": True,
                "change_summary": "manual",
            },
        )
        revisions = client.get(f"/api/entries/{entry_id}/revisions").json()
        assert len(revisions) == 1
        assert revisions[0]["change_summary"] == "manual"

    def test_rejects_stale_entry_update(self, client):
        _register(client)
        _login(client)

        nb = client.post("/api/notebooks/", json={"title": "NB"}).json()
        entry = client.post(
            "/api/entries/",
            json={"notebook_id": nb["id"], "title": "E", "content_blocks": [{"type": "text", "text": "v1"}]},
        ).json()
        entry_id = entry["id"]

        # User A snapshot version
        stale_version = entry["version"]

        # User B updates first
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "v2"}]},
        )
        assert resp.status_code == 200

        # User A attempts save with stale version
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={
                "content_blocks": [{"type": "text", "text": "v3"}],
                "expected_version": stale_version,
            },
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["message"] == "Entry was modified by someone else"
        assert "current_version" in detail

    def test_stale_noop_update_is_accepted(self, client):
        _register(client)
        _login(client)

        nb = client.post("/api/notebooks/", json={"title": "NB"}).json()
        entry = client.post(
            "/api/entries/",
            json={"notebook_id": nb["id"], "title": "E", "content_blocks": [{"type": "text", "text": "v1"}]},
        ).json()
        entry_id = entry["id"]
        stale_version = entry["version"]

        # Another session updates first
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "v2"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

        # Stale expected_version, but request is a no-op against current data.
        resp = client.put(
            f"/api/entries/{entry_id}",
            json={
                "content_blocks": [{"type": "text", "text": "v2"}],
                "expected_version": stale_version,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    def test_restore_revision(self, client):
        _register(client)
        _login(client)

        nb = client.post("/api/notebooks/", json={"title": "NB"}).json()

        entry = client.post(
            "/api/entries/",
            json={"notebook_id": nb["id"], "title": "E", "content_blocks": [{"type": "text", "text": "v1"}]},
        ).json()
        entry_id = entry["id"]

        # Checkpoint save → creates revision with v1
        client.put(
            f"/api/entries/{entry_id}",
            json={"content_blocks": [{"type": "text", "text": "v2"}], "checkpoint": True},
        )

        revisions = client.get(f"/api/entries/{entry_id}/revisions").json()
        assert len(revisions) == 1
        rev_id = revisions[0]["id"]

        # Restore revision (v1)
        resp = client.post(f"/api/entries/{entry_id}/revisions/{rev_id}/restore")
        assert resp.status_code == 200
        assert resp.json()["content_blocks"] == [{"type": "text", "text": "v1"}]
        assert resp.json()["version"] == 3

        # Should have created an undo checkpoint
        revisions = client.get(f"/api/entries/{entry_id}/revisions").json()
        assert len(revisions) == 2
