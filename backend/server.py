from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP
import psycopg2
import psycopg2.extras

try:
    from backend import settings
except ImportError:  # pragma: no cover - fallback for direct script runs
    import settings


LOG_TOOL_CALLS = os.getenv("MCP_LOG_CALLS") == "1"
mcp = FastMCP("houm-geo")


def _log_tool_call(name: str, payload: dict[str, Any] | None = None) -> None:
    if not LOG_TOOL_CALLS:
        return
    details = json.dumps(payload or {}, ensure_ascii=False)
    print(f"[mcp] tool={name} payload={details}", file=sys.stderr, flush=True)


def _require_maps_key() -> str:
    key = os.getenv("GOOGLE_MAPS_API_KEY") or settings.GOOGLE_MAPS_API_KEY
    if not key:
        raise ValueError("Missing GOOGLE_MAPS_API_KEY.")
    return key


def _request_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params)
    req = Request(
        f"{url}?{query}",
        headers={"User-Agent": "HoumMCP/1.0"},
    )
    with urlopen(req, timeout=20) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _db_connect():
    if not settings.DATABASE_URL:
        raise ValueError("Missing DATABASE_URL.")
    return psycopg2.connect(settings.DATABASE_URL)


def _build_filters(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    if not filters:
        return "", []

    clauses: list[str] = []
    params: list[Any] = []
    price_expr = "COALESCE(price, asked_price)"

    def _add_range(key_min: str, key_max: str, expr: str) -> None:
        if key_min in filters and filters[key_min] is not None:
            clauses.append(f"{expr} >= %s")
            params.append(filters[key_min])
        if key_max in filters and filters[key_max] is not None:
            clauses.append(f"{expr} <= %s")
            params.append(filters[key_max])

    _add_range("min_price", "max_price", price_expr)
    _add_range("min_rooms", "max_rooms", "rooms")
    _add_range("min_area", "max_area", "square_meters")
    _add_range("min_year", "max_year", "CASE WHEN year ~ '^[0-9]{4}$' THEN year::int END")
    if "max_monthly_fee" in filters and filters["max_monthly_fee"] is not None:
        clauses.append("monthly_fee <= %s")
        params.append(filters["max_monthly_fee"])
    if "min_monthly_fee" in filters and filters["min_monthly_fee"] is not None:
        clauses.append("monthly_fee >= %s")
        params.append(filters["min_monthly_fee"])

    list_filters = {
        "housing_forms": "housing_form",
        "housing_form": "housing_form",
        "tenure": "tenure",
        "municipalities": "municipality_name",
        "regions": "region_name",
        "counties": "county_name",
        "types": "type",
    }
    for key, column in list_filters.items():
        value = filters.get(key)
        if isinstance(value, list) and value:
            clauses.append(f"{column} = ANY(%s)")
            params.append(value)

    if isinstance(filters.get("districts"), list) and filters["districts"]:
        clauses.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(districts, '[]'::jsonb)) AS d "
            "WHERE d = ANY(%s))"
        )
        params.append(filters["districts"])

    bbox = filters.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        clauses.append("latitude IS NOT NULL AND longitude IS NOT NULL")
        clauses.append("longitude BETWEEN %s AND %s")
        clauses.append("latitude BETWEEN %s AND %s")
        params.extend([bbox[0], bbox[2], bbox[1], bbox[3]])

    if not clauses:
        return "", []

    return "WHERE " + " AND ".join(clauses), params


def _tag_query(field: str) -> tuple[str, str]:
    if field == "districts":
        return (
            "hemnet_id, jsonb_array_elements_text(COALESCE(districts, '[]'::jsonb)) AS tag",
            "hemnet_items",
        )
    if field == "labels":
        return (
            "hemnet_id, COALESCE(elem->>'text', elem->>'title', elem::text) AS tag",
            "hemnet_items, LATERAL jsonb_array_elements(COALESCE(labels, '[]'::jsonb)) AS elem",
        )
    if field == "relevant_amenities":
        return (
            "hemnet_id, COALESCE(elem->>'title', elem->>'text', elem::text) AS tag",
            "hemnet_items, LATERAL jsonb_array_elements(COALESCE(relevant_amenities, '[]'::jsonb)) AS elem",
        )
    if field == "housing_form":
        return ("hemnet_id, housing_form AS tag", "hemnet_items")
    if field == "tenure":
        return ("hemnet_id, tenure AS tag", "hemnet_items")
    if field == "municipality_name":
        return ("hemnet_id, municipality_name AS tag", "hemnet_items")
    if field == "region_name":
        return ("hemnet_id, region_name AS tag", "hemnet_items")
    if field == "county_name":
        return ("hemnet_id, county_name AS tag", "hemnet_items")
    if field == "type":
        return ("hemnet_id, type AS tag", "hemnet_items")
    return ("", "")


@mcp.tool(name="attributes_list")
async def attributes_list() -> dict[str, Any]:
    """List queryable attributes for hard filters and analytics."""
    _log_tool_call("attributes_list")
    hard_filters = {
        "min_price": "numeric",
        "max_price": "numeric",
        "min_rooms": "numeric",
        "max_rooms": "numeric",
        "min_area": "numeric",
        "max_area": "numeric",
        "min_year": "numeric",
        "max_year": "numeric",
        "min_monthly_fee": "numeric",
        "max_monthly_fee": "numeric",
        "housing_forms": "list",
        "housing_form": "list",
        "tenure": "list",
        "municipalities": "list",
        "regions": "list",
        "counties": "list",
        "types": "list",
        "districts": "list",
        "bbox": "bbox[min_lng,min_lat,max_lng,max_lat]",
    }
    tag_fields = [
        "housing_form",
        "tenure",
        "municipality_name",
        "region_name",
        "county_name",
        "districts",
        "type",
        "labels",
        "relevant_amenities",
    ]
    numeric_fields = [
        "price",
        "asked_price",
        "rooms",
        "square_meters",
        "monthly_fee",
        "year",
    ]
    available_columns = []
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'hemnet_items';
                """
            )
            available_columns = [row[0] for row in cur.fetchall()]

    return {
        "hard_filters": hard_filters,
        "tag_fields": tag_fields,
        "numeric_fields": numeric_fields,
        "hemnet_items_columns": sorted(available_columns),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _geocode(address: str) -> dict[str, Any]:
    key = _require_maps_key()
    return _request_json(
        "https://maps.googleapis.com/maps/api/geocode/json",
        {"address": address, "key": key},
    )


@mcp.tool(name="geo_nearby")
async def geo_nearby(
    address: str,
    place_type: str = "park",
    radius_m: int = 1500,
    keyword: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Find nearby places (e.g. parks) around an address using Google Places."""
    _log_tool_call(
        "geo_nearby",
        {
            "address": address,
            "place_type": place_type,
            "radius_m": radius_m,
            "keyword": keyword,
            "limit": limit,
        },
    )
    if not address:
        return {"error": "missing_address"}

    geocode = _geocode(address)
    if geocode.get("status") != "OK":
        return {"error": "geocode_failed", "status": geocode.get("status")}

    location = geocode["results"][0]["geometry"]["location"]
    params = {
        "location": f"{location['lat']},{location['lng']}",
        "radius": max(100, min(radius_m, 50000)),
        "key": _require_maps_key(),
    }
    if place_type:
        params["type"] = place_type
    if keyword:
        params["keyword"] = keyword

    places = _request_json(
        "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
        params,
    )
    if places.get("status") not in ("OK", "ZERO_RESULTS"):
        return {"error": "places_failed", "status": places.get("status")}

    results = []
    for item in (places.get("results") or [])[: max(1, min(limit, 20))]:
        results.append(
            {
                "name": item.get("name"),
                "place_id": item.get("place_id"),
                "types": item.get("types", []),
                "rating": item.get("rating"),
                "user_ratings_total": item.get("user_ratings_total"),
                "vicinity": item.get("vicinity"),
                "location": item.get("geometry", {}).get("location"),
            }
        )
    return {
        "origin": address,
        "origin_location": location,
        "count": len(results),
        "places": results,
    }


@mcp.tool(name="geo_distance")
async def geo_distance(
    origin: str,
    destination: str,
    mode: str = "driving",
) -> dict[str, Any]:
    """Return travel distance and duration via Google Distance Matrix."""
    _log_tool_call(
        "geo_distance",
        {
            "origin": origin,
            "destination": destination,
            "mode": mode,
        },
    )
    if not origin or not destination:
        return {"error": "missing_origin_or_destination"}

    key = _require_maps_key()
    payload = _request_json(
        "https://maps.googleapis.com/maps/api/distancematrix/json",
        {
            "origins": origin,
            "destinations": destination,
            "mode": mode,
            "units": "metric",
            "key": key,
        },
    )

    if payload.get("status") != "OK":
        return {"error": "distance_failed", "status": payload.get("status")}

    rows = payload.get("rows") or []
    elements = rows[0].get("elements") if rows else []
    element = elements[0] if elements else {}
    if element.get("status") != "OK":
        return {"error": "route_unavailable", "status": element.get("status")}

    return {
        "origin": origin,
        "destination": destination,
        "distance_meters": element.get("distance", {}).get("value"),
        "distance_text": element.get("distance", {}).get("text"),
        "duration_seconds": element.get("duration", {}).get("value"),
        "duration_text": element.get("duration", {}).get("text"),
        "mode": mode,
    }


@mcp.tool(name="listings_by_bbox")
async def listings_by_bbox(
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
    limit: int = 200,
) -> dict[str, Any]:
    """Return listings in a bounding box from the database."""
    _log_tool_call(
        "listings_by_bbox",
        {
            "min_lng": min_lng,
            "min_lat": min_lat,
            "max_lng": max_lng,
            "max_lat": max_lat,
            "limit": limit,
        },
    )
    limit = max(1, min(limit, 1000))
    sql = """
        SELECT hemnet_id,
               address,
               geographic_area,
               price,
               rooms,
               square_meters,
               latitude,
               longitude
        FROM hemnet_items
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
          AND longitude BETWEEN %s AND %s
          AND latitude BETWEEN %s AND %s
        LIMIT %s;
    """
    with _db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (min_lng, max_lng, min_lat, max_lat, limit))
            rows = cur.fetchall()

    return {"count": len(rows), "listings": rows}


@mcp.tool(name="listings_search")
async def listings_search(
    hard_filters: dict[str, Any] | None = None,
    limit: int = 20,
    order_by: str = "price_desc",
) -> dict[str, Any]:
    """Return listings that match hard filters."""
    _log_tool_call(
        "listings_search",
        {
            "hard_filters": hard_filters,
            "limit": limit,
            "order_by": order_by,
        },
    )
    hard_filters = hard_filters or {}
    limit = max(1, min(limit, 100))
    where_sql, params = _build_filters(hard_filters)
    order_map = {
        "price_desc": "COALESCE(price, asked_price) DESC NULLS LAST",
        "price_asc": "COALESCE(price, asked_price) ASC NULLS LAST",
        "newest": "COALESCE(published_at, collected_at) DESC NULLS LAST",
        "oldest": "COALESCE(published_at, collected_at) ASC NULLS LAST",
        "largest": "square_meters DESC NULLS LAST",
        "smallest": "square_meters ASC NULLS LAST",
        "rooms_desc": "rooms DESC NULLS LAST",
        "rooms_asc": "rooms ASC NULLS LAST",
    }
    order_sql = order_map.get(order_by, order_map["price_desc"])
    sql = f"""
        SELECT hemnet_id,
               title,
               address,
               geographic_area,
               price,
               asked_price,
               rooms,
               square_meters,
               monthly_fee,
               listing_url,
               latitude,
               longitude
        FROM hemnet_items
        {where_sql}
        ORDER BY {order_sql}
        LIMIT %s;
    """
    params.append(limit)
    with _db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return {"count": len(rows), "listings": rows}


@mcp.tool(name="listings_get")
async def listings_get(hemnet_id: int) -> dict[str, Any]:
    """Return a single listing summary from the database."""
    _log_tool_call("listings_get", {"hemnet_id": hemnet_id})
    sql = """
        SELECT hemnet_id,
               title,
               address,
               geographic_area,
               price,
               asked_price,
               rooms,
               square_meters,
               formatted_living_area,
               year,
               description,
               listing_url,
               latitude,
               longitude
        FROM hemnet_items
        WHERE hemnet_id = %s
        LIMIT 1;
    """
    with _db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (hemnet_id,))
            row = cur.fetchone()
    if not row:
        return {"error": "listing_not_found", "hemnet_id": hemnet_id}
    return row


@mcp.tool(name="search_estimate")
async def search_estimate(
    hard_filters: dict[str, Any] | None = None,
    soft_prefs: dict[str, Any] | None = None,
    tag_fields: list[str] | None = None,
    numeric_fields: list[str] | None = None,
    bins: int = 8,
    tag_limit: int = 15,
) -> dict[str, Any]:
    """Estimate result size and distributions for a given filter set."""
    _log_tool_call(
        "search_estimate",
        {
            "hard_filters": hard_filters,
            "soft_prefs": soft_prefs,
            "tag_fields": tag_fields,
            "numeric_fields": numeric_fields,
            "bins": bins,
            "tag_limit": tag_limit,
        },
    )
    hard_filters = hard_filters or {}
    soft_prefs = soft_prefs or {}
    tag_fields = tag_fields or [
        "housing_form",
        "tenure",
        "municipality_name",
        "region_name",
        "districts",
    ]
    numeric_fields = numeric_fields or ["price", "rooms", "square_meters", "monthly_fee", "year"]
    bins = max(3, min(bins, 20))
    tag_limit = max(5, min(tag_limit, 50))

    where_sql, params = _build_filters(hard_filters)
    base_sql = f"FROM hemnet_items {where_sql}"

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) {base_sql};", params)
            filtered_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM hemnet_items;")
            total_count = cur.fetchone()[0]

        tag_stats: dict[str, Any] = {}
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for field in tag_fields:
                select_sql, from_sql = _tag_query(field)
                if not select_sql:
                    continue

                overall_sql = f"""
                    SELECT tag, COUNT(DISTINCT hemnet_id) AS count
                    FROM (SELECT {select_sql} FROM {from_sql}) tags
                    WHERE tag IS NOT NULL AND tag <> ''
                    GROUP BY tag
                    ORDER BY count DESC
                    LIMIT %s;
                """
                cur.execute(overall_sql, (tag_limit,))
                overall = cur.fetchall()
                for row in overall:
                    row["share"] = (row["count"] / total_count) if total_count else 0

                filtered_sql = f"""
                    WITH filtered AS (
                        SELECT hemnet_id
                        FROM hemnet_items
                        {where_sql}
                    )
                    SELECT tag, COUNT(DISTINCT hemnet_id) AS count
                    FROM (SELECT {select_sql} FROM {from_sql}) tags
                    JOIN filtered f ON f.hemnet_id = tags.hemnet_id
                    WHERE tag IS NOT NULL AND tag <> ''
                    GROUP BY tag
                    ORDER BY count DESC
                    LIMIT %s;
                """
                cur.execute(filtered_sql, params + [tag_limit])
                filtered = cur.fetchall()
                for row in filtered:
                    row["share"] = (row["count"] / filtered_count) if filtered_count else 0

                tag_stats[field] = {
                    "overall": overall,
                    "filtered": filtered,
                }

        numeric_map = {
            "price": "COALESCE(price, asked_price)",
            "asked_price": "asked_price",
            "rooms": "rooms",
            "square_meters": "square_meters",
            "area": "square_meters",
            "monthly_fee": "monthly_fee",
            "year": "CASE WHEN year ~ '^[0-9]{4}$' THEN year::int END",
        }
        numeric_stats: dict[str, Any] = {}
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for field in numeric_fields:
                expr = numeric_map.get(field)
                if not expr:
                    numeric_stats[field] = {"error": "unsupported_field"}
                    continue
                data_sql = f"""
                    SELECT {expr} AS value
                    FROM hemnet_items
                    {where_sql}
                """
                stats_sql = f"""
                    SELECT COUNT(*) AS count,
                           MIN(value) AS min,
                           MAX(value) AS max,
                           AVG(value) AS avg,
                           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) AS p50,
                           PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY value) AS p90
                    FROM ({data_sql}) t
                    WHERE value IS NOT NULL;
                """
                cur.execute(stats_sql, params)
                stats = cur.fetchone()
                histogram = []
                if stats["count"] and stats["min"] is not None and stats["max"] is not None:
                    if stats["min"] < stats["max"]:
                        hist_sql = f"""
                            WITH data AS (
                                SELECT {expr} AS value
                                FROM hemnet_items
                                {where_sql}
                                WHERE {expr} IS NOT NULL
                            ),
                            bounds AS (
                                SELECT MIN(value) AS min_v, MAX(value) AS max_v FROM data
                            )
                            SELECT width_bucket(value, bounds.min_v, bounds.max_v, %s) AS bucket,
                                   COUNT(*) AS count
                            FROM data, bounds
                            GROUP BY bucket
                            ORDER BY bucket;
                        """
                        cur.execute(hist_sql, params + [bins])
                        histogram = cur.fetchall()
                numeric_stats[field] = {**stats, "histogram": histogram}

    soft_where, soft_params = _build_filters(soft_prefs)
    soft_match_count = None
    if soft_prefs:
        combined_clauses = []
        if where_sql:
            combined_clauses.append(where_sql.replace("WHERE ", ""))
        if soft_where:
            combined_clauses.append(soft_where.replace("WHERE ", ""))
        combined_where = ""
        if combined_clauses:
            combined_where = "WHERE " + " AND ".join(combined_clauses)
        soft_sql = f"SELECT COUNT(*) FROM hemnet_items {combined_where};"
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(soft_sql, params + soft_params)
                soft_match_count = cur.fetchone()[0]

    return _jsonable(
        {
            "total_count": total_count,
            "filtered_count": filtered_count,
            "soft_match_count": soft_match_count,
            "tag_prevalence": tag_stats,
            "numeric_distributions": numeric_stats,
        }
    )


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
