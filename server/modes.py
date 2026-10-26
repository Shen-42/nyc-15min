"""Ways of getting around (card 11): walking, or a manual wheelchair."""

import json
from pathlib import Path

from graph import WALK_SPEED_M_PER_MIN

# A manual wheelchair in everyday use averages about 0.8 m/s, or 48 m a
# minute: 0.77 m/s in Cooper et al. (2011), 0.79 m/s at home in Tolerico
# et al. (2007). Walking is 80 m a minute.
WHEELCHAIR_SPEED_M_PER_MIN = 48

# Extra minutes for passing a corner with no curb ramp: roughly the detour
# to the next corner that has one. A judgment call, not a measured value.
NO_RAMP_PENALTY_MIN = 3

SPEEDS = {"walk": WALK_SPEED_M_PER_MIN, "wheelchair": WHEELCHAIR_SPEED_M_PER_MIN}


def parse_mode(text):
    """ "walk" or "wheelchair". Raises ValueError with a message for the person using the site."""
    mode = (text or "walk").strip().lower()
    if mode not in SPEEDS:
        raise ValueError(f'Unknown way of getting around "{text}". Use walk or wheelchair.')
    return mode


def load_no_ramp_nodes(path):
    """Graph nodes at street corners with no curb ramp nearby (from scripts/build_ramps.py)."""
    return set(json.loads(Path(path).read_text())["no_ramp_nodes"])
