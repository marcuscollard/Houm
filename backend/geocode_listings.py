from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request

import psycopg2
import psycopg2.extras

try:
    from backend import settings
except ImportError:  # pragma: no cover - fallback for direct script runs
    import settings



def _ensure_columns(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE hemnet_items
            ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
            """
        )
    conn.commit()


def _build_address(row: dict) -> str:
    parts = []
    for key in (
        "address",
        "post_code",
        "municipality_name",
        "region_name",
        "county_name",
        "geographic_area",
    ):
        value = row.get(key)
        if value:
            value = str(value).strip()
            if value:
                parts.append(value)

    # De-duplicate while preserving order.
    seen = set()
    unique_parts = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        unique_parts.append(part)

    return ", ".join(unique_parts)


def _geocode(address: str, api_key: str) -> tuple[float | None, float | None, str]:
    params = urllib.parse.urlencode({"address": address, "key": api_key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "HoumGeocoder/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    status = payload.get("status", "UNKNOWN_ERROR")
    if status != "OK":
        return None, None, status

    results = payload.get("results") or []
    if not results:
        return None, None, "ZERO_RESULTS"

    location = results[0].get("geometry", {}).get("location", {})
    return location.get("lat"), location.get("lng"), status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill hemnet_items latitude/longitude via Google Geocoding."
    )
    parser.add_argument("--limit", type=int, default=100, help="Max rows to geocode.")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Seconds to sleep between requests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log geocoding results without writing to the database.",
    )
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_GEOCODING_API_KEY") or settings.GOOGLE_MAPS_API_KEY
    if not api_key:
        print("Missing GOOGLE_GEOCODING_API_KEY or GOOGLE_MAPS_API_KEY.")
        return 1

    if not settings.DATABASE_URL:
        print("Missing DATABASE_URL.")
        return 1

    with psycopg2.connect(settings.DATABASE_URL) as conn:
        _ensure_columns(conn)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT hemnet_id,
                       address,
                       post_code,
                       municipality_name,
                       region_name,
                       county_name,
                       geographic_area
                FROM hemnet_items
                WHERE (latitude IS NULL OR longitude IS NULL)
                  AND NULLIF(TRIM(COALESCE(address, '')), '') IS NOT NULL
                ORDER BY hemnet_id
                LIMIT %s;
                """,
                (args.limit,),
            )
            rows = cur.fetchall()

        if not rows:
            print("No rows to geocode.")
            return 0

        updated = 0
        with conn.cursor() as cur:
            for row in rows:
                address = _build_address(row)
                if not address:
                    continue

                lat, lng, status = _geocode(address, api_key)
                if status != "OK":
                    print(
                        f"hemnet_id={row['hemnet_id']} status={status} "
                        f"address={address}"
                    )
                    time.sleep(args.sleep)
                    continue

                print(f"hemnet_id={row['hemnet_id']} lat={lat} lng={lng}")
                if not args.dry_run:
                    cur.execute(
                        """
                        UPDATE hemnet_items
                        SET latitude = %s,
                            longitude = %s
                        WHERE hemnet_id = %s;
                        """,
                        (lat, lng, row["hemnet_id"]),
                    )
                    updated += 1

                time.sleep(args.sleep)

        if not args.dry_run:
            conn.commit()

    print(f"Done. Updated {updated} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
