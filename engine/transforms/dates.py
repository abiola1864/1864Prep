"""Date parsing to ISO (YYYY-MM-DD), using a cascade of parsers.

A robust parser tries a series of parsers in order (ymd_hms, mdy_hm, mdy_hms,
m/d/y H:M, ..., mdy, ymd) and keeps the first that succeeds, then nullifies any
date outside a valid window (configurable via min_year/max_year). Both behaviours are reproduced here. Excel serial numbers are also
handled, matching parse_any_date().
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd
from dateutil import parser as dtparser

_ISO_LIKE = re.compile(r"^\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")
_SERIAL = re.compile(r"^[0-9]{5}(\.[0-9]+)?$")
_MDY = re.compile(r"^\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")  # m/d/y or d/m/y style


class DateISOTransform:
    """params:
        min_year (int, default 1900), max_year (int, default 2100)
            -- dates outside [min_year, max_year] are nulled + flagged.
        dayfirst (bool, default False)
            -- the  files are month-first (US style: 1/1/2026, 3/9/26 8:29),
               so the default is False to match the R mdy parsers. Set True for
               day-first sources.
    """
    name = "date_iso"

    def __init__(self, **params):
        self.params = params
        self.min_year = int(params.get("min_year", 1900))
        self.max_year = int(params.get("max_year", 2100))
        self.dayfirst = bool(params.get("dayfirst", False))

    def _parse(self, s: str):
        # Excel serial (matches parse_any_date: serial -> POSIX via 1899-12-30).
        if _SERIAL.match(s):
            try:
                serial = float(s)
                base = datetime(1899, 12, 30)
                return base + pd.to_timedelta(serial, unit="D")
            except Exception:
                return None
        # ISO / year-first strings.
        if _ISO_LIKE.match(s):
            try:
                return dtparser.parse(s, yearfirst=True, dayfirst=False)
            except (ValueError, OverflowError, TypeError):
                return None
        # Everything else: honour dayfirst (default False = month-first, US-style).
        try:
            return dtparser.parse(s, dayfirst=self.dayfirst, yearfirst=False)
        except (ValueError, OverflowError, TypeError):
            return None

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "", True, "empty date"
        s = str(value).strip()
        if s == "" or s.lower() in {"nan", "nat", "none", "null", "na"}:
            return "", True, "empty date"

        dt = self._parse(s)
        if dt is None:
            return value, True, "unparseable date"

        # Two-digit years that expanded into the future are pivoted back a century.
        if dt.year > datetime.now().year + 1:
            try:
                dt = dt.replace(year=dt.year - 100)
            except ValueError:
                pass

        # Out-of-range window: nullify + flag (records kept, as the R note intends).
        if dt.year < self.min_year or dt.year > self.max_year:
            return "", True, f"date out of range ({dt.year}); nulled"

        return dt.strftime("%Y-%m-%d"), False, ""

    def run(self, series: pd.Series, source_column: str, target_field: str):
        from .base import Transform
        holder = Transform()
        holder.name = self.name
        holder.apply_value = self.apply_value  # type: ignore[assignment]
        return holder.run(series, source_column, target_field)
