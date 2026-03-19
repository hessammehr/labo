import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///file:test_att?mode=memory&cache=shared&uri=true",
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


def _setup(client) -> str:
    """Register, login, create a notebook + entry. Return the entry id."""
    client.post("/api/auth/register", json={"name": "A", "email": "a@a.com", "password": "secret123"})
    client.post("/api/auth/login", json={"email": "a@a.com", "password": "secret123"})
    nb = client.post("/api/notebooks/", json={"title": "nb", "description": ""}).json()
    entry = client.post(
        "/api/entries/",
        json={"notebook_id": nb["id"], "title": "e", "content_blocks": [], "tags": []},
    ).json()
    return entry["id"]


def _upload(client, entry_id: str, filename: str, content: bytes = b"x", content_type: str | None = None):
    """Upload an attachment, optionally overriding content_type."""
    ct = content_type or "application/octet-stream"
    return client.post(
        "/api/attachments/",
        data={"entry_id": entry_id},
        files={"file": (filename, content, ct)},
    )


class TestMimeDetection:
    """The backend should infer a useful MIME type from the filename
    when the client sends application/octet-stream."""

    @pytest.mark.parametrize(
        "filename, expected_mime",
        [
            ("data.json", "application/json"),
            ("notes.md", "text/markdown"),
            ("style.css", "text/css"),
            ("data.csv", "text/csv"),
            ("page.html", "text/html"),
            ("script.py", "text/x-python"),
        ],
    )
    def test_mime_guessed_from_extension(self, client, filename, expected_mime):
        entry_id = _setup(client)
        resp = _upload(client, entry_id, filename)
        assert resp.status_code == 201
        assert resp.json()["mime_type"] == expected_mime

    def test_browser_mime_preserved_when_informative(self, client):
        entry_id = _setup(client)
        resp = _upload(client, entry_id, "file.bin", content_type="image/png")
        assert resp.status_code == 201
        assert resp.json()["mime_type"] == "image/png"

    def test_octet_stream_kept_when_extension_unknown(self, client):
        entry_id = _setup(client)
        resp = _upload(client, entry_id, "data.xyzzy")
        assert resp.status_code == 201
        assert resp.json()["mime_type"] == "application/octet-stream"
