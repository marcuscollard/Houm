import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = os.path.join(os.path.dirname(__file__), "server.py")


def _format_result(result: Any) -> str:
    content = getattr(result, "content", None)
    if content is None:
        return json.dumps(result, indent=2, default=str)

    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    return "\n".join(parts)


async def main() -> None:
    server_params = StdioServerParameters(command=sys.executable, args=[SERVER_PATH])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            nearby = await session.call_tool(
                "geo_nearby",
                {"address": "Vasagatan 1, Stockholm", "place_type": "park", "limit": 3},
            )
            print("geo.nearby:\n", _format_result(nearby))

            distance = await session.call_tool(
                "geo_distance",
                {"origin": "Stockholm Central Station", "destination": "Skansen"},
            )
            print("\ngeo.distance:\n", _format_result(distance))


if __name__ == "__main__":
    asyncio.run(main())
