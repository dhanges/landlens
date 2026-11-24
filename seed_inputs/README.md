# seed_inputs/

Inputs for `make seed`, tracked in git so every checkout (and the submission zip) can seed without downloads
(DEC-002, DEC-006). When a file is missing, the generator uses a clearly marked synthetic fallback: rows get
`source = 'synthetic'` and names start with `[fallback]`, and `landlens verify` reports them.

| File | Used for | If missing |
| --- | --- | --- |
| `study_area.geojson` | study area (DEC-004; confirm the box on a map, T-M1-8) | DEC-004 starting box lat 17.75-18.15 N, lon 79.35-79.85 E (unverified) |
| `osm/*.json` | roads, rail, water, amenities, village points (spec 2.12 step 1); produce with `api/landlens/gen/overpass_query.ql` | synthetic villages on a jittered grid, radial highways, a local road grid, tanks, amenities |
| `projects/projects.geojson` | the 5 projects with hand-digitized geometry and sourced status histories (not supplied yet: V1) (T-M1-11; format in `api/landlens/gen/projects.py`) | approximate synthetic geometry and invented status dates |
| `zones/zone_types.json` | zone codes, names and permitted uses from the KUDA land-use map legend (DEC-005) | an 8-zone placeholder list |
| `KUDAMasterPlan2041.jpg` | source of the zone legend (DEC-005) | n/a |
| `docs/*.pdf` | RAG corpus (DEC-005): GO 202, TUA(D) Act 1975, optionally GO 168 | n/a until M5 |
