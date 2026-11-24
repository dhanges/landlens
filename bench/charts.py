"""Benchmark charts for the report (spec 2.19), as standalone SVG with no dependencies: python3 bench/charts.py

- q<N>.svg       per query: median ms per variant, SF1 and SF5 side by side (log scale), from results/sf1.csv / sf5.csv
- overview.svg   the best and the baseline variant of each query at SF1 and SF5 (log scale)
- tiles.svg      dense parcel tile size before / after migration 014 (results/tile_weight_sf1.csv)
- pgbench.svg    screener throughput at 8 and 32 clients (results/pgbench_*.csv)
Colours follow web/DESIGN.md (sage = SF1 / after, walnut = SF5 / before).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES, OUT = HERE / "results", HERE / "charts"
SAGE, WALNUT, MUTED, BORDER, TEXT = "#3F5E4A", "#7A5A40", "#62675F", "#E3DED4", "#1E2420"
FONT = "font-family='Schibsted Grotesk, Helvetica, Arial, sans-serif'"
MONO = "font-family='IBM Plex Mono, Menlo, monospace'"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read(sf: int) -> dict[tuple[str, str], float]:
    f = RES / f"sf{sf}.csv"
    if not f.exists():
        return {}
    out = {}
    for r in csv.DictReader(f.open()):
        try:
            out[(r["query"], r["variant"])] = float(r["median_ms"])
        except (ValueError, KeyError):
            pass
    return out


def hbars(title: str, subtitle: str, rows: list[tuple[str, list[float | None]]], series: list[tuple[str, str]],
          unit: str = "ms", log: bool = True) -> str:
    """Horizontal grouped bars: rows of (label, [value per series])."""
    vals = [v for _, vs in rows for v in vs if v]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if log:
        lo_e, hi_e = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
        if lo_e == hi_e:
            hi_e += 1
        scale = lambda v: (math.log10(v) - lo_e) / (hi_e - lo_e)  # noqa: E731
        ticks = [10 ** e for e in range(lo_e, hi_e + 1)]
    else:
        top = hi * 1.1
        scale = lambda v: v / top  # noqa: E731
        ticks = [top * i / 4 for i in range(5)]
    label_w, plot_w, bar_h, gap = 250, 520, 14, 10
    group_h = bar_h * len(series) + gap
    h = 90 + group_h * len(rows) + 40
    w = label_w + plot_w + 120
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>",
         f"<rect width='{w}' height='{h}' fill='#FFFFFF'/>",
         f"<text x='20' y='30' {FONT} font-size='18' fill='{TEXT}'>{esc(title)}</text>",
         f"<text x='20' y='50' {FONT} font-size='12' fill='{MUTED}'>{esc(subtitle)}</text>"]
    x0, y0 = label_w, 70
    for t in ticks:
        x = x0 + scale(t) * plot_w
        s.append(f"<line x1='{x:.1f}' y1='{y0}' x2='{x:.1f}' y2='{h - 40}' stroke='{BORDER}'/>")
        lab = f"{t:g}" if log else f"{t:,.0f}"
        s.append(f"<text x='{x:.1f}' y='{h - 24}' {MONO} font-size='10' fill='{MUTED}' text-anchor='middle'>{lab}</text>")
    s.append(f"<text x='{x0 + plot_w / 2:.0f}' y='{h - 8}' {FONT} font-size='11' fill='{MUTED}' text-anchor='middle'>"
             f"{esc(unit)}{' (log scale)' if log else ''}</text>")
    for i, (label, vs) in enumerate(rows):
        gy = y0 + 10 + i * group_h
        s.append(f"<text x='{x0 - 10}' y='{gy + group_h / 2 - 2:.0f}' {FONT} font-size='12' fill='{TEXT}' "
                 f"text-anchor='end'>{esc(label)}</text>")
        for j, ((_, colour), v) in enumerate(zip(series, vs, strict=True)):
            y = gy + j * bar_h
            if v:
                bw = max(1.5, scale(v) * plot_w) if (not log or v >= ticks[0]) else 1.5
                s.append(f"<rect x='{x0}' y='{y}' width='{bw:.1f}' height='{bar_h - 3}' fill='{colour}' rx='2'/>")
                s.append(f"<text x='{x0 + bw + 6:.1f}' y='{y + bar_h - 5}' {MONO} font-size='10' fill='{TEXT}'>"
                         f"{v:,.3g} {unit if not log else ''}</text>")
            else:
                s.append(f"<text x='{x0 + 4}' y='{y + bar_h - 5}' {MONO} font-size='10' fill='{MUTED}'>n/a</text>")
    lx = w - 110
    for j, (name, colour) in enumerate(series):
        s.append(f"<rect x='{lx}' y='{20 + j * 18}' width='12' height='10' fill='{colour}' rx='2'/>")
        s.append(f"<text x='{lx + 18}' y='{29 + j * 18}' {FONT} font-size='12' fill='{TEXT}'>{esc(name)}</text>")
    s.append("</svg>")
    return "\n".join(s)


TITLES = {
    "Q1": "Q1 point-in-parcel lookup", "Q2": "Q2 parcels near an active project", "Q3": "Q3 10 nearest comparables",
    "Q4": "Q4 a parcel's sale history", "Q5": "Q5 village yearly medians", "Q6": "Q6 screener page",
    "Q7": "Q7 sales in a date range", "Q8": "Q8 document retrieval", "Q9": "Q9 village name search",
}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    sf1, sf5 = read(1), read(5)
    written = []
    queries = sorted({q for q, _ in list(sf1) + list(sf5)}, key=lambda q: int(q[1:]))
    over = []
    for q in queries:
        variants = [v for (qq, v) in sf1 if qq == q] + [v for (qq, v) in sf5 if qq == q and (q, v) not in sf1]
        rows = [(v, [sf1.get((q, v)), sf5.get((q, v))]) for v in variants]
        svg = hbars(TITLES.get(q, q), "median of 10 runs, EXPLAIN (ANALYZE, BUFFERS), warm cache",
                    rows, [("SF1", SAGE), ("SF5", WALNUT)])
        if svg:
            (OUT / f"{q.lower()}.svg").write_text(svg)
            written.append(f"{q.lower()}.svg")
        vals1 = {v: x for v, x in [(v, sf1.get((q, v))) for v in variants] if x}
        if len(vals1) >= 2 and "refresh_concurrently" not in vals1:
            base = max(vals1, key=vals1.get)
            best = min(vals1, key=vals1.get)
            over.append((f"{q} {base}", [sf1.get((q, base)), sf5.get((q, base))]))
            over.append((f"{q} {best}", [sf1.get((q, best)), sf5.get((q, best))]))
    if over:
        (OUT / "overview.svg").write_text(hbars("Baseline vs best variant per query", "median ms; slowest and fastest "
                                                "SF1 variant of each query", over, [("SF1", SAGE), ("SF5", WALNUT)]))
        written.append("overview.svg")

    tw = RES / "tile_weight_sf1.csv"
    if tw.exists():
        rows = [r for r in csv.DictReader(line for line in tw.open() if not line.startswith("#")) if r["tile"].startswith("14/")][:3]
        before = {"14/11814/7360": 574046, "14/11810/7360": 579469, "14/11812/7358": 423532}
        data = [(f"z{r['tile']} ({int(r['parcels']):,} parcels)", [before.get(r["tile"], 0) / 1024, int(r["raw_bytes"]) / 1024])
                for r in rows]
        (OUT / "tiles.svg").write_text(hbars("Dense parcel tile size", "raw MVT bytes, before (spec 2.8 tile) and after "
                                             "migration 014; target < 150 KB", data, [("before", WALNUT), ("after", SAGE)],
                                             unit="KB", log=False))
        written.append("tiles.svg")

    pg = sorted(RES.glob("pgbench_*.csv"))
    if pg:
        data, names = {}, []
        for f in pg:
            name = "SF5" if "sf5" in f.name else "SF1"
            names.append(name)
            for r in csv.DictReader(f.open()):
                data.setdefault(r["clients"], {})[name] = float(r["tps"] or 0)
        rows = [(f"{c} clients", [data[c].get(n) for n in names]) for c in sorted(data, key=int)]
        colours = [SAGE if n == "SF1" else WALNUT for n in names]
        (OUT / "pgbench.svg").write_text(hbars("Screener throughput (pgbench)", "transactions per second, 30 s per run",
                                               rows, list(zip(names, colours, strict=True)), unit="tps", log=False))
        written.append("pgbench.svg")
    print("wrote " + ", ".join(written) + f" to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
