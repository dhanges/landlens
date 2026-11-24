"""Dependency audit (SECURITY.md): every pinned Python dependency (api/pyproject.toml) and every package in the web
lockfile (web/package-lock.json), checked against the OSV database. Usage: make audit (needs network).
Sends only package names and versions to api.osv.dev. Exits 1 if any known vulnerability is found."""

from __future__ import annotations

import json
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def osv(queries: list[dict]) -> list[dict]:
    out = []
    for i in range(0, len(queries), 500):
        req = urllib.request.Request("https://api.osv.dev/v1/querybatch", data=json.dumps({"queries": queries[i:i + 500]}).encode(),
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out += json.load(r)["results"]
    return out


def main() -> int:
    py = tomllib.loads((ROOT / "api" / "pyproject.toml").read_text())["project"]
    pins = py["dependencies"] + [d for ds in py.get("optional-dependencies", {}).values() for d in ds]
    pkgs = []
    for d in pins:
        m = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;]+)", d)
        if m:
            pkgs.append(("PyPI", m.group(1), m.group(2)))
    lock = json.loads((ROOT / "web" / "package-lock.json").read_text())
    for path, meta in lock.get("packages", {}).items():
        if path.startswith("node_modules/") and meta.get("version"):
            pkgs.append(("npm", path.split("node_modules/")[-1], meta["version"]))
    res = osv([{"package": {"name": n, "ecosystem": e}, "version": v} for e, n, v in pkgs])
    bad = [(e, n, v, [x["id"] for x in r.get("vulns", [])]) for (e, n, v), r in zip(pkgs, res, strict=True) if r.get("vulns")]
    py_n = sum(e == "PyPI" for e, *_ in pkgs)
    print(f"checked {py_n} pinned Python packages and {len(pkgs) - py_n} npm packages (lockfile) against OSV")
    for e, n, v, ids in bad:
        print(f"  VULNERABLE {e} {n}=={v}: {', '.join(ids)}")
    print("no known vulnerabilities" if not bad else f"{len(bad)} vulnerable package(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
