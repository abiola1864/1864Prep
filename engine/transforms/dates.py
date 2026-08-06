"""Date standardisation via `dateparser` (understands many formats and locales)
plus explicit handling for Excel serial numbers. Output is ISO YYYY-MM-DD.

The day/month order comes from the active region (Nigeria = day-first) or an
explicit param, so ambiguous values like 03/09/1990 are read consistently. Truly
unparseable values are flagged, never guessed into a wrong date."""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any

import dateparser

from .base import Transform, _clean_str

_SERIAL = re.compile(r"^\d{4,5}$")
_EXCEL_EPOCH = _dt.date(1899, 12, 30)   # Excel's day 0


class DateISOTransform(Transform):
    """params: dayfirst (bool) or date_order ('DMY'|'MDY'|'YMD'); min_year/max_year
    to reject implausible dates."""
    name = "date_iso"

    def __init__(self, **params):
        super().__init__(**params)
        if "date_order" in params:
            self._order = params["date_order"]
        elif params.get("dayfirst"):
            self._order = "DMY"
        else:
            try:
                from regions import get_active_region
                self._order = get_active_region().date_order
            except Exception:
                self._order = "MDY"
        self._min = int(params.get("min_year", 1900))
        self._max = int(params.get("max_year", _dt.date.today().year + 1))

    def _in_range(self, d: _dt.date) -> bool:
        return self._min <= d.year <= self._max

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", True, "empty date"
        # Excel serial number (e.g. 44197 -> 2021-01-01)
        if _SERIAL.match(s):
            n = int(s)
            if 20000 <= n <= 60000:
                d = _EXCEL_EPOCH + _dt.timedelta(days=n)
                return (d.isoformat(), False, "") if self._in_range(d) else (value, True, "date out of range")
        d = dateparser.parse(s, settings={
            "DATE_ORDER": self._order,
            "PREFER_DAY_OF_MONTH": "first",
            "STRICT_PARSING": False,
        })
        if d is None:
            return value, True, "could not parse date"
        dd = d.date()
        if not self._in_range(dd):
            return value, True, "date out of plausible range"
        return dd.isoformat(), False, ""


class DateTimeISOTransform(Transform):
    """Timestamps -> ISO 'YYYY-MM-DD HH:MM:SS' (keeps the time). Falls back to
    dateparser; unparseable values are flagged, never guessed."""
    name = "datetime_iso"

    def __init__(self, **params):
        super().__init__(**params)
        try:
            from regions import get_active_region
            self._order = params.get("date_order") or get_active_region().date_order
        except Exception:
            self._order = params.get("date_order", "MDY")

    def apply_value(self, value):
        s = _clean_str(value)
        if s == "":
            return "", True, "empty datetime"
        try:
            import dateparser
            dt = dateparser.parse(s, settings={"DATE_ORDER": self._order, "PREFER_DAY_OF_MONTH": "first"})
        except Exception:
            dt = None
        if dt is None:
            return value, True, "unparseable datetime"
        return dt.strftime("%Y-%m-%d %H:%M:%S"), False, ""
