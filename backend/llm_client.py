import json
import os
import sys
import time
from typing import Any

from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8787/sse")
ALLOWED_TOOLS = [
    "geo_nearby",
    "geo_distance",
    "listings_by_bbox",
    "listings_search",
    "listings_get",
    "search_estimate",
    "attributes_list",
]


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _format_tool_call(item: Any) -> str:
    name = _get_attr(item, "name", "unknown_tool")
    arguments = _get_attr(item, "arguments", {})
    if isinstance(arguments, str):
        return f"{name} {arguments}"
    return f"{name} {json.dumps(arguments)}"


def _log_tool_calls(response: Any) -> None:
    outputs = _get_attr(response, "output", [])
    tool_calls = []
    for item in outputs:
        item_type = _get_attr(item, "type", "")
        if "tool" in item_type:
            tool_calls.append(_format_tool_call(item))
    if tool_calls:
        print("\n[tools]", file=sys.stderr)
        for call in tool_calls:
            print(f"- {call}", file=sys.stderr)


def _stream_response(client: OpenAI, prompt: str) -> Any:
    with client.responses.stream(
        model=MODEL,
        input=prompt,
        tools=[
            {
                "type": "mcp",
                "server_label": "houm-geo",
                "server_url": MCP_SERVER_URL,
                "require_approval": "never",
                "allowed_tools": ALLOWED_TOOLS,
            }
        ],
    ) as stream:
        for event in stream:
            event_type = _get_attr(event, "type", "")
            if event_type == "response.output_text.delta":
                sys.stdout.write(_get_attr(event, "delta", ""))
                sys.stdout.flush()
            elif "tool" in event_type:
                tool_name = _get_attr(event, "name", "")
                if tool_name:
                    print(f"\n[tool] {tool_name}", file=sys.stderr)
        response = stream.get_final_response()
    print()
    return response


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Missing OPENAI_API_KEY environment variable.")
    client = OpenAI(api_key=api_key)
    prompt = "Find parks near Vasagatan 1, Stockholm."
    start = time.time()
    response = _stream_response(client, prompt)
    _log_tool_calls(response)
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.2f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
