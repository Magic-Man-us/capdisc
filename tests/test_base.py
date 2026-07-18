from __future__ import annotations

from pydantic.fields import FieldInfo

from capabilities_discovery.base import humanize_field_title

_INFO = FieldInfo()


def test_humanize_snake_case() -> None:
    assert humanize_field_title("status_message", _INFO) == "Status message"


def test_humanize_camel_case() -> None:
    assert humanize_field_title("allowedEnvVars", _INFO) == "Allowed env vars"


def test_humanize_kebab_case() -> None:
    assert humanize_field_title("argument-hint", _INFO) == "Argument hint"


def test_humanize_single_word() -> None:
    assert humanize_field_title("shell", _INFO) == "Shell"
