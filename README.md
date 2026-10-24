# NYC 15-Minute City Explorer

Click any point in Manhattan to see everywhere you can walk in 15 minutes, which groceries, pharmacies, doctors, parks, schools, and subway stations fall inside that walk, and a 0–100 score for how much of daily life is within reach.

**Live site:** https://nyc-15min.onrender.com
(The API runs on a free plan and sleeps after 15 minutes without visits. The first search after that can take up to a minute while it wakes.)

## How it works

1. **Walking network.** Manhattan's walkable streets and paths come from OpenStreetMap, downloaded once with OSMnx and saved as a graph: 36,790 nodes and 57,619 segments, each with its length in meters and the shape of curved paths.
2. **Nearest street point.** A click snaps to the nearest graph node using a grid index (0.002° cells, searched in growing rings), about 20 times faster than checking every node. Clicks on water or more than 150 m from any path are turned away with a message.
3. **15-minute search.** Dijkstra's algorithm with a binary heap spreads out from that node at 80 m per minute and stops at 15 minutes. From Times Square it reaches about 1,800 nodes in a few milliseconds.
4. **Walking area.** Every reached street segment is widened by 40 m and merged with Shapely, holes such as block interiors are filled, and the result is cut to Manhattan's shoreline minus its lakes and ponds. Segments that the time limit cuts off partway are drawn only as far as the time allows.
5. **Places.** About 1,900 groceries, pharmacies, doctors and clinics, parks, schools, and subway stations from OpenStreetMap, each attached to the graph. A park counts as reached when any path into it is reached.
6. **Score.** Each category earns points from its nearest few places, full points within 3 minutes and falling along a bell curve after that (50% at 8 minutes). Categories are then weighted:

   ```
   f(t)  = 1 if t ≤ 3 min, else exp(-(t − 3)² / 36)
   S_c   = Σ depthᵢ · f(tᵢ)       over the k nearest places in category c
   score = 100 · Σ w_c · S_c / Σ w_c
   ```

   | Category | Weight | Places counted |
   | --- | --- | --- |
   | Groceries | 3 | 5 |
   | Subway stations | 2 | 3 |
   | Pharmacies | 1 | 3 |
   | Doctors and clinics | 1 | 2 |
   | Parks | 1 | 2 |
   | Schools | 1 | 2 |

   The decay shape follows Yang et al. (2023), who scored Shanghai's 15-minute life circles. Counting several places per category and weighting groceries highest follow Walk Score. Both use full points up to 5 minutes, which scored almost all of Manhattan 97–99, so this version uses 3 minutes and counts more places. Across 150 random points the median is 78. The panel also shows proximity time, the average minutes to the nearest place in each category, adapted from Bruno et al. (2024).

## Stack

| Part | Tools |
| --- | --- |
| Front end | React 19, Vite, Leaflet with react-leaflet, Atkinson Hyperlegible font |
| Back end | Python, FastAPI, Shapely |
| Data | OpenStreetMap via OSMnx and the Overpass API |
| Map tiles | Stadia Maps, OSM Bright style |
| Hosting | Render: a static site, a web service for the API, and Key Value (Redis) for rate limits |
| Automation | GitHub Actions: monthly data refresh |
| Tests | pytest (50 tests) |

## Project layout

```
client/                    React site
  src/App.jsx              state, requests, and layout
  src/api.js               API address and request helper
  src/components/          map, results panel, category rows, place markers
  src/data/                categories, Manhattan boundary
  src/styles/              tokens, base, layout, panel, and map CSS
server/                    FastAPI API
  main.py                  routes, caching, timing
  rate_limit.py            per-visitor rate limit, in Redis or memory
  graph.py                 walking graph, grid index, Dijkstra
  walk_area.py             builds the shaded walking area
  amenities.py             which places a walk reaches
  scoring.py               the 0–100 score
  scripts/                 downloads (graph, water, places) and the data check
  data/                    the downloaded data (committed)
  test_*.py                tests
render.yaml                Render setup for all three services
.github/workflows/         monthly data refresh
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

## API

All routes take `lat`, `lng`, and optionally `minutes` (default 15, at most 30).

| Route | Returns |
| --- | --- |
| `GET /api/places` | The score, its breakdown by category, and the places within reach, closest first |
| `GET /api/area` | The walking area as a GeoJSON geometry |
| `GET /api/reachable` | Both of the above in one response |
| `GET /api/nearest-node` | The graph node closest to a point |
| `GET /api/graph/info` | Node and segment counts |
| `GET /api/health` | Whether the server is up and the graph is loaded |

The site requests `/api/places` and `/api/area` at the same time, so the panel fills in while the slower area is still being built. Recent results are cached by start node. Each visitor gets 30 searches a minute per route; over that, the API returns 429 with a `Retry-After` header and the panel says how many seconds to wait. On Render the counts are kept in a free Redis-compatible Key Value instance, so they survive the API sleeping; locally they are kept in memory (`server/rate_limit.py`).

Every search prints its timing to the server log, for example `/api/places nearest 1 ms, search 3 ms, places 1 ms (total 5 ms)`, and sends it in a `Server-Timing` header, visible in Chrome's DevTools under Network > Timing.

## Rebuild the data

The data in `server/data/` is committed. A GitHub Actions job (`.github/workflows/refresh-data.yml`) rebuilds it on the 1st of every month: it downloads everything again, checks that no count dropped by more than 15% (`server/scripts/check_data.py`), runs the tests, and commits the new data, which makes Render redeploy. Run it by hand from the repo's **Actions** tab under **Refresh map data**. Its results table is on the run's summary page.

To rebuild by hand:

```bash
cd server
source .venv/bin/activate
pip install -r requirements-build.txt
python scripts/build_graph.py      # walking network
python scripts/build_water.py      # lakes and ponds
python scripts/build_amenities.py  # places
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

The tests cover Dijkstra on small made-up graphs, the grid index against checking every node, the walking area (block interiors filled, nothing over the Hudson, Harlem Meer, or the Reservoir), places and scoring, the API routes, and the rate limit (with a stand-in for Redis).

## Deploy (Render, free plan)

`render.yaml` defines three services, created together in the Render dashboard under **New > Blueprint**:

- **nyc-15min-api**: the FastAPI server. 512 MB of memory and 0.1 CPU. It sleeps after 15 minutes without visits; the site shows "Waking up the server" while it starts again.
- **nyc-15min**: the built React site, served as static files. Always on.
- **nyc-15min-limits**: a free Key Value (Redis-compatible) instance for rate-limit counts, reachable only from the API.

Set these in each service's **Environment** page:

| Service | Variable | Value |
| --- | --- | --- |
| nyc-15min-api | `ALLOWED_ORIGINS` | The site's address, e.g. `https://nyc-15min.onrender.com` |
| nyc-15min | `VITE_API_URL` | The API's address, e.g. `https://nyc-15min-api.onrender.com` |

Vite builds `VITE_API_URL` into the site, so changing it needs a new deploy of the site. When a change touches both the API and the site, wait for the API to finish deploying before testing, since the site finishes first.

On the live site, Stadia Maps allows tiles by checking the site's domain, which you register under **Authentication Configuration** in the Stadia dashboard. No key is shipped to the browser.

## Design and accessibility

- Mobile first: on phones the results sit in a bottom sheet over a full-screen map; from 768 px up they move to a side panel.
- Text contrast is at least 4.5:1 (WCAG 1.4.3), and every category color is at least 5:1 under white text.
- Categories have letters as well as colors (G, T, Rx, +, P, S), so color is never the only cue (WCAG 1.4.1).
- Buttons and rows are at least 44 px tall, and keyboard focus is always visible.
- Score changes are announced to screen readers, and animations respect the reduced-motion setting.

Not yet supported: choosing a point by keyboard. An address search would fix that.

## Data and credits

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- Map tiles © [Stadia Maps](https://stadiamaps.com/attribution/) and © [OpenMapTiles](https://openmaptiles.org/).
- Manhattan boundary from Code for Germany's [Click That 'Hood](https://github.com/codeforgermany/click_that_hood).
- Scoring sources: Walk Score's methodology; Yang et al. (2023), "Walkability Measurement of 15-Minute Community Life Circle in Shanghai," *Land* 12(1); Bruno et al. (2024), "A universal framework for inclusive 15-minute cities," *Nature Cities*.
