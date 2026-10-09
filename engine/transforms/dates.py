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

_SERIAL = re.compile(r"^\d{4,5}(?:\.\d+)?$")
_YEAR_ONLY = re.compile(r"^(1[89]|20)\d{2}$")
_NUMDATE = re.compile(r"^(\d{1,4})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?$")
_TEXT_FMTS = ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y", "%d-%b-%Y", "%d-%b-%y",
              "%d %b %y", "%A %d %B %Y", "%d/%b/%Y", "%Y/%m/%d", "%d.%m.%Y")


def _year4(y: int) -> int:
    if y >= 100:
        return y
    cutoff = (_dt.date.today().year % 100) + 5       # '25' -> 2025, '68' -> 1968
    return 2000 + y if y <= cutoff else 1900 + y


def _fast_numeric_date(s: str, order: str):
    m = _NUMDATE.match(s)
    if not m:
        return None
    a, b, c = m.group(1), m.group(2), m.group(3)
    try:
        if c is None:                                 # two parts: MM/YY or MM/YYYY (card dates)
            if len(a) <= 2 and 1 <= int(a) <= 12:
                return ("month_year", None)
            return None
        if len(a) == 4:                               # YYYY/MM/DD
            return ("date", _dt.date(int(a), int(b), int(c)))
        x, y, yr = int(a), int(b), _year4(int(c))
        if x > 12 and y <= 12:  day, mon = x, y      # unambiguous day-first
        elif y > 12 and x <= 12: day, mon = y, x     # unambiguous month-first
        elif order == "MDY":    day, mon = y, x
        else:                   day, mon = x, y      # DMY (default) or anything else
        return ("date", _dt.date(yr, mon, day))
    except ValueError:
        return ("bad", None)


def _fast_text_date(s: str):
    t = " ".join(s.replace(",", ", ").split()).replace(" ,", ",")
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t, flags=re.I)
    for f in _TEXT_FMTS:
        try:
            return _dt.datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def _region_order(default: str = "DMY") -> str:
    """Day/month order of the active region. Uses the same region source as the
    server (regions.py if present, else the built-in fallback). If the region
    doesn't say, assume day-first, which is the convention in Nigeria and most of
    the world. A column's own evidence (a day > 12) always overrides this."""
    for mod in ("regions", "engine.regions_fallback"):
        try:
            m = __import__(mod, fromlist=["get_active_region"])
            o = getattr(m.get_active_region(), "date_order", None)
            if o:
                return o
        except Exception:
            continue
    return default
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
            self._order = _region_order()
        self._min = int(params.get("min_year", 1900))
        self._max = int(params.get("max_year", _dt.date.today().year + 1))

    def _in_range(self, d: _dt.date) -> bool:
        return self._min <= d.year <= self._max

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", True, "empty date"
        # Excel serial number (e.g. 44197 -> 2021-01-01; 44562.5 keeps the date part)
        _ser = _SERIAL.match(s)
        if _ser:
            f = float(s)
            if 20000 <= f <= 60000:
                d = _EXCEL_EPOCH + _dt.timedelta(days=int(f))
                return (d.isoformat(), False, "") if self._in_range(d) else (value, True, "date out of range")
        # ISO-like (YYYY-MM-DD) is unambiguous: keep as-is, never day-first swap
        _iso = _re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$", s) if (_re := __import__("re")) else None
        if _iso:
            y, mo, dy = (int(x) for x in _iso.groups())
            try:
                d = _dt.date(y, mo, dy)
                return (d.isoformat(), False, "") if self._in_range(d) else (value, True, "date out of range")
            except ValueError:
                return value, True, "impossible date (month/day out of range)"
        # A bare year is NOT a full date. Never invent a month and day for it
        # (dateparser fills missing parts from today's date).
        if _YEAR_ONLY.match(s):
            return value, True, "only a year, month and day unknown"
        # Fast, exact reading of the common shapes (12/03/1990, 3-12-90, 08/18).
        # The general date library tries every language and calendar and can take
        # seconds per value, which froze cleaning on files with many dates.
        fast = _fast_numeric_date(s, self._order)
        if fast is not None:
            kind, d = fast
            if kind == "month_year":
                return value, True, "month and year only (no day)"
            if kind == "bad":
                return value, True, "impossible date (month/day out of range)"
            return (d.isoformat(), False, "") if self._in_range(d) else (value, True, "date out of plausible range")
        fast = _fast_text_date(s)
        if fast is not None:
            return (fast.isoformat(), False, "") if self._in_range(fast) else (value, True, "date out of plausible range")
        _set = {"DATE_ORDER": self._order, "PREFER_DAY_OF_MONTH": "first", "STRICT_PARSING": False}
        d = dateparser.parse(s, languages=["en"], settings={**_set, "REQUIRE_PARTS": ["day", "month", "year"]})
        if d is None:
            if dateparser.parse(s, languages=["en"], settings=_set) is not None:
                return value, True, "incomplete date (day, month or year missing)"
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
        self._order = params.get("date_order") or _region_order()

    def apply_value(self, value):
        s = _clean_str(value)
        if s == "":
            return "", True, "empty datetime"
        # ISO-like (YYYY-MM-DD ...) is unambiguous: never apply day-first ordering
        import re as _re
        iso = _re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?", s)
        if iso:
            y, mo, d, h, mi, se = iso.groups()
            try:
                import datetime as _dt
                _dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(se or 0))
            except ValueError:
                return value, True, "impossible datetime (out of range)"
            return f"{y}-{mo}-{d} {int(h):02d}:{mi}:{se or '00'}", False, ""
        try:
            import dateparser
            dt = dateparser.parse(s, languages=["en"], settings={"DATE_ORDER": self._order, "PREFER_DAY_OF_MONTH": "first"})
        except Exception:
            dt = None
        if dt is None:
            return value, True, "unparseable datetime"
        return dt.strftime("%Y-%m-%d %H:%M:%S"), False, ""
