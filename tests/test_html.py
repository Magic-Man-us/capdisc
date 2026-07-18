from __future__ import annotations

from pathlib import Path

import pytest

from capabilities_discovery.html import redact_home, redact_secrets


def test_redact_home_collapses_home_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert redact_home(tmp_path / "project" / ".claude") == "~/project/.claude"


def test_redact_home_leaves_unrelated_paths_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    assert redact_home("/var/other/place") == "/var/other/place"


def test_redact_secrets_scrubs_bearer_token() -> None:
    text = "curl -H 'Authorization: Bearer sk-live-abc123XYZ789' https://hooks.slack.com/services/x"
    redacted = redact_secrets(text)
    assert "sk-live-abc123XYZ789" not in redacted
    assert "[redacted]" in redacted


def test_redact_secrets_scrubs_provider_key_prefixes() -> None:
    assert "ghp_" not in redact_secrets("token: ghp_abcdefghijklmnopqrstuvwxyz0123")
    assert "AKIA" not in redact_secrets("aws key AKIAABCDEFGHIJKLMNOP")


def test_redact_secrets_scrubs_key_value_pairs() -> None:
    redacted = redact_secrets("--token=abcdef0123456789 --verbose")
    assert "abcdef0123456789" not in redacted
    assert "--token=[redacted]" in redacted


def test_redact_secrets_leaves_ordinary_text_alone() -> None:
    text = "npx -y @modelcontextprotocol/server-github --port 8080"
    assert redact_secrets(text) == text
