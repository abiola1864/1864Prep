"""Geographic standardisation: state and LGA names.

Two lineages live here:

  * StateNGTransform / LGANCCTransform  -- FAITHFUL ports of the NCC MASTER
    R script (create_state_mapping and the 5-step LGA pipeline). These
    reproduce the R behaviour, quirks included, so outputs can be checked for
    equivalence. See NOTES_R_ALIGNMENT.md.
  * LGANGTransform                       -- the earlier reference/prefix matcher
    kept for the social-register worked example.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .base import Transform

# ---------------------------------------------------------------------------
# STATE  -- faithful port of create_state_mapping() + the R cleaning steps
# ---------------------------------------------------------------------------
_PARENS = re.compile(r"\(.*?\)")            # non-greedy, matches R \\(.*?\\)
_NON_ALPHA = re.compile(r"[^A-Za-z\s\-]")   # keep letters, whitespace, hyphen
_WS = re.compile(r"\s+")
_SENTINELS = {"No State", "Unknown", "UNKNOWN", "State", "OTHERS"}


class StateNGTransform(Transform):
    """params: reference (path to ng_states.json), on_unrecognized ('flag'|'null').

    Algorithm, matching the R script exactly:
      1. remove parentheticals '(...)' FIRST
      2. replace non [A-Za-z space hyphen] with a space
      3. collapse whitespace + trim (str_squish)
      4. blank or a sentinel non-value -> null (flagged)
      5. else exact, case-sensitive lookup against the variation strings
    """
    name = "state_ng"

    def __init__(self, **params):
        super().__init__(**params)
        data = json.loads(Path(self.params["reference"]).read_text(encoding="utf-8"))
        self._lookup: dict[str, str] = {}
        for canonical, variations in data["states"].items():
            for v in variations:
                self._lookup[v] = canonical  # built from RAW variation strings, as in R
        self._on_unrecognized = self.params.get("on_unrecognized", "flag")

    def _clean(self, value: Any) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        s = str(value)
        s = _PARENS.sub("", s)
        s = _NON_ALPHA.sub(" ", s)
        s = _WS.sub(" ", s).strip()
        return s

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        cleaned = self._clean(value)
        if cleaned == "" or cleaned in _SENTINELS:
            return "", True, "no usable state (blank or sentinel)"
        official = self._lookup.get(cleaned)
        if official is not None:
            return official, False, ""
        # Unrecognised: R sets NA then drops the row; we flag and keep by default.
        if self._on_unrecognized == "null":
            return "", True, f"state not recognised: '{cleaned}'"
        return value, True, f"state not recognised: '{cleaned}'"


# ---------------------------------------------------------------------------
# LGA  -- faithful port of the 5-step vectorised R pipeline (uppercase output)
# ---------------------------------------------------------------------------
_LGA_NULLS = {"REFUSED", "OTHERS", "NA", "[NULL]", "NULL", "[NA]", "UNKNOWN", "N/A", "NO LGA", ""}

# Step 4: exact-match concatenation/spelling fixes (case_when in R).
_LGA_CONCAT = {
    "ADOODOOTA": "ADO-ODO/OTA",
    "OSHODIISOLO": "OSHODI-ISOLO",
    "LAGOSISLAND": "LAGOS ISLAND",
    "LAGOSMAINLAND": "LAGOS MAINLAND",
    "IBEJULEKKI": "IBEJU/LEKKI",
    "ETIOSA": "ETI-OSA",
    "AJEROMIFELODUN": "AJEROMI-IFELODUN",
    "AMUWOORDOFIN": "AMUWO-ODOFIN",
    "IFEKOIJAYE": "IFAKO-IJAYE",
    "IKPOBAOKHA": "IKPOBA-OKHA",
    "EGOREGBEMA": "EGOR",
    "OBAFEMIOWODE": "OBAFEMI-OWODE",
    "OBIOAKPOR": "OBIO/AKPOR",
    "OBIA/AKPOR": "OBIO/AKPOR",
    "KANOMUNICIPAL": "KANO MUNICIPAL",
    "KANO": "KANO MUNICIPAL",
    "UNGONGO": "UNGOGO",
    "SHAGAMU": "SAGAMU",
    "SHOMOLU": "SOMOLU",
    "CALABARMUNICIPAL": "CALABAR MUNICIPAL",
    "CALABAR": "CALABAR MUNICIPAL",
    "OWERRIMUNICIPAL": "OWERRI MUNICIPAL",
    "OWERRI": "OWERRI MUNICIPAL",
    "AMAC": "ABUJA MUNICIPAL",
    "ABUJA": "ABUJA MUNICIPAL",
    "ANAMBRAEAST": "ANAMBRA EAST",
    "ANAMBRAWEST": "ANAMBRA WEST",
    "AWKANORTH": "AWKA NORTH",
    "AWKASOUTH": "AWKA SOUTH",
    "IDEMILINORTH": "IDEMILI NORTH",
    "IDEMILISOUTH": "IDEMILI SOUTH",
    "NNEWINORTH": "NNEWI NORTH",
    "NNEWISOUTH": "NNEWI SOUTH",
    "ONITSHANORTH": "ONITSHA NORTH",
    "ONITSHASOUTH": "ONITSHA SOUTH",
    "ORUMBANORTH": "ORUMBA NORTH",
    "ORUMBASOUTH": "ORUMBA SOUTH",
}

# Step 3 suffix strips, order preserved.
_LGA_SUFFIX = [
    (re.compile(r"\bMUNICIPAL\s*AREA\s*COUNCIL\b"), ""),
    (re.compile(r"\bMUNICIPALAREACOUNCIL\b"), ""),
    (re.compile(r"\bMUNICIPALAREACOUNCILCIL\b"), ""),
    (re.compile(r"\bMUNICIPAL\s*AREA\s*COUN\b"), ""),
    (re.compile(r"\bAREA\s*COUNCIL\b"), ""),
    (re.compile(r"\bMUNICIPALITY\b"), ""),
    (re.compile(r"\bMUNICIPAL\b"), ""),
    (re.compile(r"\bMAC\b"), ""),
]

# Step 5 compound standardisation.
_LGA_COMPOUND = [
    (re.compile(r"ADO\s*ODO\s*/\s*OTA"), "ADO-ODO/OTA"),
    (re.compile(r"OSHODI\s*ISOLO"), "OSHODI-ISOLO"),
    (re.compile(r"OSHODI\s*/\s*ISOLO"), "OSHODI-ISOLO"),
    (re.compile(r"ETI\s*OSA"), "ETI-OSA"),
    (re.compile(r"OBIO\s*/\s*AKPOR"), "OBIO/AKPOR"),
    (re.compile(r"OBIO\s*AKPOR"), "OBIO/AKPOR"),
    (re.compile(r"IBEJU\s*/\s*LEKKI"), "IBEJU/LEKKI"),
    (re.compile(r"IKPOBA\s*OKHA"), "IKPOBA-OKHA"),
    (re.compile(r"OBAFEMI\s*OWODE"), "OBAFEMI-OWODE"),
]

_LGA_SPECIAL = re.compile(r"[^A-Z0-9\s\-/]")
_NUM_ONLY = re.compile(r"^[0-9\.\-]+$")
_STARTS_NUM = re.compile(r"^[0-9]")


class LGANCCTransform(Transform):
    """Faithful 5-step LGA cleaner from the NCC script. Output is UPPERCASE;
    unresolved values become 'UNKNOWN'. No per-state reference needed."""
    name = "lga_ncc"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "UNKNOWN", True, "empty LGA"

        # Step 1: basic
        s = str(value).strip().upper()
        if s in _LGA_NULLS or _NUM_ONLY.match(s) or _STARTS_NUM.match(s):
            return "UNKNOWN", True, "non-LGA / numeric value"

        # Step 2: special chars (remove parentheticals, keep A-Z0-9 space - /)
        s = _PARENS.sub("", s)
        s = _LGA_SPECIAL.sub(" ", s)
        s = _WS.sub(" ", s).strip()

        # Step 3: municipal/council suffixes
        for pat, rep in _LGA_SUFFIX:
            s = pat.sub(rep, s)
        s = s.strip()

        # Step 4: exact concatenation fixes
        if s in _LGA_CONCAT:
            s = _LGA_CONCAT[s]

        # Step 5: compound standardisation + final guards
        for pat, rep in _LGA_COMPOUND:
            s = pat.sub(rep, s)
        s = _WS.sub(" ", s).strip()
        if len(s) < 3 or s in {"", "-"}:
            return "UNKNOWN", True, "too short / empty after cleaning"

        return s, False, ""


class LGANGTransform(Transform):
    """Reference/prefix matcher for the social-register example. params: reference."""
    name = "lga_ng"

    def __init__(self, **params):
        super().__init__(**params)
        data = json.loads(Path(self.params["reference"]).read_text(encoding="utf-8"))
        self._lookup: dict[str, str] = {}
        norm = lambda x: re.sub(r"[^a-z0-9]+", "", str(x).strip().lower())
        for lga in data["lgas"]:
            self._lookup[norm(lga["canonical"])] = lga["canonical"]
            for a in lga["aliases"]:
                self._lookup[norm(a)] = lga["canonical"]
        self._keys_by_len = sorted(self._lookup.keys(), key=len, reverse=True)
        self._norm = norm

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        k = self._norm(value)
        if k == "":
            return "", True, "empty LGA"
        if k in self._lookup:
            return self._lookup[k], False, ""
        for cand in self._keys_by_len:
            if k.startswith(cand):
                leftover = k[len(cand):]
                return self._lookup[cand], True, f"de-concatenated; leftover '{leftover}' dropped"
        return value, True, "LGA not recognised"
