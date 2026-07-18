from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

HookTimeout = Annotated[
    int,
    Field(
        ge=1,
        le=86_400,
        title="Hook timeout",
        description="Seconds the hook may run before it is killed. Defaults vary by type "
        "(command/http/mcp_tool 600, prompt 30, agent 60) and the docs set no maximum, so the "
        "cap is only an absurd-value guard, not a product limit.",
        examples=[30, 120, 600],
    ),
]
ShellCommand = Annotated[
    str,
    Field(
        min_length=1,
        max_length=4000,
        title="Shell command",
        description="Command a command hook runs, or the executable to spawn when `args` is set.",
        examples=["./run-tests.sh"],
    ),
]
ShellArg = Annotated[
    str,
    Field(
        max_length=2000,
        title="Shell argument",
        description="One argument in a command hook's argument vector.",
    ),
]
HookUrl = Annotated[
    str,
    Field(
        pattern=r"^https?://",
        max_length=2000,
        title="Hook URL",
        description="Endpoint an http hook POSTs the event JSON to.",
        examples=["http://localhost:8080/hooks/tool-use"],
    ),
]
HeaderName = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9-]+$",
        max_length=128,
        title="Header name",
        description="Name of an http hook request header.",
        examples=["Authorization"],
    ),
]
HeaderValue = Annotated[
    str,
    Field(
        max_length=2000,
        title="Header value",
        description="Value of an http hook request header; supports `$VAR` interpolation.",
        examples=["Bearer $MY_TOKEN"],
    ),
]
EnvVarName = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        title="Env var",
        description="Name of an environment variable.",
        examples=["MY_TOKEN"],
    ),
]
HookModel = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        title="Hook model",
        description="Model a prompt or agent hook evaluates with; omit for a fast default.",
        examples=["haiku"],
    ),
]
HookPrompt = Annotated[
    str,
    Field(
        min_length=1,
        max_length=8000,
        title="Hook prompt",
        description="Prompt a prompt or agent hook evaluates; `$ARGUMENTS` injects the input JSON.",
        examples=["Verify all unit tests pass. $ARGUMENTS"],
    ),
]
StatusMessage = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        title="Status message",
        description="Text shown while the hook runs.",
    ),
]
HookCondition = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z][A-Za-z0-9_]*(\(.*\))?$",
        max_length=400,
        title="Hook condition",
        description=(
            "A single permission rule narrowing when the handler runs on tool events, e.g. "
            "'Bash(git *)' or 'Edit(*.ts)'; ignored on non-tool events."
        ),
        examples=["Bash(rm *)", "Edit(*.ts)"],
    ),
]
HookMatcherPattern = Annotated[
    str,
    Field(
        max_length=200,
        title="Hook matcher",
        description="Pattern selecting which subjects an event's handlers run for, e.g. "
        "'Write|Edit', 'Bash', or '*' for all; empty also means all.",
        examples=["Write|Edit", "Bash", "*", ""],
    ),
]
RunOnce = Annotated[
    bool,
    Field(
        description="If true, the hook runs once per session, then is removed. Only honored for "
        "hooks declared in skill frontmatter — ignored in settings files and agent frontmatter.",
    ),
]
RunAsync = Annotated[
    bool,
    Field(
        description="If true, a command hook runs in the background without blocking Claude; its "
        "output is delivered on the next conversation turn. Command hooks only.",
    ),
]
AsyncRewake = Annotated[
    bool,
    Field(
        description="If true, a command hook runs in the background and wakes Claude on exit "
        "code 2 (implies async). The hook's stderr — or stdout if stderr is empty — is shown to "
        "Claude as a system reminder, so it can react to a long-running background failure.",
    ),
]


class HookShell(StrEnum):
    """Interpreter a command hook runs under."""

    bash = "bash"
    powershell = "powershell"
