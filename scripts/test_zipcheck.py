"""Tests for scripts/zipcheck.py. Run: make test-zipcheck"""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zipcheck import check, forbidden  # noqa: E402


def make_zip(tmp_path, names, pad=0):
    p = tmp_path / "sub.zip"
    with zipfile.ZipFile(p, "w") as z:
        for n in names:
            z.writestr(n, "x" * pad if pad and n.endswith(".bin") else "x")
    return p


def test_seed_inputs_allowed_and_forbidden_entries_rejected(tmp_path):
    ok = make_zip(tmp_path, ["landlens/README.md", "landlens/.env.example", "landlens/seed_inputs/osm/kuda.osm.pbf",
                             "landlens/seed_inputs/embeddings.dump", "landlens/seed_inputs/docs/plan.pdf"])
    violations, warnings, n = check(ok)
    assert violations == [] and n == 5 and not warnings
    for bad in ["landlens/.env", "landlens/api/.env.local", "landlens/data/osm/x.pbf", "data/docs/plan.pdf",
                "landlens/pgdata/base/1", "wal_archive/0001", "landlens/data/"]:
        assert forbidden(bad), bad
    assert not forbidden("landlens/seed_inputs/metadata.json")


def test_missing_seed_inputs_and_size_warnings(tmp_path, monkeypatch):
    import zipcheck as zc

    p = make_zip(tmp_path, ["landlens/README.md"])
    violations, warnings, _ = check(p)
    assert not violations and any("no seed_inputs" in w for w in warnings)
    monkeypatch.setattr(zc, "WARN_BYTES", 10)
    _, warnings, _ = check(p)
    assert any("> 100 MB" in w for w in warnings)


def test_unreadable_zip(tmp_path):
    p = tmp_path / "bad.zip"
    p.write_text("not a zip")
    assert check(p)[0] and check(tmp_path / "missing.zip")[0]
