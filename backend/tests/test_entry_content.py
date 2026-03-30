"""Tests for reading/writing entry text content via the /v1/files/ API."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///file:test_entry_content?mode=memory&cache=shared&uri=true",
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


def _setup(client) -> tuple[str, str, str]:
    """Register, login, create notebook + entry + scoped token.

    Returns (entry_id, notebook_id, raw_token).
    """
    client.post("/api/auth/register", json={"name": "A", "email": "a@a.com", "password": "secret123"})
    client.post("/api/auth/login", json={"email": "a@a.com", "password": "secret123"})

    nb = client.post("/api/notebooks/", json={"title": "nb"}).json()
    entry = client.post(
        "/api/entries/",
        json={
            "notebook_id": nb["id"],
            "title": "Experiment 1",
            "content_blocks": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}], "children": []},
            ],
            "tags": [],
        },
    ).json()

    token_resp = client.post(
        "/api/scoped-tokens/",
        json={
            "resource_type": "notebook",
            "resource_id": nb["id"],
            "access_level": "readwrite",
            "label": "test",
        },
    ).json()

    return entry["id"], nb["id"], token_resp["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestReadContent:
    def test_read_markdown(self, client):
        _, _, token = _setup(client)
        resp = client.get("/api/v1/files/Experiment 1", params={"content": "markdown"}, headers=_auth(token))
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "Experiment 1" in resp.text
        assert "Hello world" in resp.text

    def test_read_blocks(self, client):
        _, _, token = _setup(client)
        resp = client.get("/api/v1/files/Experiment 1", params={"content": "blocks"}, headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Experiment 1"
        assert data["blocks"][0]["type"] == "paragraph"

    def test_read_content_on_root_fails(self, client):
        _, _, token = _setup(client)
        resp = client.get("/api/v1/files/", params={"content": "markdown"}, headers=_auth(token))
        assert resp.status_code == 400

    def test_invalid_content_param(self, client):
        _, _, token = _setup(client)
        resp = client.get("/api/v1/files/Experiment 1", params={"content": "html"}, headers=_auth(token))
        assert resp.status_code == 400

    def test_read_entry_scoped(self, client):
        """Entry-scoped token: empty path = the entry itself."""
        client.post("/api/auth/register", json={"name": "B", "email": "b@b.com", "password": "secret123"})
        client.post("/api/auth/login", json={"email": "b@b.com", "password": "secret123"})
        nb = client.post("/api/notebooks/", json={"title": "nb2"}).json()
        entry = client.post(
            "/api/entries/",
            json={
                "notebook_id": nb["id"],
                "title": "E",
                "content_blocks": [{"type": "paragraph", "content": [{"type": "text", "text": "body"}], "children": []}],
                "tags": [],
            },
        ).json()
        token = client.post(
            "/api/scoped-tokens/",
            json={"resource_type": "entry", "resource_id": entry["id"], "access_level": "readwrite", "label": "t"},
        ).json()["token"]

        resp = client.get("/api/v1/files/", params={"content": "markdown"}, headers=_auth(token))
        assert resp.status_code == 200
        assert "body" in resp.text


class TestRename:
    def test_rename_entry(self, client):
        _, _, token = _setup(client)
        resp = client.patch(
            "/api/v1/files/Experiment 1",
            headers={**_auth(token), "Content-Type": "application/json"},
            content=json.dumps({"name": "Experiment 2"}),
        )
        assert resp.status_code == 200
        assert resp.json() == {"path": "Experiment 2", "status": "renamed"}

        # Old path is gone
        resp = client.get("/api/v1/files/Experiment 1", params={"content": "blocks"}, headers=_auth(token))
        assert resp.status_code == 404

        # New path works
        resp = client.get("/api/v1/files/Experiment 2", params={"content": "blocks"}, headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["title"] == "Experiment 2"

    def test_rename_readonly_rejected(self, client):
        client.post("/api/auth/register", json={"name": "D", "email": "d@d.com", "password": "secret123"})
        client.post("/api/auth/login", json={"email": "d@d.com", "password": "secret123"})
        nb = client.post("/api/notebooks/", json={"title": "nb4"}).json()
        client.post("/api/entries/", json={"notebook_id": nb["id"], "title": "E", "content_blocks": [], "tags": []})
        token = client.post(
            "/api/scoped-tokens/",
            json={"resource_type": "notebook", "resource_id": nb["id"], "access_level": "read", "label": "ro"},
        ).json()["token"]

        resp = client.patch(
            "/api/v1/files/E",
            headers={**_auth(token), "Content-Type": "application/json"},
            content=json.dumps({"name": "E2"}),
        )
        assert resp.status_code == 403

    def test_rename_missing_name_rejected(self, client):
        _, _, token = _setup(client)
        resp = client.patch(
            "/api/v1/files/Experiment 1",
            headers={**_auth(token), "Content-Type": "application/json"},
            content=json.dumps({"wrong_key": "x"}),
        )
        assert resp.status_code == 400


class TestWriteBlocks:
    def test_write_blocks(self, client):
        _, _, token = _setup(client)
        payload = {"blocks": [{"type": "paragraph", "content": [{"type": "text", "text": "Replaced"}], "children": []}]}
        resp = client.put(
            "/api/v1/files/Experiment 1",
            params={"content": "blocks"},
            headers={**_auth(token), "Content-Type": "application/json"},
            content=json.dumps(payload),
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "updated"

        # Verify round-trip
        resp = client.get("/api/v1/files/Experiment 1", params={"content": "blocks"}, headers=_auth(token))
        assert resp.json()["blocks"][0]["content"][0]["text"] == "Replaced"

    def test_write_markdown_rejected(self, client):
        _, _, token = _setup(client)
        resp = client.put(
            "/api/v1/files/Experiment 1",
            params={"content": "markdown"},
            headers={**_auth(token), "Content-Type": "text/markdown"},
            content="# Title\n\nBody\n",
        )
        assert resp.status_code == 400

    def test_write_missing_blocks_key_rejected(self, client):
        _, _, token = _setup(client)
        resp = client.put(
            "/api/v1/files/Experiment 1",
            params={"content": "blocks"},
            headers={**_auth(token), "Content-Type": "application/json"},
            content=json.dumps([{"type": "paragraph"}]),  # bare list, not {"blocks": [...]}
        )
        assert resp.status_code == 400

    def test_write_readonly_token_rejected(self, client):
        client.post("/api/auth/register", json={"name": "C", "email": "c@c.com", "password": "secret123"})
        client.post("/api/auth/login", json={"email": "c@c.com", "password": "secret123"})
        nb = client.post("/api/notebooks/", json={"title": "nb3"}).json()
        client.post("/api/entries/", json={"notebook_id": nb["id"], "title": "E", "content_blocks": [], "tags": []})
        token = client.post(
            "/api/scoped-tokens/",
            json={"resource_type": "notebook", "resource_id": nb["id"], "access_level": "read", "label": "ro"},
        ).json()["token"]

        resp = client.put(
            "/api/v1/files/E",
            params={"content": "blocks"},
            headers={**_auth(token), "Content-Type": "application/json"},
            content=json.dumps({"blocks": []}),
        )
        assert resp.status_code == 403
