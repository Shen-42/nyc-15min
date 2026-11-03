"""Download the map data the server needs from the repo's GitHub Releases (card 15).

Run from the server folder (standard library only):
    python scripts/get_data.py

The data for all five boroughs is about 50 MB and replaced every month, so
it isn't kept in git. The monthly refresh job (refresh-data.yml) uploads it
to a release, and data-release.json, which is in git, names that release and
each file's SHA-256 fingerprint. This script downloads every file that's
missing or different, and checks each one against its fingerprint. Render's
build, the test job, and your computer all run it.

Without data-release.json, it leaves data/ as it is.

The refresh job also uses it to write data-release.json:
    python scripts/get_data.py --pin data-2026-12-01-42
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
DATA = SERVER_DIR / "data"
RELEASE_FILE = SERVER_DIR / "data-release.json"
# On GitHub Actions this is set to the repo the job runs in.
REPO = os.environ.get("GITHUB_REPOSITORY", "Shen-42/nyc-15min")
BASE_URL = f"https://github.com/{REPO}/releases/download"
# The files the server and the tests read.
GRID_FILES = [f"grid-{b}.json" for b in ("bronx", "brooklyn", "manhattan", "queens", "staten-island")]
FILES = ["walk_graph.npz", "amenities.json", "parks.json", "water.json", "ramps.json", *GRID_FILES]
TRIES = 4


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url, path):
    """Download url to path, retrying with growing waits (5, 10, 20 s)."""
    partial = path.with_name(path.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "nyc-15min get_data.py"})
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as out:
                while block := response.read(1 << 20):
                    out.write(block)
            return partial
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            if attempt == TRIES - 1:
                raise
            wait = 5 * 2**attempt
            print(f"  {err}. Trying again in {wait} s")
            time.sleep(wait)


def get():
    if not RELEASE_FILE.exists():
        print(f"No {RELEASE_FILE.name}, so using the files already in {DATA}.")
        return
    release = json.loads(RELEASE_FILE.read_text())
    tag = release["tag"]
    print(f"Map data from release {tag} (built {release.get('built', '?')})")
    DATA.mkdir(exist_ok=True)
    for name, info in release["files"].items():
        path = DATA / name
        if path.exists() and sha256(path) == info["sha256"]:
            print(f"  {name}: up to date")
            continue
        url = f"{BASE_URL}/{tag}/{name}"
        print(f"  {name}: downloading {info['bytes'] / 1e6:.1f} MB")
        partial = download(url, path)
        if sha256(partial) != info["sha256"]:
            partial.unlink()
            sys.exit(f"{name} from {url} doesn't match its fingerprint in {RELEASE_FILE.name}. Not using it.")
        os.replace(partial, path)
    print("Map data ready.")


def pin(tag):
    """Write data-release.json for the files now in data/, uploaded as release `tag`."""
    missing = [name for name in FILES if not (DATA / name).exists()]
    if missing:
        sys.exit(f"Missing from {DATA}: {', '.join(missing)}")
    RELEASE_FILE.write_text(json.dumps({
        "tag": tag,
        "built": date.today().isoformat(),
        "files": {name: {"sha256": sha256(DATA / name), "bytes": (DATA / name).stat().st_size} for name in FILES},
    }, indent=2) + "\n")
    print(f"Wrote {RELEASE_FILE} for release {tag}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pin", metavar="TAG", help="write data-release.json for the files in data/, uploaded as release TAG")
    args = parser.parse_args()
    pin(args.pin) if args.pin else get()
