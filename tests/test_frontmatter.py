from __future__ import annotations

from capabilities_discovery.frontmatter import read_frontmatter

_EXPECTED = {"name": "foo", "description": "does a thing"}


def test_reads_lf_frontmatter() -> None:
    assert read_frontmatter("---\nname: foo\ndescription: does a thing\n---\nbody") == _EXPECTED


def test_reads_crlf_frontmatter() -> None:
    text = "---\r\nname: foo\r\ndescription: does a thing\r\n---\r\nbody"
    assert read_frontmatter(text) == _EXPECTED


def test_reads_bom_prefixed_frontmatter() -> None:
    text = "\ufeff---\nname: foo\ndescription: does a thing\n---\nbody"
    assert read_frontmatter(text) == _EXPECTED


def test_deeply_nested_yaml_returns_none() -> None:
    # untrusted repo content must skip itself, not blow the stack
    text = "---\nx: " + "[" * 5000 + "]" * 5000 + "\n---\nbody"
    assert read_frontmatter(text) is None


def test_no_frontmatter_returns_none() -> None:
    assert read_frontmatter("just a body\n") is None
