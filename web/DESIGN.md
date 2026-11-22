# LandLens design brief

The approved look for M4. Reference mockups are in `design/` next to this file
(`Main.dc.html` = landing, `Map.dc.html` = map + screener, `Report.dc.html` = parcel report).
They are static HTML mockups: copy their layout, spacing and styling, not their code structure.
All numbers in them are sample data.

## Feel

Screener.in's clarity and density, in an earthy palette. Professional, calm, finance-grade.
No emoji, no gradients, no left-border accent cards, no stock "AI SaaS" look.

## Colour tokens

Define these as CSS variables on `:root` and `[data-theme="dark"]`, and map them into Tailwind
(`bg-surface`, `text-muted`, etc.) and the shadcn/ui theme. Never hard-code hex in components.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F7F5F0` | `#121513` | Page background |
| `--surface` | `#FFFFFF` | `#1A1F1C` | Cards, header, panels |
| `--border` | `#E3DED4` | `#2B322D` | Hairlines, table rules |
| `--text` | `#1E2420` | `#E7E5DF` | Body text |
| `--muted` | `#62675F` | `#9AA096` | Labels, secondary text |
| `--primary` | `#3F5E4A` | `#8FB596` | Brand sage: logo, primary buttons, active nav, focus |
| `--on-primary` | `#FFFFFF` | `#121513` | Text on primary |
| `--tint` | `#E7EEE8` | `#22302A` | Chips, selected filter background |
| `--tint-text` | `#2E4537` | `#B9D3BD` | Text on tint |
| `--accent` | `#7A5A40` | `#C9A07A` | Walnut: links, secondary actions, highlights |
| `--up` | `#3F7A4E` | `#7FBF8C` | Gains, positive drivers |
| `--down` | `#A8483A` | `#E08A78` | Losses, negative drivers, warnings (terracotta, never pure red) |
| `--heat-1/2/3` | `#DCE6DD` / `#A9C2AE` / `#6F9479` | `#2A3A30` / `#456552` / `#6E9A7C` | Parcel fill: below / near / above village median |

Rules:
- One primary (filled sage) button per view. Everything else is outlined (surface + border) or a walnut link.
- "Price vs median" in tables stays neutral `--text`: below median is good for a buyer, so it is not red.
- Text contrast must pass 4.5:1; the values above do.

## Shadow (ochre lift, like Screener's cards)

Every card, tile, table container and floating map panel gets:

- Light: `box-shadow: 0 1px 2px rgba(122,90,64,0.10), 0 6px 16px -4px rgba(184,134,60,0.25);`
- Dark: `box-shadow: 0 1px 2px rgba(0,0,0,0.5), 0 6px 16px -4px rgba(201,160,122,0.12);`

Expose as `--shadow-card`. Cards: 1px `--border`, radius 12px (10px for small tiles and map panels).

## Typography

Load from Google Fonts with `next/font/google`:

| Role | Font | Weights | Where |
|---|---|---|---|
| Display / headings | Newsreader (serif) | 400, 500 | Logo wordmark, page titles, section headings (h1 to h3) |
| UI and body | Schibsted Grotesk | 400, 500, 600 | Everything else |
| Numbers | IBM Plex Mono | 400, 500 | Every price, percentage, distance, area, count, credit balance |

Sizes: h1 44 to 56px (landing hero 56, report title 44), section headings 22 to 26px, body 15 to 16px,
labels and table headers 12 to 13px. Headings weight 500, tight letter-spacing (-0.015em) on large serif.
Numbers in tables are right-aligned.

## Logo

Sage magnifying glass with a small rising trend line inside the lens, plus "LandLens" in Newsreader 500.
Inline SVG (24 to 26px): circle r 6.5 at (10.5,10.5), handle from (15.5,15.5) to (21,21), polyline
7.5,12.5 9.5,10 11,11.5 13,8.5; stroke `--primary`, width 2, round caps. Copy it from any mockup header.

## Light / dark toggle

Moon icon button (40 to 44px, outlined) in the header on every page. Persists to localStorage,
defaults to the system preference, sets `data-theme` on `<html>`. No flash on load (set it in a
blocking script in the layout head).

## Map style (MapLibre)

Topographic / outdoor look on free OpenStreetMap vector tiles (no Google tiles, no paid key).
Start from a free OSM-based MapLibre style (for example OpenFreeMap) and recolour its layers:

| Feature | Light | Dark |
|---|---|---|
| Land base | `#EEEEDF` | `#1E211B` |
| Farmland / grass | `#D3DAA6`, `#C2CD8C` | `#283022`, `#303A26` |
| Forest / wood | `#AFC07E` | `#2C3A24` |
| Water fill / outline | `#8ED3E3` / `#2F8FA6` | `#1F4650` / `#5FAFC2` |
| Major road / casing | `#FFFFFF` / `#D3CEBC` | `#3B4038` / `#2A2E27` |
| Tracks, paths | `#6B5A3C`, dashed (7 5), 2.5px | `#B39A6C` |
| Buildings fill / outline | `#CFCBC0` / `#A9A59A` | `#3A3A33` / `#4C4C43` |
| Labels / halo | `#3B3F36` / `#FFFFFF`, Schibsted Grotesk | `#D8D8CC` / `#1E211B` |

Our layers on top (from Martin): parcels filled with `--heat-1/2/3`, 2px surface-coloured outline,
90% opacity; selected parcel outlined 3px `--accent`; development projects as dashed `--accent`
lines/outlines with haloed labels; parcel-coverage boundary as a thin dashed `--muted` line.
Switch the base style and our layer colours when the theme changes.

## Page layouts (match the mockups)

**Header (all pages):** surface background, bottom border. Logo, nav (Map, Trends, Pricing; active item
in `--primary` weight 500), search box on the map page, credit balance in mono, theme toggle, sign in
or primary CTA.

**Landing:** hero (eyebrow in walnut uppercase 13px, serif headline, muted subhead, one primary + one
outlined CTA) beside a parcel snapshot card with a 2x2 grid of metric tiles; a 4-column feature band
on surface; pricing (Free, 5 credits Rs 1,999 highlighted with a 2px sage border, 20 credits Rs 6,999);
footer with the "not legal or financial advice" and synthetic-data line.

**Map + screener:** left screener panel (~300px, surface): land-type chips (selected = tint + sage
border), zone select, range sliders with mono values, groundwater checkbox, full-width primary
"Show N parcels". Map fills the rest (~560px tall) with floating panels: layers (top right), legend
(bottom left), clicked-parcel card with three mono rows and "Unlock full report · 1 credit". Results
table below the map with keyset "Load more"; first/selected row tinted.

**Parcel report:** breadcrumb, serif title, chips, two outlined/primary actions; 4 metric tiles; then a
two-column layout. Main: Valuation (range bar with p25 to p75 band, p50 marker in sage, asking marker
in walnut, signed drivers list in up/down colours), Price history (Recharts line in sage, project
announcement as a dashed walnut reference line, parcel sales as open walnut circles), Comparable
sales table, Zoning and Soil and water cards side by side. Side: Ask the master plan (question bubble,
answer with mono walnut citations, input + Ask), Location distances, provenance/disclaimer box.

## States

Every data view has a loading skeleton (surface blocks with a subtle pulse), an empty state (serif
headline + one-line suggestion + action) and an error state (what happened + retry). Badges reading
"Sample data" or "Synthetic" wherever synthetic values appear.

## Responsive

Desktop-first (1280px+). Below 900px the screener panel stacks above the map and tables scroll
horizontally inside their container.
