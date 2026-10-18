"""FastAPI back end for the NYC 15-Minute City Explorer.

Run from this folder with:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI

app = FastAPI(title="NYC 15-Minute City Explorer API", version="0.1.0")


@app.get("/api/health")
def health():
    """Lets the front end check that the server is up."""
    return {"status": "ok", "version": app.version}


# Card 3 adds the walking graph and card 4 adds the search, for example:
# @app.get("/api/reachable")
# def reachable(lat: float, lon: float, minutes: int = 15): ...
