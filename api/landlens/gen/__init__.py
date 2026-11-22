"""Seeded synthetic data generator over real geography (spec 2.12, ADR-008)."""

from __future__ import annotations

import time

import numpy as np

from landlens.db import connect

from . import load, osm, projects, steps
from .geo import study_area


def run(sf: float, seed: int) -> int:
    t0 = time.time()
    rng = np.random.default_rng(seed)
    with connect() as conn:
        area, area_src = study_area(conn)
        print(f"gen --sf {sf} --seed {seed}")
        print(f"  study area: {area.area / 1e6:.0f} sq km from {area_src}")
        layers = osm.load(conn, area, rng)                         # step 1
        print(f"  base layers: {layers.origin}: {len(layers.features)} features, {len(layers.villages)} village points")
        projs, proj_src = projects.load(conn, layers.centres)     # step 6 inputs
        print(f"  projects: {len(projs)} from {proj_src}")
        w = steps.World(seed=seed, sf=sf, study_area=area, layers=layers, projects=projs)
        steps.boundaries(w, rng)                                   # step 2
        steps.demo_window(w)                                       # step 4 window (DEC-004)
        steps.parcels(w, rng)                                      # steps 3-4
        steps.road_frontage(w)                                     # step 5
        steps.zones(w, rng)                                        # step 7
        price = steps.price_model(w, rng)                          # step 8
        steps.sales(w, rng, price)                                 # step 9
        steps.guideline_rates(w, rng, price)                       # step 10
        steps.environment(w, rng)                                  # step 11
        for n in w.notes:
            print(f"  {n}")
        print(f"  generated in {time.time() - t0:.0f}s; loading")
        load.reset(conn)                                           # step 12
        ref = load.load_reference(conn, w)
        par = load.load_parcels(conn, w)
        sal = load.load_sales(conn, w)
        der = load.derive(conn)
        demo = load.demo_account(conn)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("ANALYZE")
    print(f"  reference rows: {ref}")
    print(f"  parcels: {par}")
    print(f"  sales: {sal}")
    print(f"  derived: {der}")
    print(f"  demo account: {demo}")
    print(f"  window: {w.window_meta}")
    print(f"gen done in {time.time() - t0:.0f}s")
    return 1 if par["failed_batches"] or sal["failed_batches"] else 0
