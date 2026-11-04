"""Time the live site (card 15): cold start, first and repeat search, and
what the score map downloads. Standard library only. From the server folder:
    python scripts/time_live.py

For a real cold start, run it when nobody has used the site for 20 minutes,
so the free API has gone to sleep. Searches report the server's own timing
(the Server-Timing header) next to the time the whole request took from here.
"""

import json
import sys
import time
import urllib.request

API = "https://nyc-15min-api.onrender.com"
SITE = "https://nyc-15min.onrender.com"
# One spot per borough: Times Square, Crown Heights, Flushing, Parkchester, New Springville.
SPOTS = {
    "Manhattan": (40.7580, -73.9855),
    "Brooklyn": (40.6782, -73.9442),
    "Queens": (40.7590, -73.8303),
    "Bronx": (40.8448, -73.8648),
    "Staten Island": (40.6437, -74.0764),  # St. George
}


def get(url, gzip=False):
    """(seconds, status, headers, body bytes as sent)."""
    request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"} if gzip else {})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as res:
            body = res.read()
            return time.perf_counter() - start, res.status, res.headers, body
    except urllib.error.HTTPError as err:
        return time.perf_counter() - start, err.code, err.headers, err.read()


def server_ms(headers):
    """Total of the Server-Timing steps, e.g. "nearest;dur=0.3, search;dur=1.1"."""
    steps = [part.split(";dur=") for part in (headers.get("Server-Timing") or "").split(", ") if ";dur=" in part]
    return sum(float(ms) for _, ms in steps), ", ".join(f"{name} {float(ms):.0f}" for name, ms in steps)


def main():
    print("Cold start (asleep if unused for 15+ minutes)")
    seconds, status, _, _ = get(f"{API}/api/health")
    print(f"  /api/health answered {status} in {seconds:.1f} s")

    print("\nSearches: total time from here, then the server's own steps in ms")
    for borough, (lat, lng) in SPOTS.items():
        for attempt in ("first", "repeat"):
            for route in ("places", "area"):
                seconds, status, headers, body = get(f"{API}/api/{route}?lat={lat}&lng={lng}")
                total, steps = server_ms(headers)
                print(f"  {borough:13} {attempt:6} /api/{route:6} {status}  {seconds * 1000:6.0f} ms total, server {total:5.1f} ms ({steps})")
                if status != 200:
                    print(f"    {json.loads(body).get('detail')}")

    print("\nScore map files (compressed, as sent)")
    _, status, headers, body = get(f"{SITE}/grid/index.json")
    if status != 200:
        sys.exit(f"  /grid/index.json answered {status}")
    index = json.loads(body)
    print(f"  index.json: Cache-Control {headers.get('Cache-Control')!r}, release {index.get('tag')}")
    total = 0
    for borough, path in index["files"].items():
        seconds, status, headers, body = get(f"{SITE}/grid/{path}", gzip=True)
        total += len(body)
        print(f"  {borough:13} {len(body) / 1000:5.0f} KB in {seconds:.1f} s ({headers.get('Content-Encoding') or 'not compressed'}), "
              f"Cache-Control {headers.get('Cache-Control')!r}")
    print(f"  all five: {total / 1000:.0f} KB")


if __name__ == "__main__":
    main()
