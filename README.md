# NYC 15-Minute City Explorer

Click any point in Manhattan and see what you can reach on foot in 15 minutes.

- `client/`: React app (Vite). Later: Leaflet map, Turf.js shapes.
- `server/`: FastAPI back end. Later: walking graph and Dijkstra search.

## Requirements

- Node.js 20.19 or newer (`node -v`)
- Python 3.11 or newer (`python3 --version`)

## Run it

Use two terminals.

**Terminal 1, back end:**

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Check it at http://localhost:8000/api/health. FastAPI also lists all routes at http://localhost:8000/docs.

**Terminal 2, front end:**

```bash
cd client
npm install
npm run dev
```

Open http://localhost:5173. A green box saying "Server says: ok" means the two halves are talking. A red box means the back end is not running.

## Build the walking graph (once)

The server needs `server/data/walk_graph.json`, Manhattan's walkable streets from OpenStreetMap. It's committed to the repo, so you only need to rebuild it to get newer map data.

```bash
cd server
source .venv/bin/activate
pip install -r requirements-build.txt
python scripts/build_graph.py
```

Check it with the server running: http://localhost:8000/api/graph/info and http://localhost:8000/api/nearest-node?lat=40.758&lng=-73.9855

## Tests

```bash
cd server
source .venv/bin/activate
pytest
```

## How the halves connect

In development, Vite forwards any request starting with `/api` to `localhost:8000` (see `client/vite.config.js`). The React code calls `fetch("/api/...")` and never needs the server's full address.

## Deploy (Render, free plan)

`render.yaml` defines two services:

- **nyc-15min-api**: the FastAPI server (Python). Sleeps after 15 minutes without visits; the first request after that takes about a minute while it wakes, and the site says so.
- **nyc-15min**: the React site, built with `npm run build` and served as static files. Always on.

Environment variables you set in the Render dashboard:

| Service | Variable | Value |
| --- | --- | --- |
| nyc-15min-api | `ALLOWED_ORIGINS` | The site's address, e.g. `https://nyc-15min.onrender.com` |
| nyc-15min | `VITE_API_URL` | The API's address, e.g. `https://nyc-15min-api.onrender.com` |

Changing `VITE_API_URL` needs a new deploy of the site, because Vite bakes it in at build time.

## Map tiles

The base map is Stadia Maps' OSM Bright style (free for non-commercial use, 200,000 tiles a month).

- **Locally:** without a key, Stadia rate-limits localhost and the map loads in patches. Create a free API key in the Stadia dashboard and put it in `client/.env.local`:
  ```
  VITE_STADIA_API_KEY=your-key-here
  ```
  Restart `npm run dev` after creating the file. `.env.local` is ignored by git.
- **Deployed site:** add its domain under "Authentication Configuration" in the Stadia dashboard, or tiles won't load. No key is needed there.

