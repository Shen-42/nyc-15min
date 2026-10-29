# Development

How to run, test, rebuild, and deploy the project.

## Stack

| Part | Tools |
| --- | --- |
| Front end | React 19, Vite, Leaflet with react-leaflet, Atkinson Hyperlegible font |
| Back end | Python, FastAPI, Shapely, opening-hours-py |
| Data | OpenStreetMap via OSMnx and the Overpass API; NYC Open Data for curb ramps |
| Map tiles | Stadia Maps, OSM Bright style |
| Accounts | Supabase Auth (email and password) and Postgres, through the API |
| Hosting | Render: a static site, a web service for the API, and Key Value (Redis) for rate limits and usage counts |
| Automation | GitHub Actions: tests on every push and pull request, Dependabot updates, monthly data refresh, Supabase keep-alive |
| Tests | pytest (server), Vitest (site) |

## Project layout

```
client/                    React site
  src/App.jsx              state, requests, and layout
  src/api.js               API address and request helper
  src/components/          map, results panel, category rows, place and corner markers,
                           the time, "Your needs", and "Map view" sections, the grid layer
  src/data/                categories, needs presets, New York time, heat map colors and image,
                           Manhattan boundary
  src/hooks.js             media query hook (phone or desktop layout)
  src/account/             sign-in, account, and admin dialogs, saving places and profiles
  src/styles/              tokens, base, layout, panel, and map CSS
server/                    FastAPI API
  main.py                  routes, caching, timing
  rate_limit.py            per-visitor rate limit, in Redis or memory
  graph.py                 walking graph, grid index, Dijkstra
  walk_area.py             builds the shaded walking area
  amenities.py             which places a walk reaches
  scoring.py               the 0–100 score, with custom weights
  hours.py                 whether a place is open at a given time
  modes.py                 walking and wheelchair speeds, curb ramp penalty
  grid.py                  the scored Manhattan grid, and ranking a spot against it
  accounts.py              sign-in checks, saved places, profiles, roles, admin routes
  auth.py, store.py        checking Supabase tokens; reading and writing the tables
  usage.py                 daily request counts for the admin page
  scripts/                 downloads (graph, water, places, curb ramps), the grid, and the data check
  data/                    the downloaded data (committed)
  test_*.py                tests
supabase/schema.sql        the account tables, to paste into Supabase's SQL editor
render.yaml                Render setup for all three services
.github/workflows/         tests, monthly data refresh, Supabase keep-alive
.github/dependabot.yml     weekly dependency updates
docs/                      these docs
```

## Run it locally

Requirements: Node.js 20.19 or newer, and Python 3.11 or newer.

**1. API** (first terminal):

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Check it at http://localhost:8000/api/health. The interactive API docs are at http://localhost:8000/docs (turned off on Render).

**2. Map key.** Stadia Maps rate-limits requests from localhost without a key, so the map loads in patches. Create a free key at https://client.stadiamaps.com and save it in `client/.env.local`, which git ignores:

```
VITE_STADIA_API_KEY=your-key-here
```

**3. Site** (second terminal):

```bash
cd client
npm install
npm run dev
```

Open http://localhost:5173. In development, Vite forwards requests that start with `/api` to `localhost:8000` (see `client/vite.config.js`).

**4. Accounts (optional).** Without these settings the site runs as before, with no sign-in.

1. Create a free project at https://supabase.com. In its **SQL Editor**, run `supabase/schema.sql`.
2. Under **Authentication > URL Configuration**, set the Site URL to the live site and add `http://localhost:5173/**` to the redirect URLs.
3. Copy `client/.env.example` and `server/.env.example` to `client/.env.local` and `server/.env`, and fill in the project URL and keys from **Project Settings > API Keys**. Both files are ignored by git.
4. Start the API with `uvicorn main:app --reload --port 8000 --env-file .env`.
5. To make yourself an admin, sign up on the site, copy your user id from **Authentication > Users** into `ADMIN_USER_IDS`, and restart the API.

## Rebuild the data

The data in `server/data/` is committed. A GitHub Actions job (`.github/workflows/refresh-data.yml`) rebuilds it on the 1st of every month: it downloads everything again (OpenStreetMap from Overpass, curb ramps from NYC Open Data), checks that no count dropped by more than 15% (`server/scripts/check_data.py`), runs the tests, scores the Manhattan grid again, and commits the new data, which makes Render redeploy. Run it by hand from the repo's **Actions** tab under **Refresh map data**. Its results table is on the run's summary page.

To rebuild by hand:

```bash
cd server
source .venv/bin/activate
pip install -r requirements-build.txt
python scripts/build_graph.py      # walking network
python scripts/build_water.py      # lakes and ponds
python scripts/build_amenities.py  # places and park outlines
python scripts/build_ramps.py      # curb ramps from NYC Open Data (after build_graph.py)
python scripts/build_grid.py       # score every 100 m of Manhattan (after all the others)
```

Public Overpass servers are often busy. Each download retries up to six times with growing waits (30 s to 5 minutes), alternating between two servers (`server/scripts/overpass.py`). Finished downloads are cached in `server/cache/`, so a script that fails partway can be run again. If the default servers are blocked where you are, choose another:

```bash
OVERPASS_URL=https://overpass.kumi.systems/api python scripts/build_water.py
```

`server/data/manhattan-boundary.json` is a copy of `client/src/data/manhattan-boundary.json`. If you change one, copy it over.

## Tests

```bash
cd server
source .venv/bin/activate
pytest
```

For the site:

```bash
cd client
npm test
```

The server tests cover:

- Dijkstra on small made-up graphs, including the slower wheelchair speed and the extra minutes at corners without ramps
- the grid index, checked against testing every node
- the walking area: block interiors filled, nothing drawn over the Hudson, Harlem Meer, or the Reservoir
- places and scoring, including custom weights, categories set to 0, and closed places
- opening hours at different times and days
- ranking a spot against the grid with different weights
- the API routes, including bad `weights`, `at`, and `mode` values
- the rate limit, with a stand-in for Redis
- accounts: missing, forged, expired, and wrong-project tokens; people only seeing and deleting their own places; the two-tab profile conflict; deleting an account; each admin route refused to users; and the exact requests sent to Supabase, with a fake server in place of it
- unexpected errors: a crashing route answers with a plain message and a request id, keeps its security headers, and leaks nothing; bad input comes back as one sentence

The site tests (Vitest, with jsdom standing in for the browser) cover the 70-second timeout, retrying the shaded area once, readable messages for every kind of failure, the **Try again** button and its focus, and the crash screens.

## Deploy (Render, free plan)

`render.yaml` defines three services, created together in the Render dashboard under **New > Blueprint**:

- **nyc-15min-api**: the FastAPI server. 512 MB of memory and 0.1 CPU. It sleeps after 15 minutes without visits; the site shows "Waking up the server" while it starts again.
- **nyc-15min**: the built React site, served as static files. Always on.
- **nyc-15min-limits**: a free Key Value (Redis-compatible) instance for rate-limit counts, reachable only from the API.

Set these in each service's **Environment** page:

| Service | Variable | Value |
| --- | --- | --- |
| nyc-15min-api | `ALLOWED_ORIGINS` | The site's address, e.g. `https://nyc-15min.onrender.com` |
| nyc-15min-api | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | From Supabase's **Project Settings > API Keys** (accounts) |
| nyc-15min-api | `ADMIN_USER_IDS` | Comma-separated Supabase user ids |
| nyc-15min-api | `GH_REFRESH_TOKEN` | A fine-grained GitHub token with Actions read and write on this repo |
| nyc-15min | `VITE_API_URL` | The API's address, e.g. `https://nyc-15min-api.onrender.com` |
| nyc-15min | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` | From the same Supabase page; the publishable key is public by design |

Vite builds `VITE_API_URL` into the site, so changing it needs a new deploy of the site. When a change touches both the API and the site, wait for the API to finish deploying before testing, since the site finishes first.

On the live site, Stadia Maps allows tiles by checking the site's domain, which you register under **Authentication Configuration** in the Stadia dashboard. No key is shipped to the browser.

[Back to the README](../README.md)
