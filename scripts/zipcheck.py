"""Inspect the LandLens submission zip (`make zip` runs this as its zip_contents check).

Allowed: anything, including seed_inputs/ (OSM export, projects GeoJSON + sources, PDFs, embeddings dump).
Rejected: any .env file (except .env.example), any data/ directory entry, Postgres volume directories
(pgdata, wal_archive). Warns, without failing, when the zip is larger than 100 MB.

Usage: python3 scripts/zipcheck.py <path-to-zip>   (exit 0 = ok, 1 = forbidden entries or unreadable zip)
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

WARN_BYTES = 100 * 1024 * 1024
FORBIDDEN_DIRS = {"data", "pgdata", "wal_archive"}


def forbidden(name: str) -> str | None:
    parts = [p for p in name.split("/") if p]
    if not parts:
        return None
    base = parts[-1]
    if base.startswith(".env") and base != ".env.example":
        return "secret file (.env)"
    dirs = parts if name.endswith("/") else parts[:-1]
    for d in dirs:
        if d in FORBIDDEN_DIRS:
            return f"forbidden directory {d}/"
    if base in FORBIDDEN_DIRS and name.endswith("/"):
        return f"forbidden directory {base}/"
    return None


def check(path: Path) -> tuple[list[str], list[str], int]:
    """Return (violations, warnings, entry_count)."""
    if not path.exists():
        return [f"zip not found: {path}"], [], 0
    try:
        names = zipfile.ZipFile(path).namelist()
    except zipfile.BadZipFile as exc:
        return [f"not a valid zip: {exc}"], [], 0
    violations = [f"{n}: {why}" for n in names if (why := forbidden(n))]
    warnings = []
    size = path.stat().st_size
    if size > WARN_BYTES:
        warnings.append(f"WARNING: zip is {size / 1024 / 1024:.1f} MB (> 100 MB); check what seed_inputs/ contains")
    if not any(n.split("/")[0] == "seed_inputs" or "/seed_inputs/" in f"/{n}" for n in names):
        warnings.append("WARNING: no seed_inputs/ in the zip; a fresh machine cannot seed without downloads")
    return violations, warnings, len(names)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    violations, warnings, count = check(Path(argv[0]))
    for w in warnings:
        print(w)
    for v in violations:
        print(f"FORBIDDEN: {v}")
    if not violations:
        print(f"{count} entries; no .env, data/, pgdata or wal_archive")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
