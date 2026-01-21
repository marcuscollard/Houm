# Houm

Map-first real-estate concept UI with a lightweight frontend and small Python backend utilities.

Quick start
- Frontend (Next.js):
  - Install: `npm install`
  - Dev server: `npm run dev`
  - Set `NEXT_PUBLIC_API_BASE_URL` to your backend origin (e.g., `http://127.0.0.1:8000`).
- Backend (FastAPI):
  - Set `GOOGLE_MAPS_API_KEY` in `.env`.
  - Enable Google Geocoding API (billing required) on the same key if you want map points.
  - Set `DATABASE_URL` in `.env` if you want backend access to Neon Postgres.
  - Install backend deps: `pip install -r requirements.txt`.
  - Add coords columns if needed: `backend/migrations/001_add_latlng.sql`.
  - Add profile tables: `backend/migrations/002_add_houm_profile.sql`.
  - Backfill coordinates: `python backend/geocode_listings.py --limit 200`.
  - Run `python backend/run.py` (or `uvicorn backend.app:app --host 0.0.0.0 --port 8000`).

MCP server
- Enable Google Places API + Distance Matrix API on the same key.
- Run `python backend/server.py` to start the MCP server (set `MCP_TRANSPORT=sse` for SSE).

Agents SDK (stdio, local-first)
- Install: `pip install openai openai-agents`.
- Run: `python backend/agent_runner.py "Find parks near Vasagatan 1, Stockholm."`.

Structure
- `src/app/`: Next.js app router frontend.
- `public/`: static assets and `app.js` (map logic loaded by the page).
- `backend/`: Python utilities and service code.
- Legacy static files in repo root are kept for reference only.

Remote frontend notes
- Set `CORS_ORIGINS` on the backend to your Vercel URL (comma-separated for multiple).
- Set `PUBLIC_BASE_URL` if you want image URLs to resolve to the backend host.
