from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("houm-users")


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    email: str
    full_name: str
    location: str
    status: str
    created_at: str
    last_login_at: str


class UserStore:
    def __init__(self) -> None:
        self._users = self._seed_users()

    def list_users(self, limit: int, offset: int) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        return [asdict(user) for user in self._users[offset : offset + limit]]

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        for user in self._users:
            if user.user_id == user_id:
                return asdict(user)
        return None

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        normalized = email.strip().lower()
        for user in self._users:
            if user.email.lower() == normalized:
                return asdict(user)
        return None

    @staticmethod
    def _seed_users() -> list[UserProfile]:
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        return [
            UserProfile(
                user_id="user_001",
                email="alex.morgan@example.com",
                full_name="Alex Morgan",
                location="Stockholm, SE",
                status="active",
                created_at=now,
                last_login_at=now,
            ),
            UserProfile(
                user_id="user_002",
                email="sam.berg@example.com",
                full_name="Sam Berg",
                location="Uppsala, SE",
                status="active",
                created_at=now,
                last_login_at=now,
            ),
            UserProfile(
                user_id="user_003",
                email="jo.holm@example.com",
                full_name="Jo Holm",
                location="Gothenburg, SE",
                status="invited",
                created_at=now,
                last_login_at=now,
            ),
        ]


store = UserStore()


@mcp.tool()
async def list_users(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    """Return a paginated list of users."""
    users = store.list_users(limit, offset)
    return {
        "count": len(users),
        "limit": limit,
        "offset": offset,
        "users": users,
    }


@mcp.tool()
async def get_user(user_id: str) -> dict[str, Any]:
    """Return a single user by id."""
    user = store.get_user(user_id)
    if not user:
        return {"error": "user_not_found", "user_id": user_id}
    return user


@mcp.tool()
async def get_user_by_email(email: str) -> dict[str, Any]:
    """Return a single user by email."""
    user = store.find_by_email(email)
    if not user:
        return {"error": "user_not_found", "email": email}
    return user


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8787"))
        mcp.run(transport="sse", host=host, port=port)
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
