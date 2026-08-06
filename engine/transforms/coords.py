"""Geographic coordinate cleaning: latitude, longitude, and combined points.

Coordinates arrive as signed decimals (6.45, -3.39), DMS (6°27'N, 30.123W),
or a single "lat, long" point. This uses `lat-lon-parser` to normalise any of
those to decimal degrees, and validates the ranges (lat ±90, long ±180). Out-of-
range or unparseable values are flagged, never guessed.
"""
from __future__ import annotations

from typing import Any

from .base import Transform, _clean_str


def _to_decimal(s: str):
    try:
        from lat_lon_parser import parse
        return float(parse(s))
    except Exception:
        try:
            return float(s.replace(",", "").strip())
        except ValueError:
            return None


class LatitudeTransform(Transform):
    """Normalise to decimal degrees; flag values outside -90..90."""
    name = "latitude"

    def apply_value(self, value: Any):
        s = _clean_str(value)
        if s == "":
            return "", True, "empty latitude"
        d = _to_decimal(s)
        if d is None:
            return value, True, "unparseable latitude"
        if not -90.0 <= d <= 90.0:
            return value, True, f"latitude out of range ({d})"
        return str(round(d, 6)), False, ""


class LongitudeTransform(Transform):
    """Normalise to decimal degrees; flag values outside -180..180."""
    name = "longitude"

    def apply_value(self, value: Any):
        s = _clean_str(value)
        if s == "":
            return "", True, "empty longitude"
        d = _to_decimal(s)
        if d is None:
            return value, True, "unparseable longitude"
        if not -180.0 <= d <= 180.0:
            return value, True, f"longitude out of range ({d})"
        return str(round(d, 6)), False, ""
