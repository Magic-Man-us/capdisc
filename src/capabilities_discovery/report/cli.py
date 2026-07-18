"""`capabilities-discovery` / `python -m capabilities_discovery.report` entry point."""

from __future__ import annotations

import argparse
import sys

from ..settings import get_settings
from .harvest import REPORT_HTML_NAME, REPORT_JSON_NAME, build_report, write_report

_DESCRIPTION = (
    "Scan this machine's Claude Code capabilities — skills, built-in tools, plugins, and "
    "connected MCP servers — and write a JSON snapshot and an HTML report to the default paths."
)


def main() -> None:
    """Build the report against this machine and write both files to the default paths."""
    parser = argparse.ArgumentParser(prog="capabilities-discovery", description=_DESCRIPTION)
    parser.add_argument(
        "--oauth",
        action="store_true",
        help="allow the interactive OAuth flow (browser) for HTTP MCP servers with a "
        "pre-registered client in settings; forces a fresh MCP harvest",
    )
    args = parser.parse_args()
    write_report(build_report(oauth=args.oauth))
    report_dir = get_settings().report_dir
    sys.stdout.write(
        f"wrote {report_dir / REPORT_JSON_NAME}\nwrote {report_dir / REPORT_HTML_NAME}\n"
    )


if __name__ == "__main__":
    main()
