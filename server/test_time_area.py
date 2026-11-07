import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from time_area import cut_path  # noqa: E402


def test_cut_path_halfway_along_a_bend():
    # An L-shaped path: 100 m east, then 100 m north. Half of it ends at the corner.
    path = [(0, 0), (100, 0), (100, 100)]
    assert cut_path(path, 0.5) == [(0, 0), (100, 0)]
    assert cut_path(path, 0.75) == [(0, 0), (100, 0), (100, 50)]
    assert cut_path(path, 1.0)[-1] == (100, 100)
