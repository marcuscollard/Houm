from __future__ import annotations

import argparse
import asyncio
import os
import sys

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

try:
    from backend import settings
except ImportError:  # pragma: no cover - fallback for direct script runs
    import settings


def _server_params(server_path: str) -> dict[str, object]:
    return {
        "command": sys.executable,
        "args": [server_path],
    }


def _agent_used_tool(result) -> bool:
    def _scan(value) -> bool:
        if isinstance(value, dict):
            item_type = str(value.get("type", ""))
            if "tool" in item_type:
                return True
            if "tool_name" in value or (value.get("name") and "arguments" in value):
                return True
            return any(_scan(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return any(_scan(v) for v in value)
        item_type = getattr(value, "type", "")
        if isinstance(item_type, str) and "tool" in item_type:
            return True
        if hasattr(value, "name") and hasattr(value, "arguments"):
            return True
        return False

    for attr in ("new_items", "items", "output", "events", "trace"):
        if _scan(getattr(result, attr, None)):
            return True
    return False


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Houm MCP via Agents SDK.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Find parks near Vasagatan 1, Stockholm.",
        help="Prompt to send to the agent.",
    )
    parser.add_argument(
        "--server-path",
        default=os.path.join(os.path.dirname(__file__), "server.py"),
        help="Path to the MCP server entrypoint.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", ""),
        help="Override the OpenAI model name.",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY (check .env or environment).", file=sys.stderr)
        return 1

    async with MCPServerStdio(
        name="houm_mcp",
        params=_server_params(args.server_path),
    ) as mcp_server:
        agent_kwargs = {
            "name": "SearchAgent",
            "instructions": (
                "Use MCP tools to search listings, compute distances, and summarize results."
            ),
        }
        if args.model:
            agent_kwargs["model"] = args.model
        try:
            agent = Agent(**agent_kwargs, mcp_servers=[mcp_server])
        except TypeError:
            agent = Agent(**agent_kwargs)
        try:
            result = await Runner.run(
                agent,
                args.prompt,
                tool_choice="required",
                mcp_servers=[mcp_server],
            )
        except TypeError:
            try:
                result = await Runner.run(agent, args.prompt, mcp_servers=[mcp_server])
            except TypeError:
                result = await Runner.run(agent, args.prompt)
        print(result.final_output)
        if not _agent_used_tool(result):
            print("Warning: no tool calls detected in agent output.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
