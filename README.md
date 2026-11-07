# NYC 15-Minute City Explorer

[![Tests](https://github.com/Shen-42/nyc-15min/actions/workflows/tests.yml/badge.svg)](https://github.com/Shen-42/nyc-15min/actions/workflows/tests.yml)
[![Refresh map data](https://github.com/Shen-42/nyc-15min/actions/workflows/refresh-data.yml/badge.svg)](https://github.com/Shen-42/nyc-15min/actions/workflows/refresh-data.yml)
[![Live site](https://img.shields.io/badge/live-nyc15min.com-2ea44f)](https://www.nyc15min.com)

**Could you get through your week in New York on foot?** Click any spot in the five boroughs and see everywhere you can walk in 15 minutes, the groceries, pharmacies, doctors, parks, schools, and subway stations inside that walk, and a 0–100 score for how much of daily life is close by.

**[Try it here](https://www.nyc15min.com)**. No sign-up needed.

> The API runs on a free plan and sleeps when nobody's using it, so the first search can take up to a minute. After that it answers in milliseconds.

## Why this exists

The idea comes from Carlos Moreno, a professor at the Sorbonne, who proposed the [15-minute city](https://en.wikipedia.org/wiki/15-minute_city): a neighborhood where you can reach food, health care, school, parks, and transit within a 15-minute walk or bike ride. Paris took it up in 2020 under Mayor Anne Hidalgo, and other cities have followed.

This project puts that test in anyone's hands. Residents, students, and researchers can check how well a block works on foot, compare neighborhoods, and see who gets left out. The gaps are not spread evenly. In the November 2026 data, 16 of Manhattan's 4,667 lived-in 100 m squares have no grocery store within a 15-minute walk; on Staten Island it's 4,266 of 9,860. In Queens, 14,046 of 21,487 squares are more than 15 minutes on foot from a subway station. Wheelchair mode shows how much further a missing curb ramp pushes things away.

## What you can do

- **Click anywhere and see your walk.** The shaded area follows real streets and paths, not a circle drawn around you.
- **Score what matters to you.** Mark each kind of place as essential or not needed, or start from Student, Parent, or Retiree.
- **Pick a time.** Slide to 11 pm and only places open then count.
- **Switch to wheelchair.** A slower pace, extra time at corners without curb ramps, and those corners marked on the map.
- **Look at the whole city.** A heat map scores every 100 m of the five boroughs, and the gap finder shows where there's no pharmacy (or grocery, or subway) in reach and the best spot in each borough to add one. A spot's score also says how it ranks in its borough and the city.
- **Save places** with an optional account.

## How it works

The five boroughs' streets and paths from OpenStreetMap become a graph of 344,000 points, kept as NumPy arrays. When you click, the server runs Dijkstra's algorithm (scipy's) outward at walking speed until it hits 15 minutes, draws the area it reached, and scores the places inside it. A search takes about a millisecond. The data refreshes itself every month and is published as a [GitHub release](https://github.com/Shen-42/nyc-15min/releases).

The full story, with the scoring formula and its sources, is in [How it works](docs/how-it-works.md).

## Run it locally

You need Node.js 20.19+ and Python 3.11+.

```bash
# Terminal 1: the API
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/get_data.py   # the map data, about 50 MB
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
| Live site | https://www.nyc15min.com |
| API health check | https://nyc-15min-api.onrender.com/api/health |
| How it works | [docs/how-it-works.md](docs/how-it-works.md) |
| Development (setup, tests, data, deploy) | [docs/development.md](docs/development.md) |
| API reference | [docs/api.md](docs/api.md) |
| Security | [docs/security.md](docs/security.md) |
| Test runs | [GitHub Actions: Tests](https://github.com/Shen-42/nyc-15min/actions/workflows/tests.yml) |
| Data refresh runs | [GitHub Actions: Refresh map data](https://github.com/Shen-42/nyc-15min/actions/workflows/refresh-data.yml) |
| Map data | [GitHub releases](https://github.com/Shen-42/nyc-15min/releases) (`data-...`) |

## Built with

React, Vite, and Leaflet on the front; Python, FastAPI, NumPy, scipy, and Shapely behind it; Supabase for accounts; hosted on Render.

## Data and credits

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- Opening hours parsed with [opening-hours-py](https://pypi.org/project/opening-hours-py/) by Rémi Dupré.
- Curb ramps from NYC DOT's Pedestrian Ramp Locations on [NYC Open Data](https://data.cityofnewyork.us/d/ufzp-rrqu).
- Wheelchair speed: Cooper et al. (2011) and Tolerico et al. (2007), via the [SCIRE Project](https://scireproject.com/evidence/wheeled-mobility-and-seating-equipment/manual-wheelchairs/wheelchair-use/wheelchair-usage/).
- Map tiles © [Stadia Maps](https://stadiamaps.com/attribution/) and © [OpenMapTiles](https://openmaptiles.org/).
- Borough shorelines from the NYC Department of City Planning, via Code for Germany's [Click That 'Hood](https://github.com/codeforgermany/click_that_hood); the city's boundary through the water from OpenStreetMap.
- Scoring sources: Walk Score's methodology; Yang et al. (2023), "Walkability Measurement of 15-Minute Community Life Circle in Shanghai," *Land* 12(1); Bruno et al. (2024), "A universal framework for inclusive 15-minute cities," *Nature Cities*.
