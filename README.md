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

## Tests

```bash
cd server
source .venv/bin/activate
pytest
```

## How the halves connect

In development, Vite forwards any request starting with `/api` to `localhost:8000` (see `client/vite.config.js`). The React code calls `fetch("/api/...")` and never needs the server's full address.
