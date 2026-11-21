# LandLens

An independent land research terminal for the Warangal (KUDA) region. LandLens is
"Screener.in for land": a map and parcel screener over computed intelligence, locality
price trends, an explainable valuation range, and a document assistant that answers
master plan questions with citations to the source documents.

It is **not** a marketplace — no listings, no buy/sell, no broker leads. Neutrality is
the positioning.

## Data

Geography, OpenStreetMap features, and the real projects and documents in the corpus are
real. Parcels, sales, soil, and groundwater are synthetic (ADR-008). Reports and
valuations carry "Not legal or financial advice" and "synthetic data" badges.

## Setup

Two commands bring up a working app with a seeded demo account:

```
make up
make seed SF=1
```

## Demo account

- Email: `demo@landlens.local`
- Password: `demolandlens` (local demo only — change before any hosted deployment)

The demo account starts with 10 credits.

See `.env.example` for the environment variables to copy into an (uncommitted) `.env`.

> This is a stub. The full README lands in T-M7-1.
