from __future__ import annotations

import pytest
from pydantic import ValidationError

from capabilities_discovery.hooks import (
    EVENT_HANDLER_TYPES,
    AgentHook,
    CommandHook,
    HandlerType,
    HookAdapter,
    HookConfig,
    HookEvent,
    HttpHook,
    McpToolHook,
    PromptHook,
)

# One representative wire payload per type, using the real camelCase JSON keys.
WIRE: dict[str, dict[str, object]] = {
    "command": {
        "type": "command",
        "command": "./run-tests.sh",
        "async": True,
        "asyncRewake": False,
        "shell": "bash",
        "timeout": 120,
        "if": "Bash(rm *)",
        "statusMessage": "go",
        "once": True,
    },
    "http": {
        "type": "http",
        "url": "http://localhost:8080/h",
        "headers": {"Authorization": "Bearer $T"},
        "allowedEnvVars": ["T"],
    },
    "mcp_tool": {
        "type": "mcp_tool",
        "server": "my_server",
        "tool": "security_scan",
        "input": {"file_path": "${tool_input.file_path}"},
    },
    "prompt": {
        "type": "prompt",
        "prompt": "p $ARGUMENTS",
        "model": "haiku",
        "continueOnBlock": True,
    },
    "agent": {"type": "agent", "prompt": "a $ARGUMENTS", "timeout": 120},
}
EXPECTED: dict[str, type] = {
    "command": CommandHook,
    "http": HttpHook,
    "mcp_tool": McpToolHook,
    "prompt": PromptHook,
    "agent": AgentHook,
}


@pytest.mark.parametrize("kind", list(WIRE))
def test_dispatch_and_round_trip(kind: str) -> None:
    obj = HookAdapter.validate_python(WIRE[kind])
    assert type(obj) is EXPECTED[kind]
    dumped = obj.model_dump(mode="json")  # JSON mode -> camelCase aliases, enums as strings
    assert HookAdapter.validate_python(dumped) == obj
    for wire_key in WIRE[kind]:  # every key we fed in survives the dump under its wire name
        assert wire_key in dumped


def test_command_keyword_aliases_emit_wire_names() -> None:
    dumped = HookAdapter.validate_python(WIRE["command"]).model_dump(mode="json")
    assert dumped["async"] is True  # `run_async` field -> `async` key
    assert dumped["asyncRewake"] is False
    assert dumped["if"] == "Bash(rm *)"  # `condition` field -> `if` key
    assert dumped["statusMessage"] == "go"


def test_snake_case_field_names_also_accepted() -> None:
    obj = CommandHook.model_validate({"command": "x", "run_async": True, "condition": "Edit(*.ts)"})
    assert obj.run_async is True
    assert obj.condition == "Edit(*.ts)"


def test_async_rewake_forces_async() -> None:
    # asyncRewake implies async; `async` left unset must normalize to run_async=True
    obj = CommandHook.model_validate({"command": "x", "asyncRewake": True})
    assert obj.async_rewake is True
    assert obj.run_async is True
    assert obj.model_dump(mode="json")["async"] is True


def test_condition_accepted_on_every_variant() -> None:
    for raw in WIRE.values():
        obj = HookAdapter.validate_python({**raw, "if": "Write(*.sql)"})
        assert obj.condition == "Write(*.sql)"


def test_unknown_keys_tolerated_on_ingest() -> None:
    # A field a newer Claude Code adds must not break parsing — it is dropped, not rejected.
    obj = HookAdapter.validate_python({"type": "command", "command": "x", "bogusFutureField": 1})
    assert isinstance(obj, CommandHook)
    assert "bogusFutureField" not in obj.model_dump(mode="json")


def test_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        HookAdapter.validate_python({"type": "shell", "command": "x"})


def test_llm_hooks_require_prompt() -> None:
    for kind in ("prompt", "agent"):
        with pytest.raises(ValidationError):
            HookAdapter.validate_python({"type": kind})


def test_invalid_condition_rule_rejected() -> None:
    with pytest.raises(ValidationError):
        HookAdapter.validate_python({"type": "command", "command": "x", "if": "(bad"})


def test_http_url_must_be_http() -> None:
    with pytest.raises(ValidationError):
        HookAdapter.validate_python({"type": "http", "url": "ftp://host/x"})


def test_timeout_allows_values_above_the_default() -> None:
    # 600 is the command default, not a maximum; values above it are valid (docs set no max).
    obj = HookAdapter.validate_python({"type": "command", "command": "x", "timeout": 900})
    assert isinstance(obj, CommandHook)
    assert obj.timeout == 900


def test_timeout_absurd_value_rejected() -> None:
    with pytest.raises(ValidationError):
        HookAdapter.validate_python({"type": "command", "command": "x", "timeout": 86_401})


_ALL_HANDLER_TYPES: tuple[HandlerType, ...] = ("command", "http", "mcp_tool", "prompt", "agent")


@pytest.mark.parametrize("event", list(HookEvent))
def test_event_handler_matrix_is_enforced(event: HookEvent) -> None:
    # exercises EVENT_HANDLER_TYPES and HookConfig._enforce_event_support for every event against
    # every handler type — a wrong tier assignment or a dropped validator loop would otherwise
    # pass every other test while silently accepting (or rejecting) the wrong handlers
    allowed = EVENT_HANDLER_TYPES[event]
    for handler_type in _ALL_HANDLER_TYPES:
        payload = {event.value: [{"hooks": [WIRE[handler_type]]}]}
        if handler_type in allowed:
            config = HookConfig.model_validate(payload)
            assert config.root[event][0].hooks[0].type == handler_type
        else:
            with pytest.raises(ValidationError):
                HookConfig.model_validate(payload)
