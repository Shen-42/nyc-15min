# NYC 15-Minute City Explorer

[![Tests](https://github.com/Shen-42/nyc-15min/actions/workflows/tests.yml/badge.svg)](https://github.com/Shen-42/nyc-15min/actions/workflows/tests.yml)
[![Refresh map data](https://github.com/Shen-42/nyc-15min/actions/workflows/refresh-data.yml/badge.svg)](https://github.com/Shen-42/nyc-15min/actions/workflows/refresh-data.yml)
[![Live site](https://img.shields.io/badge/live-nyc--15min.onrender.com-2ea44f)](https://nyc-15min.onrender.com)

**Could you get through your week in Manhattan on foot?** Click any spot on the map and see everywhere you can walk in 15 minutes, the groceries, pharmacies, doctors, parks, schools, and subway stations inside that walk, and a 0–100 score for how much of daily life is close by.

**[Try it here](https://nyc-15min.onrender.com)**. No sign-up needed.

> The API runs on a free plan and sleeps when nobody's using it, so the first search can take up to a minute. After that it answers in milliseconds.

## What you can do

- **Click anywhere and see your walk.** The shaded area follows real streets and paths, not a circle drawn around you.
- **Score what matters to you.** Mark each kind of place as essential or not needed, or start from Student, Parent, or Retiree.
- **Pick a time.** Slide to 11 pm and only places open then count.
- **Switch to wheelchair.** A slower pace, extra time at corners without curb ramps, and those corners marked on the map.
- **Look at the whole island.** A heat map scores all of Manhattan, and the gap finder shows where there's no pharmacy (or grocery, or subway) in reach and the best spot to add one.
- **Save places** with an optional account.

## How it works

Manhattan's streets and paths from OpenStreetMap become a graph of 36,790 points. When you click, the server runs Dijkstra's algorithm outward at walking speed until it hits 15 minutes, draws the area it reached, and scores the places inside it. A search takes a few milliseconds. The data refreshes itself every month.

The full story, with the scoring formula and its sources, is in [How it works](docs/how-it-works.md).

## Run it locally

You need Node.js 20.19+ and Python 3.11+.

```bash
# Terminal 1: the API
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2: the site
cd client
npm install
npm run dev
```

Open http://localhost:5173. For the map key, accounts, tests, and deploying, see [Development](docs/development.md).

## Links

| | |
| --- | --- |
| Live site | https://nyc-15min.onrender.com |
| API health check | https://nyc-15min-api.onrender.com/api/health |
| How it works | [docs/how-it-works.md](docs/how-it-works.md) |
| Development (setup, tests, data, deploy) | [docs/development.md](docs/development.md) |
| API reference | [docs/api.md](docs/api.md) |
| Security | [docs/security.md](docs/security.md) |
| Test runs | [GitHub Actions: Tests](https://github.com/Shen-42/nyc-15min/actions/workflows/tests.yml) |
| Data refresh runs | [GitHub Actions: Refresh map data](https://github.com/Shen-42/nyc-15min/actions/workflows/refresh-data.yml) |

## Built with

React, Vite, and Leaflet on the front; Python, FastAPI, and Shapely behind it; Supabase for accounts; hosted on Render.

## Data and credits

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- Opening hours parsed with [opening-hours-py](https://pypi.org/project/opening-hours-py/) by Rémi Dupré.
- Curb ramps from NYC DOT's Pedestrian Ramp Locations on [NYC Open Data](https://data.cityofnewyork.us/d/ufzp-rrqu).
- Wheelchair speed: Cooper et al. (2011) and Tolerico et al. (2007), via the [SCIRE Project](https://scireproject.com/evidence/wheeled-mobility-and-seating-equipment/manual-wheelchairs/wheelchair-use/wheelchair-usage/).
- Map tiles © [Stadia Maps](https://stadiamaps.com/attribution/) and © [OpenMapTiles](https://openmaptiles.org/).
- Manhattan boundary from Code for Germany's [Click That 'Hood](https://github.com/codeforgermany/click_that_hood).
- Scoring sources: Walk Score's methodology; Yang et al. (2023), "Walkability Measurement of 15-Minute Community Life Circle in Shanghai," *Land* 12(1); Bruno et al. (2024), "A universal framework for inclusive 15-minute cities," *Nature Cities*.
