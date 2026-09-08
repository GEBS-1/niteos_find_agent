from __future__ import annotations

# Back-compat: flat city list comes from the geography tree.
from app.geo_tree import city_list as city_list  # noqa: F401
from app.geo_tree import geo_payload

# Kept for older scripts that imported CITIES.
CITIES: tuple[str, ...] = tuple(geo_payload()["cities"])
