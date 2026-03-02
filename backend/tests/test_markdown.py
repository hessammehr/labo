"""Tests for app.services.markdown — BlockNote blocks → Markdown."""

from app.services.markdown import blocks_to_markdown


def _text(t: str, **styles) -> dict:
    return {"type": "text", "text": t, "styles": styles}


def _link(href: str, text: str) -> dict:
    return {"type": "link", "href": href, "content": [_text(text)]}


def _block(btype: str, content=None, props=None, children=None) -> dict:
    return {
        "type": btype,
        "props": props or {},
        "content": content or [],
        "children": children or [],
    }


class TestInlineStyles:
    def test_plain_text(self):
        blocks = [_block("paragraph", [_text("hello")])]
        assert "hello" in blocks_to_markdown(blocks)

    def test_bold(self):
        blocks = [_block("paragraph", [_text("strong", bold=True)])]
        assert "**strong**" in blocks_to_markdown(blocks)

    def test_italic(self):
        blocks = [_block("paragraph", [_text("em", italic=True)])]
        assert "*em*" in blocks_to_markdown(blocks)

    def test_bold_italic(self):
        blocks = [_block("paragraph", [_text("both", bold=True, italic=True)])]
        assert "***both***" in blocks_to_markdown(blocks)

    def test_code(self):
        blocks = [_block("paragraph", [_text("x = 1", code=True)])]
        assert "`x = 1`" in blocks_to_markdown(blocks)

    def test_strikethrough(self):
        blocks = [_block("paragraph", [_text("nope", strike=True)])]
        assert "~~nope~~" in blocks_to_markdown(blocks)

    def test_underline(self):
        blocks = [_block("paragraph", [_text("u", underline=True)])]
        assert "<u>u</u>" in blocks_to_markdown(blocks)

    def test_link(self):
        blocks = [_block("paragraph", [_link("https://x.com", "click")])]
        assert "[click](https://x.com)" in blocks_to_markdown(blocks)


class TestBlockTypes:
    def test_heading_levels(self):
        for level in (1, 2, 3):
            blocks = [_block("heading", [_text("Title")], props={"level": level})]
            md = blocks_to_markdown(blocks)
            assert md.startswith("#" * level + " Title")

    def test_bullet_list(self):
        blocks = [
            _block("bulletListItem", [_text("one")]),
            _block("bulletListItem", [_text("two")]),
        ]
        md = blocks_to_markdown(blocks)
        assert "- one" in md
        assert "- two" in md

    def test_numbered_list(self):
        blocks = [
            _block("numberedListItem", [_text("first")]),
            _block("numberedListItem", [_text("second")]),
        ]
        md = blocks_to_markdown(blocks)
        assert "1. first" in md
        assert "2. second" in md

    def test_numbered_list_counter_resets(self):
        blocks = [
            _block("numberedListItem", [_text("a")]),
            _block("paragraph", [_text("break")]),
            _block("numberedListItem", [_text("b")]),
        ]
        md = blocks_to_markdown(blocks)
        # Second run should restart at 1
        lines = md.strip().split("\n")
        numbered = [l for l in lines if l and l[0].isdigit()]
        assert numbered[0].startswith("1.")
        assert numbered[1].startswith("1.")

    def test_check_list(self):
        blocks = [
            _block("checkListItem", [_text("done")], props={"checked": True}),
            _block("checkListItem", [_text("todo")], props={"checked": False}),
        ]
        md = blocks_to_markdown(blocks)
        assert "- [x] done" in md
        assert "- [ ] todo" in md

    def test_quote(self):
        blocks = [_block("quote", [_text("wise words")])]
        assert "> wise words" in blocks_to_markdown(blocks)

    def test_code_block(self):
        blocks = [_block("codeBlock", [_text("print('hi')")], props={"language": "python"})]
        md = blocks_to_markdown(blocks)
        assert "```python" in md
        assert "print('hi')" in md
        assert "```" in md

    def test_divider(self):
        blocks = [_block("divider")]
        assert "---" in blocks_to_markdown(blocks)

    def test_image(self):
        blocks = [_block("image", props={"url": "http://img.png", "name": "photo", "caption": "A photo"})]
        md = blocks_to_markdown(blocks)
        assert "![photo](http://img.png)" in md
        assert "*A photo*" in md

    def test_file(self):
        blocks = [_block("file", props={"url": "http://f.zip", "name": "data.zip"})]
        md = blocks_to_markdown(blocks)
        assert "[data.zip](http://f.zip)" in md


class TestTable:
    def test_simple_table(self):
        blocks = [
            {
                "type": "table",
                "props": {},
                "content": {
                    "type": "tableContent",
                    "rows": [
                        {"cells": [[_text("A")], [_text("B")]]},
                        {"cells": [[_text("1")], [_text("2")]]},
                    ],
                },
                "children": [],
            }
        ]
        md = blocks_to_markdown(blocks)
        assert "| A | B |" in md
        assert "| --- | --- |" in md
        assert "| 1 | 2 |" in md


class TestNesting:
    def test_nested_bullets(self):
        blocks = [
            _block(
                "bulletListItem",
                [_text("parent")],
                children=[_block("bulletListItem", [_text("child")])],
            ),
        ]
        md = blocks_to_markdown(blocks)
        assert "- parent" in md
        assert "    - child" in md


class TestTitle:
    def test_title_prepended(self):
        blocks = [_block("paragraph", [_text("body")])]
        md = blocks_to_markdown(blocks, title="My Entry")
        lines = md.split("\n")
        assert lines[0] == "# My Entry"

    def test_no_title(self):
        blocks = [_block("paragraph", [_text("body")])]
        md = blocks_to_markdown(blocks)
        assert not md.startswith("#")


class TestEmpty:
    def test_empty_blocks(self):
        md = blocks_to_markdown([])
        assert md == ""

    def test_empty_paragraph(self):
        blocks = [_block("paragraph", [])]
        md = blocks_to_markdown(blocks)
        assert md.strip() == ""
