"""Enum values mirrored from migration 002 (validated at the edge, cast in SQL)."""

from __future__ import annotations

from enum import Enum


class LandType(str, Enum):
    urban_plot = "urban_plot"
    peri_urban = "peri_urban"
    agricultural = "agricultural"


class GwCategory(str, Enum):
    safe = "safe"
    semi_critical = "semi_critical"
    critical = "critical"
    over_exploited = "over_exploited"
