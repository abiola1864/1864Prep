"""Categorical cleaners ported from the NCC script: complaint Category,
Ticket source, and SLA status."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Transform

_WS = re.compile(r"\s+")


def _prep(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value)
    s = re.sub(r"[\r\n]+", " ", s)
    s = s.replace("\x02", "")
    s = _WS.sub(" ", s).strip()
    return s


class CategoryTransform(Transform):
    """Canonicalises complaint categories via ordered keyword rules (grepl on
    the upper-cased value), matching the R case_when."""
    name = "category"

    # (compiled pattern on UPPER text, canonical) -- order matters (first wins).
    _RULES = [
        (re.compile(r"DATA DEPLETION"), "Data Depletion"),
        (re.compile(r"QUALITY.*(VOICE|\(VOICE\))"), "Quality of Service/Experience (Voice)"),
        (re.compile(r"QUALITY.*(DATA|\(DATA\)|EXPERINCE)"), "Quality of Service/Experience (Data)"),
        (re.compile(r"FAULTY TERMINAL"), "Faulty Terminals"),
        (re.compile(r"SMS"), "SMS/MMS"),
        (re.compile(r"SIM.*REPLACEMENT"), "SIM Replacement"),
        (re.compile(r"SIM CARD ISSUES"), "SIM Replacement"),
        (re.compile(r"RECHARGE.*(TOP|UP)"), "Recharge/Top-Up Issues"),
        (re.compile(r"RECHARGE\s*/\s*TOP"), "Recharge/Top-Up Issues"),
        (re.compile(r"VALUE.*ADD.*SERVICES"), "Value-Added Services (VAS)"),
        (re.compile(r"DO.*NOT.*DISTURB|DND"), "Do-Not-Disturb Service"),
        (re.compile(r"MOBILE NUMBER PORTABILITY"), "Mobile Number Portability"),
        (re.compile(r"INTERNATIONAL ROAMING"), "International Roaming"),
        (re.compile(r"FAILED PAYMENT"), "Failed Payment Transaction"),
        (re.compile(r"BTS ISSUE"), "BTS Issues"),
        (re.compile(r"CALL CENT(RE|ER)"), "Call Center/Customer Care"),
        (re.compile(r"CALL CENTER / CUSTOMER CARE"), "Call Center/Customer Care"),
        (re.compile(r"SALES PROMOTION"), "Sales Promotions & Advertisement"),
        (re.compile(r"OTHER SIM.*RELATED"), "Other SIM-Related Issues"),
        (re.compile(r"NETWORK COVERAGE"), "Network Coverage"),
    ]
    # Rules needing "does NOT contain" logic are handled explicitly below.
    _QOS_GENERIC = re.compile(r"^QUALITY (OF|IS) (SERVICE|EXPERIENCE)")
    _QOS_EXP = re.compile(r"QUALITY OF EXPERIENCE")
    _VOICE_DATA = re.compile(r"VOICE|DATA")
    _OTHERS = re.compile(r"^OTHERS?$")
    _COMPLAINTS = re.compile(r"^COMPLAINTS?$")

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _prep(value)
        if s == "":
            return "UNKNOWN", True, "empty category"
        up = s.upper()

        if self._QOS_GENERIC.search(up) and not self._VOICE_DATA.search(up):
            return "Quality of Service/Experience", False, ""
        if self._QOS_EXP.search(up):
            return "Quality of Service/Experience", False, ""

        for pat, canon in self._RULES:
            if pat.search(up):
                return canon, False, ""

        if up == "BILLING":
            return "Billing", False, ""
        if self._OTHERS.search(up):
            return "Others", False, ""
        if self._COMPLAINTS.search(up):
            return "Complaints", False, ""

        # Unmatched: keep the tidied value (R leaves it as-is).
        return s, False, ""


class TicketSourceTransform(Transform):
    """Maps ticket source to 7 buckets, matching the R str_detect chain."""
    name = "ticket_source"

    _SRC06 = re.compile(r"SRC06")
    _CALL = re.compile(r"CALL|CONTACT CENTRE|CONTACT CENTER|INBOUND|OUTBOUND|CC\b|VOICE|PHONE CALL|PHONE")
    _ESERVICE = re.compile(r"ESERVICE|E-SERVICE|EPC|SWIFT NETWORK CRM|SPECTRANET CX|HC APP|MY LEGEND")
    _DIGITAL = re.compile(r"DIGITAL|EMAIL|E-MAIL|WEBSITE|WEBCARE|CHAT|WHATSAPP|INSTAGRAM|TWITTER|FACEBOOK|SOCIAL MEDIA|SM-|APP|LIVE CHAT|ONLINE|MOBILE APP|WEB PORTAL")
    _WALKIN = re.compile(r"WALK|DROP IN|STORE|SHOP|RETAIL|REATAIL|LOUNGE|ESTATE|VICTORIA ISLAND|WALK-IN")
    _INTERNAL = re.compile(r"INTERNAL|REFERRAL|MARKETING|CAMPAIGN|QUALITY|EXPERIENCE|CX|SUPPORT AGENT|BACKOFFICE")
    _NUMERIC = re.compile(r"^[0-9\.]+$")

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "Other", False, ""
        up = str(value).strip().upper()
        if up == "" or self._NUMERIC.match(up):
            return "Other", False, ""
        if self._SRC06.search(up):
            return "src06", False, ""
        if self._CALL.search(up):
            return "Call Center", False, ""
        if self._ESERVICE.search(up):
            return "eService", False, ""
        if self._DIGITAL.search(up):
            return "Digital", False, ""
        if self._WALKIN.search(up):
            return "Walk-in", False, ""
        if self._INTERNAL.search(up):
            return "Internal", False, ""
        return "Other", False, ""


class SLATransform(Transform):
    """Standardises the 'Closed- within SLA' column to Yes / No, else blank.
    Open/unclear states (In View, OPENED, -, --) become blank + flagged."""
    name = "sla"

    _YES = re.compile(r"^(Yes|YES|Within SLA|within sla)$")
    _NO = re.compile(r"(^No$|^NO$|Outside SLA|OUTSIDE SLA|outside SLA|Resolved outside|NOT WITHIN SLA|Closed outside)", re.IGNORECASE)

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "", True, "no SLA value"
        s = str(value).strip()
        if self._YES.match(s):
            return "Yes", False, ""
        if self._NO.search(s):
            return "No", False, ""
        return "", True, "SLA unresolved/unclear"
