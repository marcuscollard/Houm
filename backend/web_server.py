from __future__ import annotations

import asyncio
import json
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import psycopg2
import psycopg2.extras

try:
    from backend import settings
except ImportError:  # pragma: no cover - fallback for direct script runs
    import settings

BASE_DIR = settings.BASE_DIR


class HoumHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path.startswith("/.env"):
            self.send_error(404)
            return
        if path == "/config":
            key = settings.GOOGLE_MAPS_API_KEY
            body = json.dumps({"googleMapsApiKey": key}).encode("utf-8")
            self.send_response(200 if key else 500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/listings/points":
            self._handle_points(query)
            return
        if path == "/api/profile":
            self._handle_profile_get(query)
            return
        if path == "/api/favorites":
            self._handle_favorites_get(query)
            return
        if path.startswith("/api/listings/"):
            tail = path.split("/api/listings/", 1)[1]
            parts = [p for p in tail.split("/") if p]
            if len(parts) == 2 and parts[1] == "image":
                self._handle_image(parts[0], "main")
                return
            if len(parts) == 3 and parts[1] == "image":
                self._handle_image(parts[0], parts[2])
                return
            if len(parts) == 1:
                self._handle_listing(parts[0])
                return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/assistant":
            self._handle_assistant()
            return
        if path == "/api/profile":
            self._handle_profile_upsert()
            return
        if path == "/api/favorites":
            self._handle_favorites_add()
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/favorites":
            self._handle_favorites_remove()
            return
        self.send_error(404)

    def _db_connect(self):
        if not settings.DATABASE_URL:
            raise RuntimeError("Missing DATABASE_URL")
        return psycopg2.connect(settings.DATABASE_URL)

    def _send_json(self, data, status=200):
        def _default(value):
            try:
                return value.isoformat()
            except AttributeError:
                return str(value)

        body = json.dumps(data, ensure_ascii=False, default=_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _coerce_json(self, value):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode("utf-8")
            except Exception:
                return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _normalize_name(self, value):
        if not isinstance(value, str):
            return None, None
        display_name = value.strip()
        if not display_name:
            return None, None
        return display_name, display_name.casefold()

    def _fetch_favorites(self, conn, user_id):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT hemnet_id FROM houm_favorites WHERE user_id = %s",
                (user_id,),
            )
            return [row[0] for row in cur.fetchall()]

    def _handle_profile_get(self, query):
        name = query.get("name", [""])[0]
        display_name, name_key = self._normalize_name(name)
        if not display_name:
            self._send_json({"error": "missing_name"}, status=400)
            return

        sql = "SELECT * FROM houm_users WHERE name_key = %s LIMIT 1;"
        with self._db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (name_key,))
                row = cur.fetchone()
            if not row:
                self._send_json({"error": "not_found"}, status=404)
                return
            favorites = self._fetch_favorites(conn, row["id"])

        row.pop("name_key", None)
        row["favorites"] = favorites
        self._send_json(row)

    def _handle_profile_upsert(self):
        payload = self._read_json_body() or {}
        display_name, name_key = self._normalize_name(payload.get("name", ""))
        if not display_name:
            self._send_json({"error": "missing_name"}, status=400)
            return

        preferences = payload.get("preferences") or {}
        if not isinstance(preferences, dict):
            preferences = {}

        preference_map = {
            "min_price": "min_price",
            "max_price": "max_price",
            "min_rooms": "min_rooms",
            "max_rooms": "max_rooms",
            "min_area": "min_area",
            "max_area": "max_area",
            "min_year": "min_year",
            "max_year": "max_year",
            "max_monthly_fee": "max_monthly_fee",
            "housing_forms": "housing_forms",
            "tenure": "tenure",
            "municipalities": "municipalities",
            "regions": "regions",
            "districts": "districts",
            "prefer_new_construction": "prefer_new_construction",
            "prefer_upcoming": "prefer_upcoming",
            "max_coast_distance_m": "max_coast_distance_m",
            "max_water_distance_m": "max_water_distance_m",
        }
        json_columns = {
            "housing_forms",
            "tenure",
            "municipalities",
            "regions",
            "districts",
        }

        with self._db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO houm_users (name, name_key)
                    VALUES (%s, %s)
                    ON CONFLICT (name_key)
                    DO UPDATE SET name = EXCLUDED.name, updated_at = NOW()
                    RETURNING *;
                    """,
                    (display_name, name_key),
                )
                row = cur.fetchone()

                updates = []
                values = []
                for key, column in preference_map.items():
                    if key not in preferences:
                        continue
                    value = preferences[key]
                    if column in json_columns:
                        value = psycopg2.extras.Json(value)
                    updates.append(f"{column} = %s")
                    values.append(value)

                if updates:
                    updates.append("updated_at = NOW()")
                    values.append(row["id"])
                    cur.execute(
                        f"""
                        UPDATE houm_users
                        SET {", ".join(updates)}
                        WHERE id = %s
                        RETURNING *;
                        """,
                        values,
                    )
                    row = cur.fetchone()

            favorites = self._fetch_favorites(conn, row["id"])

        row.pop("name_key", None)
        row["favorites"] = favorites
        self._send_json(row)

    def _handle_favorites_get(self, query):
        name = query.get("name", [""])[0]
        display_name, name_key = self._normalize_name(name)
        if not display_name:
            self._send_json({"error": "missing_name"}, status=400)
            return

        sql = "SELECT id FROM houm_users WHERE name_key = %s LIMIT 1;"
        with self._db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (name_key,))
                row = cur.fetchone()
                if not row:
                    self._send_json({"error": "not_found"}, status=404)
                    return
                favorites = self._fetch_favorites(conn, row[0])

        self._send_json({"name": display_name, "favorites": favorites})

    def _handle_favorites_add(self):
        payload = self._read_json_body() or {}
        display_name, name_key = self._normalize_name(payload.get("name", ""))
        hemnet_id = payload.get("hemnet_id")
        if not display_name:
            self._send_json({"error": "missing_name"}, status=400)
            return
        if not isinstance(hemnet_id, int):
            try:
                hemnet_id = int(hemnet_id)
            except Exception:
                self._send_json({"error": "invalid_hemnet_id"}, status=400)
                return

        with self._db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO houm_users (name, name_key)
                    VALUES (%s, %s)
                    ON CONFLICT (name_key)
                    DO UPDATE SET name = EXCLUDED.name, updated_at = NOW()
                    RETURNING id;
                    """,
                    (display_name, name_key),
                )
                user_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO houm_favorites (user_id, hemnet_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                    """,
                    (user_id, hemnet_id),
                )
                favorites = self._fetch_favorites(conn, user_id)

        self._send_json({"name": display_name, "favorites": favorites})

    def _handle_favorites_remove(self):
        payload = self._read_json_body() or {}
        display_name, name_key = self._normalize_name(payload.get("name", ""))
        hemnet_id = payload.get("hemnet_id")
        if not display_name:
            self._send_json({"error": "missing_name"}, status=400)
            return
        if not isinstance(hemnet_id, int):
            try:
                hemnet_id = int(hemnet_id)
            except Exception:
                self._send_json({"error": "invalid_hemnet_id"}, status=400)
                return

        with self._db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM houm_users WHERE name_key = %s LIMIT 1;",
                    (name_key,),
                )
                row = cur.fetchone()
                if not row:
                    self._send_json({"error": "not_found"}, status=404)
                    return
                user_id = row[0]
                cur.execute(
                    "DELETE FROM houm_favorites WHERE user_id = %s AND hemnet_id = %s;",
                    (user_id, hemnet_id),
                )
                favorites = self._fetch_favorites(conn, user_id)

        self._send_json({"name": display_name, "favorites": favorites})

    def _handle_assistant(self):
        payload = self._read_json_body() or {}
        message = payload.get("message", "")
        history = payload.get("history") or []
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        if not isinstance(message, str) or not message.strip():
            self._send_json({"error": "missing_message"}, status=400)
            return
        if not os.getenv("OPENAI_API_KEY"):
            self._send_json({"error": "missing_openai_key"}, status=500)
            return

        prompt = self._build_prompt(history, message.strip(), context)
        try:
            reply = asyncio.run(self._run_agent(prompt))
        except Exception as exc:
            self._send_json({"error": "assistant_failed", "detail": str(exc)}, status=500)
            return
        reply_text, recommended_ids, recommendation_notes = self._parse_assistant_output(
            reply
        )
        self._send_json(
            {
                "reply": reply_text,
                "recommended_ids": recommended_ids,
                "recommendation_notes": recommendation_notes,
            }
        )

    def _agent_instructions_path(self):
        return os.path.join(BASE_DIR, "backend", "agent_instruct.txt")

    def _load_agent_instructions(self):
        default = (
            "You are a Houm assistant. You MUST use MCP tools before answering.\n"
            "Never invent listings. If tools return no data, say so.\n"
            "If tools are unavailable, return JSON with message=TOOL_UNAVAILABLE.\n"
            "Return JSON only, with message, recommended_ids, and recommendation_notes.\n"
            "Keep responses concise and actionable."
        )
        path = self._agent_instructions_path()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
        except FileNotFoundError:
            return default
        except OSError:
            return default
        return content or default

    def _build_prompt(self, history, message, context=None):
        lines = []
        if isinstance(context, dict):
            bbox = context.get("bbox")
            if isinstance(bbox, str) and bbox.strip():
                lines.append(
                    "Map bbox (min_lng,min_lat,max_lng,max_lat): "
                    f"{bbox}. Use listings_by_bbox if relevant."
                )
        if isinstance(history, list):
            for item in history[-6:]:
                role = item.get("role")
                content = item.get("content")
                if role not in ("user", "assistant"):
                    continue
                if not isinstance(content, str):
                    continue
                lines.append(f"{role.title()}: {content.strip()}")
        lines.append(f"User: {message}")
        lines.append("Assistant:")
        return "\n".join(lines)

    def _parse_assistant_output(self, reply: str):
        if not reply:
            return "", [], {}
        try:
            payload = json.loads(reply)
        except Exception:
            return reply, [], {}
        if not isinstance(payload, dict):
            return reply, [], {}
        message = payload.get("message") or payload.get("reply") or ""
        if not isinstance(message, str):
            message = ""
        raw_ids = payload.get("recommended_ids") or []
        recommended_ids = []
        if isinstance(raw_ids, list):
            for item in raw_ids:
                try:
                    recommended_ids.append(int(item))
                except (TypeError, ValueError):
                    continue
        notes_raw = payload.get("recommendation_notes") or {}
        recommendation_notes = {}
        if isinstance(notes_raw, dict):
            for key, value in notes_raw.items():
                try:
                    hemnet_id = int(key)
                except (TypeError, ValueError):
                    continue
                if not isinstance(value, dict):
                    continue
                pros = value.get("pros")
                cons = value.get("cons")
                pros_list = (
                    [item for item in pros if isinstance(item, str)] if isinstance(pros, list) else []
                )
                cons_list = (
                    [item for item in cons if isinstance(item, str)] if isinstance(cons, list) else []
                )
                recommendation_notes[hemnet_id] = {"pros": pros_list, "cons": cons_list}
        return message or reply, recommended_ids, recommendation_notes

    def _agent_used_tool(self, result) -> bool:
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

    async def _run_agent(self, prompt: str) -> str:
        from agents import Agent, Runner
        from agents.mcp import MCPServerStdio

        server_path = os.path.join(BASE_DIR, "backend", "server.py")
        async with MCPServerStdio(
            name="houm_mcp",
            params={"command": sys.executable, "args": [server_path]},
        ) as mcp_server:
            try:
                agent = Agent(
                    name="SearchAgent",
                    instructions=self._load_agent_instructions(),
                    mcp_servers=[mcp_server],
                )
            except TypeError:
                agent = Agent(
                    name="SearchAgent",
                    instructions=self._load_agent_instructions(),
                )
            try:
                result = await Runner.run(
                    agent,
                    prompt,
                    tool_choice="required",
                    mcp_servers=[mcp_server],
                )
            except TypeError:
                try:
                    result = await Runner.run(agent, prompt, mcp_servers=[mcp_server])
                except TypeError:
                    result = await Runner.run(agent, prompt)
            if not self._agent_used_tool(result):
                forced_prompt = (
                    prompt
                    + "\n\nIMPORTANT: You must call at least one MCP tool before "
                    "answering. If you cannot, reply with: TOOL_UNAVAILABLE."
                )
                try:
                    result = await Runner.run(
                        agent,
                        forced_prompt,
                        tool_choice="required",
                        mcp_servers=[mcp_server],
                    )
                except TypeError:
                    try:
                        result = await Runner.run(
                            agent,
                            forced_prompt,
                            mcp_servers=[mcp_server],
                        )
                    except TypeError:
                        result = await Runner.run(agent, forced_prompt)
                if not self._agent_used_tool(result):
                    return (
                        "I could not access verified tool data. "
                        "Please try again once the MCP tools are available."
                    )
        return result.final_output or ""


    def _extract_image_url(self, image):
        if not isinstance(image, dict):
            return None
        preferred = ["ITEMGALLERY_L", "ITEMGALLERY_CUT", "ITEMGALLERY_M"]
        for fmt in preferred:
            key = f'url({{"format":"{fmt}"}})'
            if key in image and isinstance(image[key], str):
                return image[key]
        for key, value in image.items():
            if key.startswith("url(") and isinstance(value, str):
                return value
        return None

    def _select_image_url(self, listing):
        if listing.get("main_image_bytes"):
            return f"/api/listings/{listing['hemnet_id']}/image/main"

        if listing.get("main_image_url"):
            return listing.get("main_image_url")

        images = self._coerce_json(listing.get("images"))
        if isinstance(images, dict):
            for image in images.get("images", []) or []:
                url = self._extract_image_url(image)
                if url:
                    return url

        thumbnail = self._coerce_json(listing.get("thumbnail"))
        url = self._extract_image_url(thumbnail)
        if url:
            return url

        return "assets/house-placeholder.svg"

    def _handle_points(self, query):
        bbox = query.get("bbox", [""])[0]
        try:
            min_lng, min_lat, max_lng, max_lat = [float(v) for v in bbox.split(",")]
        except Exception:
            self._send_json({"error": "invalid_bbox"}, status=400)
            return

        sql = """
            SELECT h.hemnet_id, h.latitude AS lat, h.longitude AS lng
            FROM hemnet_items h
            WHERE h.latitude IS NOT NULL
              AND h.longitude IS NOT NULL
              AND h.longitude BETWEEN %s AND %s
              AND h.latitude BETWEEN %s AND %s
            LIMIT 2000;
        """
        with self._db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (min_lng, max_lng, min_lat, max_lat))
                rows = cur.fetchall()

        points = [
            {"hemnet_id": row["hemnet_id"], "lat": row["lat"], "lng": row["lng"]}
            for row in rows
            if row.get("hemnet_id") is not None
        ]
        self._send_json({"points": points, "count": len(points)})

    def _handle_listing(self, hemnet_id):
        if not hemnet_id.isdigit():
            self._send_json({"error": "invalid_id"}, status=400)
            return

        sql = """
            SELECT h.*,
                   COALESCE(h.latitude, c.lattitude) AS lat,
                   COALESCE(h.longitude, c.longitude) AS lng
            FROM hemnet_items h
            LEFT JOIN hemnet_comp_items c ON c.hemnet_id = h.hemnet_id
            WHERE h.hemnet_id = %s
            LIMIT 1;
        """
        with self._db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (hemnet_id,))
                row = cur.fetchone()

        if not row:
            self._send_json({"error": "not_found"}, status=404)
            return

        for key in [
            "districts",
            "labels",
            "relevant_amenities",
            "listing_collection_ids",
            "breadcrumbs",
            "ad_targeting",
            "attachments",
            "images",
            "images_preview",
            "thumbnail",
            "photo_attribution",
            "price_change",
            "upcoming_open_houses",
            "floor_plan_images",
            "video_attachment",
            "three_d_attachment",
            "energy_classification",
            "active_package",
            "seller_package_recommendation",
            "housing_cooperative",
            "raw_listing",
            "raw_apollo_state",
            "broker_raw",
            "broker_agency_raw",
            "verified_bidding",
        ]:
            row[key] = self._coerce_json(row.get(key))

        row["image_url"] = self._select_image_url(row)
        row.pop("main_image_bytes", None)
        row.pop("floorplan_image_bytes", None)
        row.pop("main_image_mime", None)
        row.pop("floorplan_image_mime", None)

        self._send_json(row)

    def _handle_image(self, hemnet_id, image_type):
        if not hemnet_id.isdigit():
            self.send_error(400, "invalid id")
            return

        if image_type not in ("main", "floorplan"):
            self.send_error(404)
            return

        if image_type == "main":
            columns = "main_image_bytes, main_image_mime"
        else:
            columns = "floorplan_image_bytes, floorplan_image_mime"

        sql = f"SELECT {columns} FROM hemnet_items WHERE hemnet_id = %s LIMIT 1;"
        with self._db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (hemnet_id,))
                row = cur.fetchone()

        if not row or not row[0]:
            self.send_error(404)
            return

        data, content_type = row
        self.send_response(200)
        self.send_header("Content-Type", content_type or "image/jpeg")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    host = os.getenv("HOUM_HOST", "127.0.0.1")
    port = int(os.getenv("HOUM_PORT") or os.getenv("PORT", "8000"))
    handler = partial(HoumHandler, directory=str(BASE_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Houm server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
