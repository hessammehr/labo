"""Tests for the global fuzzy search endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///file:test_search?mode=memory&cache=shared&uri=true",
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client, name="Alice", email="alice@example.com", password="secret123"):
    resp = client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    assert resp.status_code == 201
    return resp.json()


def _login(client, email="alice@example.com", password="secret123"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp


def _create_notebook(client, title="Lab Notebook"):
    resp = client.post("/api/notebooks/", json={"title": title, "description": ""})
    assert resp.status_code == 201
    return resp.json()


def _create_entry(client, notebook_id, title="Experiment 1", content_blocks=None, tags=None):
    resp = client.post(
        "/api/entries/",
        json={
            "notebook_id": notebook_id,
            "title": title,
            "content_blocks": content_blocks or [],
            "tags": tags or [],
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _share_notebook(client, notebook_id, subject_id, access_level="read"):
    resp = client.post(
        "/api/permissions/",
        json={
            "subject_id": subject_id,
            "resource_type": "notebook",
            "resource_id": notebook_id,
            "access_level": access_level,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _search(client, query, expected_status=200):
    resp = client.get("/api/search/", params={"q": query})
    assert resp.status_code == expected_status
    return resp.json()


def _blocknote_text(*paragraphs: str) -> list[dict]:
    """Build minimal BlockNote-style content blocks with text."""
    return [
        {
            "id": f"block-{i}",
            "type": "paragraph",
            "content": [{"type": "text", "text": p}],
            "children": [],
        }
        for i, p in enumerate(paragraphs)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchAuth:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/search/", params={"q": "anything"})
        assert resp.status_code == 401

    def test_empty_query_returns_422(self, client):
        _register(client)
        _login(client)
        resp = client.get("/api/search/", params={"q": ""})
        assert resp.status_code == 422


class TestSearchVisibility:
    """Core tests: users should only see notebooks/entries they have access to."""

    def test_owner_sees_own_notebooks_and_entries(self, client):
        _register(client)
        _login(client)
        nb = _create_notebook(client, "Polymer Synthesis")
        _create_entry(client, nb["id"], "RAFT polymerisation of styrene")

        results = _search(client, "polymer")
        titles = [r["title"] for r in results]
        assert "Polymer Synthesis" in titles

    def test_owner_sees_own_entries_by_content(self, client):
        _register(client)
        _login(client)
        nb = _create_notebook(client, "NB")
        _create_entry(
            client,
            nb["id"],
            "Blank Title",
            content_blocks=_blocknote_text("The catalyst was palladium on carbon"),
        )

        results = _search(client, "palladium")
        assert len(results) >= 1
        assert any(r["title"] == "Blank Title" for r in results)

    def test_other_user_cannot_see_unshared_notebooks(self, client):
        # Alice creates a notebook
        alice = _register(client, "Alice", "alice@example.com")
        _login(client, "alice@example.com")
        _create_notebook(client, "Alice Secret Notebook")
        _create_entry(
            client,
            client.get("/api/notebooks/").json()[0]["id"],
            "Secret Experiment",
            content_blocks=_blocknote_text("Top secret catalyst data"),
        )
        client.cookies.clear()

        # Bob registers and searches — should find nothing of Alice's
        _register(client, "Bob", "bob@example.com")
        _login(client, "bob@example.com")

        results = _search(client, "secret")
        assert len(results) == 0

        results = _search(client, "catalyst")
        assert len(results) == 0

        results = _search(client, "Alice")
        assert len(results) == 0

    def test_shared_notebook_visible_to_recipient(self, client):
        # Alice creates and shares a notebook with Bob
        alice = _register(client, "Alice", "alice@example.com")
        _login(client, "alice@example.com")
        nb = _create_notebook(client, "Shared Research")
        _create_entry(
            client,
            nb["id"],
            "Enzyme Kinetics",
            content_blocks=_blocknote_text("Michaelis-Menten analysis of lipase"),
            tags=["enzymology"],
        )
        client.cookies.clear()

        # Bob registers
        bob = _register(client, "Bob", "bob@example.com")
        bob_id = bob["id"]
        client.cookies.clear()

        # Alice shares with Bob
        _login(client, "alice@example.com")
        _share_notebook(client, nb["id"], bob_id, "read")
        client.cookies.clear()

        # Bob can now find the shared content
        _login(client, "bob@example.com")
        results = _search(client, "enzyme")
        assert len(results) >= 1
        titles = [r["title"] for r in results]
        assert "Enzyme Kinetics" in titles

    def test_shared_notebook_content_searchable(self, client):
        """Bob can find shared entries by searching their content."""
        alice = _register(client, "Alice", "alice@example.com")
        _login(client, "alice@example.com")
        nb = _create_notebook(client, "NB")
        _create_entry(
            client,
            nb["id"],
            "Titration",
            content_blocks=_blocknote_text("Used phenolphthalein as the indicator"),
        )
        client.cookies.clear()

        bob = _register(client, "Bob", "bob@example.com")
        bob_id = bob["id"]
        client.cookies.clear()

        _login(client, "alice@example.com")
        _share_notebook(client, nb["id"], bob_id, "read")
        client.cookies.clear()

        _login(client, "bob@example.com")
        results = _search(client, "phenolphthalein")
        assert len(results) >= 1
        assert results[0]["title"] == "Titration"

    def test_unshared_after_revoke_not_visible(self, client):
        """After revoking access, Bob can no longer find the notebook."""
        alice = _register(client, "Alice", "alice@example.com")
        _login(client, "alice@example.com")
        nb = _create_notebook(client, "Temp Shared")
        _create_entry(client, nb["id"], "Temporary Entry")
        client.cookies.clear()

        bob = _register(client, "Bob", "bob@example.com")
        bob_id = bob["id"]
        client.cookies.clear()

        # Alice shares
        _login(client, "alice@example.com")
        perm = _share_notebook(client, nb["id"], bob_id, "read")
        client.cookies.clear()

        # Bob can see it
        _login(client, "bob@example.com")
        assert len(_search(client, "Temporary")) >= 1
        client.cookies.clear()

        # Alice revokes
        _login(client, "alice@example.com")
        resp = client.delete(f"/api/permissions/{perm['id']}")
        assert resp.status_code == 204
        client.cookies.clear()

        # Bob can no longer see it
        _login(client, "bob@example.com")
        assert len(_search(client, "Temporary")) == 0

    def test_multiple_users_isolated(self, client):
        """Three users: each sees only their own + shared content."""
        # Alice
        _register(client, "Alice", "alice@example.com")
        _login(client, "alice@example.com")
        nb_alice = _create_notebook(client, "Alice Organics")
        _create_entry(client, nb_alice["id"], "Grignard Reaction")
        client.cookies.clear()

        # Bob
        bob = _register(client, "Bob", "bob@example.com")
        _login(client, "bob@example.com")
        nb_bob = _create_notebook(client, "Bob Inorganics")
        _create_entry(client, nb_bob["id"], "Crystal Field Theory")
        client.cookies.clear()

        # Carol
        _register(client, "Carol", "carol@example.com")
        _login(client, "carol@example.com")
        nb_carol = _create_notebook(client, "Carol Biochemistry")
        _create_entry(client, nb_carol["id"], "Protein Folding")
        client.cookies.clear()

        # Alice shares her notebook with Bob
        _login(client, "alice@example.com")
        _share_notebook(client, nb_alice["id"], bob["id"], "read")
        client.cookies.clear()

        # Alice sees only her own
        _login(client, "alice@example.com")
        results = _search(client, "reaction")
        titles = {r["title"] for r in results}
        assert "Grignard Reaction" in titles
        assert "Crystal Field Theory" not in titles
        assert "Protein Folding" not in titles
        client.cookies.clear()

        # Bob sees his own + Alice's shared notebook
        _login(client, "bob@example.com")
        results = _search(client, "theory")
        titles = {r["title"] for r in results}
        assert "Crystal Field Theory" in titles

        results = _search(client, "Grignard")
        titles = {r["title"] for r in results}
        assert "Grignard Reaction" in titles

        results = _search(client, "Protein")
        assert len(results) == 0
        client.cookies.clear()

        # Carol sees only her own
        _login(client, "carol@example.com")
        results = _search(client, "Folding")
        titles = {r["title"] for r in results}
        assert "Protein Folding" in titles

        results = _search(client, "Grignard")
        assert len(results) == 0

        results = _search(client, "Crystal")
        assert len(results) == 0


class TestSearchResults:
    """Test result quality, ranking, snippets."""

    def test_title_match_ranks_higher_than_content(self, client):
        _register(client)
        _login(client)
        nb = _create_notebook(client, "NB")
        # Entry whose title matches
        _create_entry(client, nb["id"], "Catalysis Overview")
        # Entry whose content matches but title doesn't
        _create_entry(
            client,
            nb["id"],
            "Random Notes",
            content_blocks=_blocknote_text("Some notes on catalysis mechanisms"),
        )

        results = _search(client, "catalysis")
        assert len(results) >= 2
        # The title match should come first
        assert results[0]["title"] == "Catalysis Overview"

    def test_search_by_tags(self, client):
        _register(client)
        _login(client)
        nb = _create_notebook(client, "NB")
        _create_entry(client, nb["id"], "Entry A", tags=["spectroscopy", "NMR"])

        results = _search(client, "spectroscopy")
        assert len(results) >= 1
        assert results[0]["title"] == "Entry A"

    def test_fuzzy_match(self, client):
        """Misspelled queries should still match via fuzzy scoring."""
        _register(client)
        _login(client)
        nb = _create_notebook(client, "NB")
        _create_entry(client, nb["id"], "Chromatography Results")

        # Misspelled query
        results = _search(client, "cromatography")
        assert any(r["title"] == "Chromatography Results" for r in results)

    def test_result_includes_notebook_info(self, client):
        _register(client)
        _login(client)
        nb = _create_notebook(client, "My Lab Book")
        _create_entry(client, nb["id"], "Experiment 42")

        results = _search(client, "Experiment 42")
        entry_results = [r for r in results if r["type"] == "entry"]
        assert len(entry_results) >= 1
        assert entry_results[0]["notebook_id"] == nb["id"]
        assert entry_results[0]["notebook_title"] == "My Lab Book"

    def test_notebook_matches_returned(self, client):
        _register(client)
        _login(client)
        _create_notebook(client, "Quantum Chemistry Calculations")

        results = _search(client, "quantum chemistry")
        nb_results = [r for r in results if r["type"] == "notebook"]
        assert len(nb_results) >= 1
        assert nb_results[0]["title"] == "Quantum Chemistry Calculations"

    def test_snippet_contains_matched_text(self, client):
        _register(client)
        _login(client)
        nb = _create_notebook(client, "NB")
        _create_entry(
            client,
            nb["id"],
            "Entry",
            content_blocks=_blocknote_text(
                "The reaction was performed at reflux temperature using toluene as solvent"
            ),
        )

        results = _search(client, "reflux")
        assert len(results) >= 1
        assert "reflux" in results[0]["snippet"].lower()

    def test_no_results_for_unrelated_query(self, client):
        _register(client)
        _login(client)
        nb = _create_notebook(client, "Organic Chemistry")
        _create_entry(client, nb["id"], "Aldol Condensation")

        results = _search(client, "astrophysics")
        assert len(results) == 0

    def test_content_with_nested_blocks(self, client):
        """Entries with nested children blocks should be searchable."""
        _register(client)
        _login(client)
        nb = _create_notebook(client, "NB")
        nested_blocks = [
            {
                "id": "b1",
                "type": "bulletListItem",
                "content": [{"type": "text", "text": "First item"}],
                "children": [
                    {
                        "id": "b1c1",
                        "type": "bulletListItem",
                        "content": [{"type": "text", "text": "Nested ferrocene derivative"}],
                        "children": [],
                    }
                ],
            }
        ]
        _create_entry(client, nb["id"], "List Entry", content_blocks=nested_blocks)

        results = _search(client, "ferrocene")
        assert len(results) >= 1
        assert results[0]["title"] == "List Entry"
