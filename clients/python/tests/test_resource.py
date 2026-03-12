"""Unit tests for labo.Resource — path operations (no network needed)."""

from labo import Resource


def test_truediv():
    r = Resource("http://localhost", "tok")
    child = r / "Entry" / "file.csv"
    assert str(child) == "Entry/file.csv"


def test_name():
    r = Resource("http://localhost", "tok", _path="Entry/data.csv")
    assert r.name == "data.csv"


def test_parent():
    r = Resource("http://localhost", "tok", _path="Entry/data.csv")
    assert str(r.parent) == "Entry"
    assert str(r.parent.parent) == "/"


def test_parts():
    r = Resource("http://localhost", "tok", _path="Entry/sub/data.csv")
    assert r.parts == ("Entry", "sub", "data.csv")


def test_suffix_and_stem():
    r = Resource("http://localhost", "tok", _path="Entry/data.tar.gz")
    assert r.suffix == ".gz"
    assert r.stem == "data.tar"


def test_no_suffix():
    r = Resource("http://localhost", "tok", _path="Entry/README")
    assert r.suffix == ""
    assert r.stem == "README"


def test_fspath():
    import os

    r = Resource("http://localhost", "tok", _path="Entry/file.csv")
    assert os.fspath(r) == "Entry/file.csv"


def test_root_name():
    r = Resource("http://localhost", "tok")
    assert r.name == ""
    assert str(r) == "/"
    assert r.parts == ()
