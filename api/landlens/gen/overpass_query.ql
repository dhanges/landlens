/*
  LandLens Overpass query (spec 2.12 step 1). Run it at https://overpass-turbo.eu or with
    curl --data-urlencode data@overpass_query.ql https://overpass-api.de/api/interpreter > kuda.json
  and save the result as landlens/seed_inputs/osm/kuda.json (DEC-006).
  Bounding box = DEC-004 starting estimate (south, west, north, east); adjust it to the confirmed box (T-M1-8).
*/
[out:json][timeout:180][bbox:17.75,79.35,18.15,79.85];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential)$"];
  way["railway"="rail"];
  way["natural"="water"];
  way["landuse"="reservoir"];
  way["waterway"="river"];
  nwr["amenity"~"^(school|hospital|bus_station)$"];
  way["landuse"="industrial"];
  nwr["aeroway"="aerodrome"];
  node["place"~"^(city|town|village|suburb|hamlet)$"]["name"];
);
out geom;
