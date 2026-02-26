import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
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
    return client.post("/auth/register", json={"name": name, "email": email, "password": password})


def _login(client, email="alice@example.com", password="secret123"):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


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

        token = _login(client)
        me = client.get("/auth/me", headers=_auth(token))
        assert me.status_code == 200
        assert me.json()["email"] == "alice@example.com"

    def test_duplicate_email(self, client):
        _register(client)
        resp = _register(client)
        assert resp.status_code == 409

    def test_bad_login(self, client):
        _register(client)
        resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong"})
        assert resp.status_code == 401


class TestNotebooks:
    def test_crud(self, client):
        _register(client)
        token = _login(client)
        h = _auth(token)

        # Create
        resp = client.post("/notebooks/", json={"title": "Lab 1"}, headers=h)
        assert resp.status_code == 201
        nb = resp.json()
        nb_id = nb["id"]

        # List
        resp = client.get("/notebooks/", headers=h)
        assert len(resp.json()) == 1

        # Get
        resp = client.get(f"/notebooks/{nb_id}", headers=h)
        assert resp.json()["title"] == "Lab 1"

        # Update
        resp = client.patch(f"/notebooks/{nb_id}", json={"title": "Lab 1 (updated)"}, headers=h)
        assert resp.json()["title"] == "Lab 1 (updated)"

        # Delete
        resp = client.delete(f"/notebooks/{nb_id}", headers=h)
        assert resp.status_code == 204


class TestEntries:
    def test_create_and_revisions(self, client):
        _register(client)
        token = _login(client)
        h = _auth(token)

        nb = client.post("/notebooks/", json={"title": "NB"}, headers=h).json()
        nb_id = nb["id"]

        # Create entry
        resp = client.post(
            "/entries/",
            json={"notebook_id": nb_id, "title": "Exp 1", "content_blocks": [{"type": "text", "text": "hello"}]},
            headers=h,
        )
        assert resp.status_code == 201
        entry = resp.json()
        entry_id = entry["id"]

        # Update → creates revision
        resp = client.put(
            f"/entries/{entry_id}",
            json={"title": "Exp 1 (v2)", "change_summary": "updated title"},
            headers=h,
        )
        assert resp.json()["title"] == "Exp 1 (v2)"

        # Check revisions
        resp = client.get(f"/entries/{entry_id}/revisions", headers=h)
        revisions = resp.json()
        assert len(revisions) == 1
        assert revisions[0]["change_summary"] == "updated title"
