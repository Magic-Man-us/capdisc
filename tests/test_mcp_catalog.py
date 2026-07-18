from __future__ import annotations

from capabilities_discovery.mcp_catalog import parse_mcp_servers

_LIST = """\
claude.ai Postman: https://mcp.postman.com/minimal - ! Needs authentication
claude.ai Supabase: https://mcp.supabase.com/mcp - ✔ Connected
plugin:dq-toolkit:dq: /home/me/dq-toolkit/scripts/dq-mcp  - ✔ Connected
plugin:playwright:playwright: npx @playwright/mcp@latest - ✔ Connected
"""


def test_parses_connected_servers_only() -> None:
    refs = {server.ref for server in parse_mcp_servers(_LIST)}
    assert refs == {"claude-ai-supabase", "plugin-dq-toolkit-dq", "plugin-playwright-playwright"}


def test_drops_unconnected_server() -> None:
    # Postman shows "Needs authentication" — not connected, must be excluded
    assert all("postman" not in server.ref for server in parse_mcp_servers(_LIST))


def test_description_is_derived_from_the_server_name() -> None:
    # name-derived only (no hand-authored notes); recall matches the name tokens
    playwright = next(s for s in parse_mcp_servers(_LIST) if "playwright" in s.ref)
    assert "playwright" in playwright.description.lower()
    assert playwright.tags == []


def test_never_indexes_the_command_or_url() -> None:
    # the command/URL after the name can carry credentials and must not land in any card
    for server in parse_mcp_servers(_LIST):
        blob = server.model_dump_json()
        assert "https://" not in blob
        assert "npx" not in blob
        assert "/home/" not in blob
