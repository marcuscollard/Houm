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

            users = await session.call_tool("list_users", {"limit": 2, "offset": 0})
            print("list_users:\n", _format_result(users))

            user = await session.call_tool("get_user", {"user_id": "user_001"})
            print("\nget_user:\n", _format_result(user))

            by_email = await session.call_tool(
                "get_user_by_email", {"email": "sam.berg@example.com"}
            )
            print("\nget_user_by_email:\n", _format_result(by_email))


if __name__ == "__main__":
    asyncio.run(main())
