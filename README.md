# capabilities-discovery

Discovers Claude Code capabilities — skills, agents, plugins, MCP servers, hooks — into typed
Pydantic catalogs and an environment report.

## Install

```bash
uv sync
```

## Library

```python
from pathlib import Path
from capabilities_discovery.discovery import scan_environment
from capabilities_discovery.scope import ScopeRoots

roots = ScopeRoots.discover(start=Path.cwd(), home_dir=Path.home())
catalog = scan_environment(roots)
for entry in catalog.entries:
    ...  # CatalogSkill | CatalogTool | CatalogMcpServer | CatalogPlugin
```

`report.EnvironmentReport` captures the discovery harvest (scan roots, on-disk inventory, skills,
builtin tools, plugins with per-component token cost, MCP servers). `mcp_harvest` and `mcp_catalog`
enumerate connected MCP servers; `plugin_catalog` reads installed plugins; `scope` resolves which
roots to scan.

The package ships `py.typed`.

## Tests

```bash
uv run pytest
uv run mypy src
uv run ruff check .
```
