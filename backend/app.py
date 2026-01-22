from __future__ import annotations

import json
import os
import sys

import psycopg2
import psycopg2.extras
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

try:
    from backend import settings
except ImportError:  # pragma: no cover - fallback for direct script runs
    import settings


BASE_DIR = settings.BASE_DIR
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

app = FastAPI()


def _cors_origins() -> list[str]:
    raw = os.getenv("ALLOW_ORIGINS") or os.getenv("CORS_ORIGINS", "")
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db_connect():
    if not settings.DATABASE_URL:
        raise RuntimeError("Missing DATABASE_URL")
    return psycopg2.connect(settings.DATABASE_URL)


def _coerce_json(value):
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


def _normalize_name(value):
    if not isinstance(value, str):
        return None, None
    display_name = value.strip()
    if not display_name:
        return None, None
    return display_name, display_name.casefold()


def _fetch_favorites(conn, user_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT hemnet_id FROM houm_favorites WHERE user_id = %s",
            (user_id,),
        )
        return [row[0] for row in cur.fetchall()]


def _agent_instructions_path():
    return os.path.join(BASE_DIR, "backend", "agent_instruct.txt")


def _load_agent_instructions():
    default = (
        "You are a Houm assistant. You MUST use MCP tools before answering.\n"
        "Never invent listings. If tools return no data, say so.\n"
        "If tools are unavailable, return JSON with message=TOOL_UNAVAILABLE.\n"
        "Return JSON only, with message, recommended_ids, and recommendation_notes.\n"
        "Keep responses concise and actionable."
    )
    path = _agent_instructions_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
    except FileNotFoundError:
        return default
    except OSError:
        return default
    return content or default


def _build_prompt(history, message, context=None):
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


def _parse_assistant_output(reply: str):
    if not reply:
        return "", [], {}, []
    try:
        payload = json.loads(reply)
    except Exception:
        return reply, [], {}, []
    if not isinstance(payload, dict):
        return reply, [], {}, []
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

    tools_used = []
    tools_raw = payload.get("tools_used") or []
    if isinstance(tools_raw, list):
        tools_used = [item for item in tools_raw if isinstance(item, str)]

    return message or reply, recommended_ids, recommendation_notes, tools_used


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


async def _run_agent(prompt: str) -> str:
    from agents import Agent, Runner
    from agents.mcp import MCPServerStdio

    server_path = os.path.join(BASE_DIR, "backend", "server.py")
    async with MCPServerStdio(
        name="houm_mcp",
        params={
            "command": sys.executable,
            "args": [server_path],
            "env": dict(os.environ),
        },
    ) as mcp_server:
        try:
            agent = Agent(
                name="SearchAgent",
                instructions=_load_agent_instructions(),
                mcp_servers=[mcp_server],
            )
        except TypeError:
            agent = Agent(
                name="SearchAgent",
                instructions=_load_agent_instructions(),
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
        if not _agent_used_tool(result):
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
            if not _agent_used_tool(result):
                return (
                    "I could not access verified tool data. "
                    "Please try again once the MCP tools are available."
                )
    return result.final_output or ""


def _absolute_path(path: str) -> str:
    if not PUBLIC_BASE_URL:
        return path
    if not path.startswith("/"):
        return path
    return f"{PUBLIC_BASE_URL}{path}"


def _extract_image_url(image):
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


def _select_image_url(listing):
    if listing.get("main_image_bytes"):
        return _absolute_path(f"/api/listings/{listing['hemnet_id']}/image/main")

    if listing.get("main_image_url"):
        return listing.get("main_image_url")

    images = _coerce_json(listing.get("images"))
    if isinstance(images, dict):
        for image in images.get("images", []) or []:
            url = _extract_image_url(image)
            if url:
                return url

    thumbnail = _coerce_json(listing.get("thumbnail"))
    url = _extract_image_url(thumbnail)
    if url:
        return url

    return "assets/house-placeholder.svg"


@app.get("/config")
def get_config():
    key = settings.GOOGLE_MAPS_API_KEY
    status = 200 if key else 500
    return JSONResponse(
        {"googleMapsApiKey": key},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/listings/points")
def listings_points(bbox: str = Query("")):
    try:
        min_lng, min_lat, max_lng, max_lat = [float(v) for v in bbox.split(",")]
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_bbox")

    sql = """
        SELECT h.hemnet_id, h.latitude AS lat, h.longitude AS lng
        FROM hemnet_items h
        WHERE h.latitude IS NOT NULL
          AND h.longitude IS NOT NULL
          AND h.longitude BETWEEN %s AND %s
          AND h.latitude BETWEEN %s AND %s
        LIMIT 2000;
    """
    with _db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (min_lng, max_lng, min_lat, max_lat))
            rows = cur.fetchall()

    points = [
        {"hemnet_id": row["hemnet_id"], "lat": row["lat"], "lng": row["lng"]}
        for row in rows
        if row.get("hemnet_id") is not None
    ]
    return {"points": points, "count": len(points)}


@app.get("/api/profile")
def profile_get(name: str = Query("")):
    display_name, name_key = _normalize_name(name)
    if not display_name:
        raise HTTPException(status_code=400, detail="missing_name")

    sql = "SELECT * FROM houm_users WHERE name_key = %s LIMIT 1;"
    with _db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (name_key,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not_found")
        favorites = _fetch_favorites(conn, row["id"])

    row.pop("name_key", None)
    row["favorites"] = favorites
    return JSONResponse(
        jsonable_encoder(row),
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/profile")
def profile_upsert(payload: dict = Body(default=None)):
    payload = payload or {}
    display_name, name_key = _normalize_name(payload.get("name", ""))
    if not display_name:
        raise HTTPException(status_code=400, detail="missing_name")

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

    with _db_connect() as conn:
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

        favorites = _fetch_favorites(conn, row["id"])

    row.pop("name_key", None)
    row["favorites"] = favorites
    return JSONResponse(
        jsonable_encoder(row),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/favorites")
def favorites_get(name: str = Query("")):
    display_name, name_key = _normalize_name(name)
    if not display_name:
        raise HTTPException(status_code=400, detail="missing_name")

    sql = "SELECT id FROM houm_users WHERE name_key = %s LIMIT 1;"
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name_key,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="not_found")
            favorites = _fetch_favorites(conn, row[0])

    return JSONResponse(
        {"name": display_name, "favorites": favorites},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/favorites")
def favorites_add(payload: dict = Body(default=None)):
    payload = payload or {}
    display_name, name_key = _normalize_name(payload.get("name", ""))
    hemnet_id = payload.get("hemnet_id")
    if not display_name:
        raise HTTPException(status_code=400, detail="missing_name")
    if not isinstance(hemnet_id, int):
        try:
            hemnet_id = int(hemnet_id)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_hemnet_id")

    with _db_connect() as conn:
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
            favorites = _fetch_favorites(conn, user_id)

    return JSONResponse(
        {"name": display_name, "favorites": favorites},
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/favorites")
def favorites_remove(payload: dict = Body(default=None)):
    payload = payload or {}
    display_name, name_key = _normalize_name(payload.get("name", ""))
    hemnet_id = payload.get("hemnet_id")
    if not display_name:
        raise HTTPException(status_code=400, detail="missing_name")
    if not isinstance(hemnet_id, int):
        try:
            hemnet_id = int(hemnet_id)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_hemnet_id")

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM houm_users WHERE name_key = %s LIMIT 1;",
                (name_key,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="not_found")
            user_id = row[0]
            cur.execute(
                "DELETE FROM houm_favorites WHERE user_id = %s AND hemnet_id = %s;",
                (user_id, hemnet_id),
            )
            favorites = _fetch_favorites(conn, user_id)

    return JSONResponse(
        {"name": display_name, "favorites": favorites},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/assistant")
async def assistant(payload: dict = Body(default=None)):
    payload = payload or {}
    message = payload.get("message", "")
    history = payload.get("history") or []
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="missing_message")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="missing_openai_key")

    prompt = _build_prompt(history, message.strip(), context)
    try:
        reply = await _run_agent(prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"assistant_failed: {exc}") from exc
    reply_text, recommended_ids, recommendation_notes, tools_used = _parse_assistant_output(reply)
    if tools_used:
        print(f"[assistant] tools_used={tools_used}", file=sys.stderr, flush=True)
    return JSONResponse(
        {
            "reply": reply_text,
            "recommended_ids": recommended_ids,
            "recommendation_notes": recommendation_notes,
            "tools_used": tools_used,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/listings/{hemnet_id}")
def listing_get(hemnet_id: str):
    if not hemnet_id.isdigit():
        raise HTTPException(status_code=400, detail="invalid_id")

    sql = """
        SELECT h.*,
               COALESCE(h.latitude, c.lattitude) AS lat,
               COALESCE(h.longitude, c.longitude) AS lng
        FROM hemnet_items h
        LEFT JOIN hemnet_comp_items c ON c.hemnet_id = h.hemnet_id
        WHERE h.hemnet_id = %s
        LIMIT 1;
    """
    with _db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (hemnet_id,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="not_found")

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
        row[key] = _coerce_json(row.get(key))

    row["image_url"] = _select_image_url(row)
    if row.get("floorplan_image_bytes"):
        row["floorplan_image_url"] = _absolute_path(
            f"/api/listings/{row['hemnet_id']}/image/floorplan"
        )
    else:
        row["floorplan_image_url"] = None
    row.pop("main_image_bytes", None)
    row.pop("floorplan_image_bytes", None)
    row.pop("main_image_mime", None)
    row.pop("floorplan_image_mime", None)

    return JSONResponse(
        jsonable_encoder(row),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/listings/{hemnet_id}/image")
def listing_image_default(hemnet_id: str):
    return listing_image(hemnet_id, "main")


@app.get("/api/listings/{hemnet_id}/image/{image_type}")
def listing_image(hemnet_id: str, image_type: str):
    if not hemnet_id.isdigit():
        raise HTTPException(status_code=400, detail="invalid_id")

    if image_type not in ("main", "floorplan"):
        raise HTTPException(status_code=404, detail="not_found")

    if image_type == "main":
        columns = "main_image_bytes, main_image_mime"
    else:
        columns = "floorplan_image_bytes, floorplan_image_mime"

    sql = f"SELECT {columns} FROM hemnet_items WHERE hemnet_id = %s LIMIT 1;"
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (hemnet_id,))
            row = cur.fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="not_found")

    data, content_type = row
    return Response(
        content=data,
        media_type=content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
