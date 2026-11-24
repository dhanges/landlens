# seed_inputs/

Inputs for `make seed`, tracked in git so every checkout can seed without downloads
or an OpenAI key. When a file is missing, the generator uses a clearly marked synthetic fallback: rows get
`source = 'synthetic'` and names start with `[fallback]`, and `landlens verify` reports them. Origins and dates
of every input: `sources.md`.

| File | Used for | If missing |
| --- | --- | --- |
| `study_area.geojson` | the study area (KUDA boundary) | a starting box, lat 17.75-18.15 N, lon 79.35-79.85 E (unverified) |
| `osm/*.json` | roads, rail, water, amenities, village points; produce with `api/landlens/gen/overpass_query.ql` | synthetic villages on a jittered grid, radial highways, a local road grid, tanks, amenities |
| `projects/projects.geojson` | the 5 projects with hand-digitized geometry and sourced status histories (format in `api/landlens/gen/projects.py`; not supplied yet: V1) | approximate synthetic geometry and invented status dates |
| `zones/zone_types.json` | zone codes, names and permitted uses from the KUDA land-use map legend | an 8-zone placeholder list |
| `docs/KUDAMasterPlan2041.jpg` | source of the zone legend (not read by the code yet) | n/a |
| `docs/*.pdf` + `docs/manifest.json` | the document Q&A corpus (`landlens ingest-pdf`) | no documents; chat answers "not found" |
| `docs/embeddings/*.json` | chunk embeddings, so `make seed` restores the documents without calling OpenAI | `make ingest` re-embeds (needs a key) |
