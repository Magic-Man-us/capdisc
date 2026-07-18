from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, RootModel, TypeAdapter, model_validator

from ..base import FrozenWireModel
from ..catalog import McpServerRef, McpToolName
from .types import (
    AsyncRewake,
    EnvVarName,
    HeaderName,
    HeaderValue,
    HookCondition,
    HookMatcherPattern,
    HookModel,
    HookPrompt,
    HookShell,
    HookTimeout,
    HookUrl,
    RunAsync,
    RunOnce,
    ShellArg,
    ShellCommand,
    StatusMessage,
)


class _Handler(FrozenWireModel):
    """Fields every hook handler carries, whatever its `type`."""

    timeout: HookTimeout | None = None
    status_message: StatusMessage | None = None
    once: RunOnce = False
    condition: HookCondition | None = Field(default=None, alias="if")


class CommandHook(_Handler):
    """Runs a shell command, or spawns an executable directly when `args` is set."""

    type: Literal["command"] = "command"
    command: ShellCommand
    args: list[ShellArg] = []
    run_async: RunAsync = Field(default=False, alias="async")
    async_rewake: AsyncRewake = False
    shell: HookShell | None = None

    @model_validator(mode="after")
    def _async_rewake_implies_async(self) -> CommandHook:
        """`asyncRewake` implies `async` (per the hooks docs), so `run_async` stays truthful as
        'runs in background': any hook with `asyncRewake` set is forced async."""
        if self.async_rewake and not self.run_async:
            return self.model_copy(update={"run_async": True})
        return self


class HttpHook(_Handler):
    """POSTs the event JSON to an endpoint and reads the decision from the response body."""

    type: Literal["http"] = "http"
    url: HookUrl
    headers: dict[HeaderName, HeaderValue] = {}
    allowed_env_vars: list[EnvVarName] = []


class McpToolHook(_Handler):
    """Calls a tool on an already-connected MCP server."""

    type: Literal["mcp_tool"] = "mcp_tool"
    server: McpServerRef
    tool: McpToolName
    input: dict[str, JsonValue] = {}


class _LlmHook(_Handler):
    """Shared fields of the LLM-evaluated hooks: a prompt sent to a model for an allow/block
    decision. Prompt and agent hooks differ only in whether that model gets tool access."""

    prompt: HookPrompt
    model: HookModel | None = None


class PromptHook(_LlmHook):
    """Single-turn LLM evaluation that allows or blocks the action."""

    type: Literal["prompt"] = "prompt"
    continue_on_block: bool = False


class AgentHook(_LlmHook):
    """Multi-turn agentic verifier with tool access (experimental)."""

    type: Literal["agent"] = "agent"


HookHandler = Annotated[
    CommandHook | HttpHook | McpToolHook | PromptHook | AgentHook,
    Field(discriminator="type"),
]

HookAdapter: TypeAdapter[HookHandler] = TypeAdapter(HookHandler)

HandlerType = Literal["command", "http", "mcp_tool", "prompt", "agent"]


class HookEvent(StrEnum):
    """An event a hook can fire on. Which handler `type`s an event accepts varies — see
    `EVENT_HANDLER_TYPES`."""

    pre_tool_use = "PreToolUse"
    post_tool_use = "PostToolUse"
    post_tool_use_failure = "PostToolUseFailure"
    post_tool_batch = "PostToolBatch"
    permission_denied = "PermissionDenied"
    permission_request = "PermissionRequest"
    user_prompt_submit = "UserPromptSubmit"
    user_prompt_expansion = "UserPromptExpansion"
    stop = "Stop"
    subagent_stop = "SubagentStop"
    task_completed = "TaskCompleted"
    task_created = "TaskCreated"
    teammate_idle = "TeammateIdle"
    config_change = "ConfigChange"
    cwd_changed = "CwdChanged"
    elicitation = "Elicitation"
    elicitation_result = "ElicitationResult"
    file_changed = "FileChanged"
    instructions_loaded = "InstructionsLoaded"
    notification = "Notification"
    post_compact = "PostCompact"
    pre_compact = "PreCompact"
    session_end = "SessionEnd"
    stop_failure = "StopFailure"
    subagent_start = "SubagentStart"
    worktree_create = "WorktreeCreate"
    worktree_remove = "WorktreeRemove"
    session_start = "SessionStart"
    setup = "Setup"


# Which handler types each event accepts, per the Claude Code hooks docs. Three tiers: all
# five types, the non-LLM three (no prompt/agent), and command+mcp_tool only.
# Source: https://code.claude.com/docs/en/hooks (snapshot verified 2026-06). This mirrors a
# product matrix that shifts between releases — refresh against the docs when events change.
_ALL_TYPES: frozenset[HandlerType] = frozenset(("command", "http", "mcp_tool", "prompt", "agent"))
_NO_LLM_TYPES: frozenset[HandlerType] = frozenset(("command", "http", "mcp_tool"))
_CMD_MCP_TYPES: frozenset[HandlerType] = frozenset(("command", "mcp_tool"))

EVENT_HANDLER_TYPES: dict[HookEvent, frozenset[HandlerType]] = {
    HookEvent.session_start: _CMD_MCP_TYPES,
    HookEvent.setup: _CMD_MCP_TYPES,
    **dict.fromkeys(
        (
            HookEvent.config_change,
            HookEvent.cwd_changed,
            HookEvent.elicitation,
            HookEvent.elicitation_result,
            HookEvent.file_changed,
            HookEvent.instructions_loaded,
            HookEvent.notification,
            HookEvent.post_compact,
            HookEvent.pre_compact,
            HookEvent.session_end,
            HookEvent.stop_failure,
            HookEvent.subagent_start,
            HookEvent.worktree_create,
            HookEvent.worktree_remove,
        ),
        _NO_LLM_TYPES,
    ),
    **dict.fromkeys(
        (
            HookEvent.pre_tool_use,
            HookEvent.post_tool_use,
            HookEvent.post_tool_use_failure,
            HookEvent.post_tool_batch,
            HookEvent.permission_denied,
            HookEvent.permission_request,
            HookEvent.user_prompt_submit,
            HookEvent.user_prompt_expansion,
            HookEvent.stop,
            HookEvent.subagent_stop,
            HookEvent.task_completed,
            HookEvent.task_created,
            HookEvent.teammate_idle,
        ),
        _ALL_TYPES,
    ),
}


class MatcherGroup(FrozenWireModel):
    """One `{matcher, hooks}` entry under an event: the handlers that run for matched subjects."""

    matcher: HookMatcherPattern = "*"
    hooks: list[HookHandler]


class HookConfig(RootModel[dict[HookEvent, list[MatcherGroup]]]):
    """The value of a `hooks` settings key (or a plugin's hooks.json): events mapped to their
    matcher groups. Enforces that each handler `type` is one its event supports."""

    @model_validator(mode="after")
    def _enforce_event_support(self) -> HookConfig:
        """Reject any handler whose `type` its event doesn't accept (per `EVENT_HANDLER_TYPES`)."""
        for event, groups in self.root.items():
            allowed = EVENT_HANDLER_TYPES[event]
            for group in groups:
                for handler in group.hooks:
                    if handler.type not in allowed:
                        raise ValueError(
                            f"{handler.type!r} hook is not supported on {event.value} "
                            f"(allowed: {sorted(allowed)})"
                        )
        return self
