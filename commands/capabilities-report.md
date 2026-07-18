---
description: Inventory this machine's Claude Code capabilities — skills, agents, plugins, MCP servers, hooks, and built-in tools across user/project/plugin scopes — as a typed JSON catalog and an HTML environment report.
allowed-tools: Bash, Read
---

Build the environment report and summarize it. The scan covers every scope root
(user, project, plugin), installed plugins with per-component token cost,
connected MCP servers and their tool schemas, indexed skills, and built-in
tools. Distinct from `/context-cartographer:map-context`, which budgets one
repo's context surface — this maps what the whole machine/session has.

Run exactly this:

```bash
if [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
  echo "CLAUDE_PLUGIN_ROOT is unset — this command must run from an installed plugin." >&2
  exit 1
fi
PLUGIN="$CLAUDE_PLUGIN_ROOT"
# Bearer auth for the GitHub MCP server, when gh is logged in — the host binding below is
# enforced: the token is attached only if the server's own url resolves to that exact host,
# so a same-named server elsewhere can never receive it. Neither printed nor stored.
if TOKEN=$(gh auth token 2>/dev/null) && [ -n "$TOKEN" ]; then
  export GH_TOKEN="$TOKEN"
  export CAPABILITIES_DISCOVERY_MCP_BEARER_ENV='{"github": {"env": "GH_TOKEN", "host": "api.githubcopilot.com"}}'
fi
uv run --project "$PLUGIN" capabilities-discovery
```

It prints the two output paths (JSON snapshot + HTML report, under
`~/.claude/capabilities-discovery/` by default). Then:

- Read the JSON snapshot and report the counts per catalog kind (skills, tools,
  MCP servers, plugins), the scan roots used, and anything anomalous (servers
  that failed to connect, empty scopes).
- Point the user at the HTML report path for the full browsable view.

Notes:
- MCP tool inventories are served from a 12-hour cache; a fresh probe happens in
  the background when the cache is stale.
- HTTP MCP servers needing auth: `mcp_bearer_env` in settings maps a server name
  to `{env, host}` — an env var holding a bearer token, and the exact host the
  server's url must resolve to before the token is attached (non-interactive).
  `--oauth` additionally runs the browser OAuth flow for servers with a
  pre-registered, host-bound client in `mcp_oauth_clients`; never pass it here
  — this command must stay non-interactive.
- The JSON round-trips through `EnvironmentReport.model_validate_json` for any
  downstream typed consumer.
