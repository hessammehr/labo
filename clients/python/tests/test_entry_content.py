"""Tests for Resource.read_markdown(), read_blocks(), write_blocks(), rename()."""

import json

from pytest_httpserver import HTTPServer

from labo import Resource


def _resource(httpserver: HTTPServer) -> Resource:
    return Resource(httpserver.url_for(""), "test-token")


class TestReadMarkdown:
    def test_read_markdown(self, httpserver: HTTPServer):
        httpserver.expect_request(
            "/api/v1/files/My Entry",
            method="GET",
            query_string="content=markdown",
        ).respond_with_data("# My Entry\n\nHello\n", content_type="text/markdown")

        entry = _resource(httpserver) / "My Entry"
        assert entry.read_markdown() == "# My Entry\n\nHello\n"


class TestReadBlocks:
    def test_read_blocks(self, httpserver: HTTPServer):
        payload = {"title": "My Entry", "blocks": [{"type": "paragraph", "content": []}]}
        httpserver.expect_request(
            "/api/v1/files/My Entry",
            method="GET",
            query_string="content=blocks",
        ).respond_with_json(payload)

        entry = _resource(httpserver) / "My Entry"
        assert entry.read_blocks() == [{"type": "paragraph", "content": []}]


class TestWriteBlocks:
    def test_write_blocks(self, httpserver: HTTPServer):
        blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "Hi"}]}]
        httpserver.expect_request(
            "/api/v1/files/My Entry",
            method="PUT",
            query_string="content=blocks",
            data=json.dumps({"blocks": blocks}),
        ).respond_with_json({"status": "updated"})

        entry = _resource(httpserver) / "My Entry"
        entry.write_blocks(blocks)  # should not raise


class TestRename:
    def test_rename_entry(self, httpserver: HTTPServer):
        httpserver.expect_request(
            "/api/v1/files/Old Name",
            method="PATCH",
            data=json.dumps({"target": "New Name"}),
        ).respond_with_json({"path": "New Name", "status": "renamed"})

        entry = _resource(httpserver) / "Old Name"
        new_entry = entry.rename("New Name")

        assert str(new_entry) == "New Name"
        assert new_entry.name == "New Name"
        # Original is unchanged
        assert str(entry) == "Old Name"

    def test_move_attachment(self, httpserver: HTTPServer):
        httpserver.expect_request(
            "/api/v1/files/Entry1/data.csv",
            method="PATCH",
            data=json.dumps({"target": "Entry2/data.csv"}),
        ).respond_with_json({"path": "Entry2/data.csv", "status": "renamed"})

        f = _resource(httpserver) / "Entry1" / "data.csv"
        new_f = f.rename("Entry2/data.csv")

        assert str(new_f) == "Entry2/data.csv"
        assert new_f.name == "data.csv"
        assert str(new_f.parent) == "Entry2"
