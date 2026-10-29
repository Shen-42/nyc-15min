# NYC 15-Minute City Explorer

Click any point in Manhattan to see everywhere you can walk in 15 minutes, which groceries, pharmacies, doctors, parks, schools, and subway stations fall inside that walk, and a 0–100 score for how much of daily life is within reach. The score can be fitted to what you need, to the hour of the day, and to getting around in a wheelchair.

**Live site:** https://nyc-15min.onrender.com
(The API runs on a free plan and sleeps after 15 minutes without visits. The first search after that can take up to a minute while it wakes.)

## How it works

1. **Walking network.** Manhattan's walkable streets and paths come from OpenStreetMap, downloaded once with OSMnx and saved as a graph: 36,790 nodes and 57,619 segments, each with its length in meters and the shape of curved paths. The graph also lists its street corners and crosswalk ends, for wheelchair mode (step 9).
2. **Nearest street point.** A click snaps to the nearest graph node using a grid index (0.002° cells, searched in growing rings), about 20 times faster than checking every node. Clicks on water, inside a park (nobody lives there; outlines from `server/data/parks.json`), or more than 150 m from any path are turned away with a message.
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

7. **Your needs.** The weights above are the defaults. Under "Your needs" in the panel, anyone can start from a preset (Student, Parent, Retiree) and set each category to Not needed, Nice to have, Important, or Essential, which are weights 0 to 3. A category set to Not needed is still listed but is left out of the score and of proximity time. Changing a setting re-requests only the score, not the shaded area, and the browser remembers the choice.

   | Preset | Groceries | Subway | Pharmacies | Doctors | Parks | Schools |
   | --- | --- | --- | --- | --- | --- | --- |
   | Default | 3 | 2 | 1 | 1 | 1 | 1 |
   | Student | 3 | 3 | 1 | 1 | 2 | 0 |
   | Parent | 3 | 2 | 2 | 2 | 3 | 3 |
   | Retiree | 3 | 2 | 3 | 3 | 2 | 0 |

   The presets are my own judgment calls, not survey results.

8. **Time of day.** By default every place counts, whatever its hours. Move the "Open at" slider, or press Now, and the score only counts places open at that hour today, New York time. Hours come from OpenStreetMap's `opening_hours` tag, read on the server with [opening-hours-py](https://pypi.org/project/opening-hours-py/). Closed places leave the map, and the panel lists them as "Closed at 9 pm" with a count such as "3 of 5 open". Places with no listed hours still count and get a "?" badge. The subway runs all night and schools matter for being nearby, so those two are always counted.

9. **Wheelchair.** "Your needs" starts with how you get around: Walking or Wheelchair. In a wheelchair the search moves at 48 m a minute instead of 80, about 0.8 m/s, the everyday average in Cooper et al. (2011) and Tolerico et al. (2007). Each street corner or crosswalk end with no curb ramp within 30 m adds 3 minutes, roughly the detour to the next corner that has one. That penalty is my estimate, not a measured value. Ramps come from NYC DOT's [Pedestrian Ramp Locations](https://data.cityofnewyork.us/d/ufzp-rrqu). Corners without a ramp show on the map as dark diamonds with "!", and the line under the score says how many are in reach. The penalty applies whenever the search passes such a corner, even where it walks along the street rather than crossing it.

10. **All of Manhattan.** A script (`server/scripts/build_grid.py`) lays a 100 m grid over the island, about 5,450 squares on land, and runs the same 15-minute walk from each one, saving every category's score. It takes under a minute and runs after each monthly data refresh. Nobody lives in a park, so squares that lie mostly inside a park outline from OpenStreetMap (saved by `build_amenities.py` as `server/data/parks.json`) are left out of the rank, the gaps, and the search for a best spot. On the gap finder, every park outline and lake is cut out of the image, and color also fades wherever most nearby squares are park (such as the Henry Hudson Parkway's strip through Inwood Hill Park), so no gap is ever shown in a park. With the grid:
    - Each clicked spot gets a rank under its score, such as "Better than 70% of Manhattan", using the same weights as the score. The grid was scored walking at any time, so the rank only shows for those settings.
    - **Score map** (under "Map view"): a smooth heat map of the score with your weights, colored with the viridis palette, which stays in order for color-blind viewers. The squares are data points, not drawn shapes: the browser (`client/src/data/gridImage.js`) sets each pixel to a weighted average of the nearby squares' scores, with weights falling off along a Gaussian curve (sigma 120 m), and divides by the total weight so the shore and small parks don't fade. The image is cut to Manhattan's shoreline, with lakes cut out. Parks have no score of their own, so they take the colors of the blocks around them: where the normal smoothing has no data, a wider one (sigma 500 m) takes over, which reaches the middle of Central Park without leaving holes. It's rebuilt in about 0.2 seconds when your weights change.
    - **Gap finder**: for one category, the areas with nothing of it within 15 minutes, drawn the same smooth way in the category's color (darker where more nearby squares are gaps), and the one square where a new place would cover the most gap squares, marked with a star. The spot is named by its nearest corner, using the street names in the curb ramp data, or else by the nearest named place. Manhattan has few true gaps. In the October 2026 data, of 4,720 squares outside parks: 15 have no grocery store in reach (11 of them on Roosevelt Island), 83 no subway station (the largest group, 27 squares, on the Lower East Side), 61 no pharmacy (38 in Inwood), and none lack a park.

11. **Accounts (optional).** Searching never needs an account. Signing in, with email and password through [Supabase Auth](https://supabase.com/docs/guides/auth), lets you save places and keep your needs profile across devices.
    - The browser only uses Supabase to sign in. Saves, loads, and deletes go through the API, which checks the sign-in token itself against Supabase's public keys (`server/auth.py`) and filters every query by the signed-in user (`server/store.py`).
    - The two tables (`supabase/schema.sql`) have row-level security on with no policies, so the browser's public key can't read or write them; only the API's secret key can.
    - Two roles. A **user** manages only their own saved places, profile, and account. An **admin**, listed by user id in the API's `ADMIN_USER_IDS` setting, also sees the last week's search counts and can start the monthly data refresh. The server checks the role on every admin request and answers 403 otherwise.
    - Edge cases handled: a session that expires mid-visit is refreshed once, then signs out with a message; signing in before confirming the email offers to resend the link; signing up twice with the same email says the account exists; password reset by email; two tabs editing the same profile (each save names the version it started from, and an out-of-date save is refused with the latest profile, which the page then shows); deleting an account removes its saved places, profile, and sign-in.
    - Free Supabase projects pause after a week without use, so a small GitHub Actions job (`keep-supabase-awake.yml`) queries the database twice a week.

12. **When things go wrong.** Every message appears in one place under the title, in one style, saying what happened and what to do next. Errors that a second try might fix (no connection, a timeout, a server error) come with a **Try again** button, and keyboard focus moves to it; refusals such as a click in a park or too many searches don't, since trying again wouldn't help.
    - Requests give up after 70 seconds, longer than the free API takes to wake up, instead of spinning forever.
    - The shaded area, the slowest request, is tried a second time before the panel says it couldn't be drawn; the score and places still show.
    - A crash in the map or the panel shows a message and a **Reload the page** button in its place, instead of a blank page; the other part keeps working.
    - On the server, any error a route doesn't handle is logged with the request that caused it and answered with a plain message and a short request id (also in the `X-Request-ID` header of every response), so a visitor's report can be matched to the log. FastAPI's own input errors come back as one readable sentence.

## Stack

| Part | Tools |
| --- | --- |
| Front end | React 19, Vite, Leaflet with react-leaflet, Atkinson Hyperlegible font |
| Back end | Python, FastAPI, Shapely, opening-hours-py |
| Data | OpenStreetMap via OSMnx and the Overpass API; NYC Open Data for curb ramps |
| Map tiles | Stadia Maps, OSM Bright style |
| Accounts | Supabase Auth (email and password) and Postgres, through the API |
| Hosting | Render: a static site, a web service for the API, and Key Value (Redis) for rate limits and usage counts |
| Automation | GitHub Actions: monthly data refresh, then scoring the Manhattan grid |
| Tests | pytest |

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

**4. Accounts (optional).** Without these settings the site runs as before, with no sign-in.

1. Create a free project at https://supabase.com. In its **SQL Editor**, run `supabase/schema.sql`.
2. Under **Authentication > URL Configuration**, set the Site URL to the live site and add `http://localhost:5173/**` to the redirect URLs.
3. Copy `client/.env.example` and `server/.env.example` to `client/.env.local` and `server/.env`, and fill in the project URL and keys from **Project Settings > API Keys**. Both files are ignored by git.
4. Start the API with `uvicorn main:app --reload --port 8000 --env-file .env`.
5. To make yourself an admin, sign up on the site, copy your user id from **Authentication > Users** into `ADMIN_USER_IDS`, and restart the API.

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
| `GET /api/me` | The signed-in user's id, email, and role |
| `GET`, `POST /api/saved-places`; `DELETE /api/saved-places/{id}` | The signed-in user's saved places (at most 50) |
| `GET`, `PUT /api/profile` | The signed-in user's needs profile; `PUT` names the version it started from and gets 409 if it's out of date |
| `DELETE /api/account` | Deletes the signed-in user's account and data |
| `GET /api/admin/usage`, `POST /api/admin/refresh` | Admins only: search counts for the last 7 days, and starting the data refresh |
| `GET /api/grid` | Every 100 m square of Manhattan with its category scores, plus each category's gaps and best spot (no `lat`/`lng`) |

`/api/places` and `/api/reachable` also take `weights`, for example `weights=grocery:3,park:3,school:0`. Each weight is a whole number from 0 to 3, and categories left out keep their defaults. An unknown category, a weight out of range, or all weights at 0 returns 422 with a message saying what to fix.

`/api/places` and `/api/reachable` also take `at`, a New York time such as `at=2026-10-26T21:00`. With it, each place gets a `status` (`open`, `closed`, or `unknown`) and closed places are left out of the score.

`/api/places`, `/api/area`, and `/api/reachable` take `mode`, either `walk` (the default) or `wheelchair`. In wheelchair mode `/api/places` also returns `barriers`, the corners in reach with no curb ramp.

`/api/places` returns `score.rank`, the share of Manhattan's grid squares that score lower with the same weights, or `null` in wheelchair mode or with `at` set.

The site requests `/api/places` and `/api/area` at the same time, so the panel fills in while the slower area is still being built. Recent results are cached by start node. Each visitor gets 30 searches a minute per route; over that, the API returns 429 with a `Retry-After` header and the panel says how many seconds to wait. On Render the counts are kept in a free Redis-compatible Key Value instance, so they survive the API sleeping; locally they are kept in memory (`server/rate_limit.py`).

Every search prints its timing to the server log, for example `/api/places nearest 1 ms, search 3 ms, places 1 ms (total 5 ms)`, and sends it in a `Server-Timing` header, visible in Chrome's DevTools under Network > Timing.

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

## Design and accessibility

- Mobile first: on phones the results sit in a bottom sheet over a full-screen map; from 768 px up they move to a side panel. The sheet has three positions: open (settings and categories), peek (just the title and score), and hidden (just the handle, so the whole map shows). Swipe up or down to move between them, or tap the handle to step hidden → peek → open → peek; the handle is a button, so it works by keyboard and screen reader too. Clicking the map brings a hidden sheet back to peek so the new score shows. Whatever is off screen is skipped by Tab.
- Text contrast is at least 4.5:1 (WCAG 1.4.3), and every category color is at least 5:1 under white text.
- Categories have letters as well as colors (G, T, Rx, +, P, S), so color is never the only cue (WCAG 1.4.1).
- Buttons and rows are at least 44 px tall, and keyboard focus is always visible.
- Score changes are announced to screen readers, and animations respect the reduced-motion setting.
- The time and "Your needs" settings start closed, so the panel shows the score and categories first. Their current values show on the closed line, e.g. "Time: Open at 9 pm".
- The hour is a native slider, so arrow keys work, and screen readers read the hour as "9 pm".
- Map markers carry meaning in shape and symbol, not only color: places with no listed hours get a "?" badge, corners without curb ramps are diamonds with "!", and the gap finder's best spot is a star.
- The score map and gap finder are off until chosen under "Map view". While one is on, a box at the top of the panel names it, explains it in words (the legend labels the scale with numbers and both ends in words, and the gap finder names the best spot by its cross streets), and has a "Back to your walk" button. Clicking the map also goes back.

- Account forms have visible labels, fill in from password managers (`autocomplete`), and show each error under its field, announced to screen readers. Dialogs use the native `<dialog>`, so focus stays inside and Escape closes them.
- Deleting an account is set apart in red and takes a second step, where "Keep account" is the default and has the focus.

Not yet supported: choosing a point by keyboard. An address search would fix that.

## Security

- No secrets are in the repo. Keys live in Render's environment settings, GitHub's repository secrets, and git-ignored local files (`server/.env`, `client/.env.local`); the `.env.example` files show the names only. The site holds only Supabase's publishable key, which can't read or write any table.
- No SQL is written by hand. The API reaches the database through Supabase's REST API with every value sent as a parameter: user ids come from a verified sign-in token, saved-place ids must be UUIDs, and everything else is checked before use.
- React escapes all text it renders, including place names from OpenStreetMap and saved-place names. The few map markers built from HTML use fixed strings only.
- The site sends a Content-Security-Policy (set in `render.yaml`) that allows scripts only from itself and connections only to the API, the map tiles, and Supabase. Both the site and the API send `nosniff`, HSTS, and headers that forbid other sites from framing them.
- The API accepts requests only from the site's address (CORS), limits each visitor to 30 searches a minute, and has its interactive docs turned off on Render. The rate limit identifies visitors by the address Cloudflare and Render add to `X-Forwarded-For`, counted from the end of the list, so a made-up header can't get around it.
- Dependabot (`.github/dependabot.yml`) opens a weekly pull request for outdated or vulnerable Python packages, npm packages, and GitHub Actions.

## Data and credits

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- Opening hours parsed with [opening-hours-py](https://pypi.org/project/opening-hours-py/) by Rémi Dupré.
- Curb ramps from NYC DOT's Pedestrian Ramp Locations on [NYC Open Data](https://data.cityofnewyork.us/d/ufzp-rrqu).
- Wheelchair speed: Cooper et al. (2011) and Tolerico et al. (2007), via the [SCIRE Project](https://scireproject.com/evidence/wheeled-mobility-and-seating-equipment/manual-wheelchairs/wheelchair-use/wheelchair-usage/).
- Map tiles © [Stadia Maps](https://stadiamaps.com/attribution/) and © [OpenMapTiles](https://openmaptiles.org/).
- Manhattan boundary from Code for Germany's [Click That 'Hood](https://github.com/codeforgermany/click_that_hood).
- Scoring sources: Walk Score's methodology; Yang et al. (2023), "Walkability Measurement of 15-Minute Community Life Circle in Shanghai," *Land* 12(1); Bruno et al. (2024), "A universal framework for inclusive 15-minute cities," *Nature Cities*.
