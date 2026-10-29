# API

Base URL: https://nyc-15min-api.onrender.com

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

[Back to the README](../README.md)
