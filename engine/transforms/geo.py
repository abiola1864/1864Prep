"""Geographic standardisation: state and LGA names.

  * StateNGTransform  -- match a value to one of the 37 official states using a
    reference list of names/variations (see reference/ng_states.json).
  * LGANGTransform    -- reference / longest-prefix matcher for LGAs.

For the robust, dictionary-free path (recommended), see engine/resolve.py, which
matches messy values to a canonical list with fuzzy + phonetic similarity.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .base import Transform

_PARENS = re.compile(r"\(.*?\)")
_NON_ALPHA = re.compile(r"[^A-Za-z\s\-]")
_WS = re.compile(r"\s+")
_SENTINELS = {"No State", "Unknown", "UNKNOWN", "State", "OTHERS"}


class StateNGTransform(Transform):
    """params: reference (path to ng_states.json), on_unrecognized ('flag'|'null').

    Cleaning: strip parentheticals, drop non-letter characters, collapse
    whitespace, then look the value up against the reference names. Blank or
    sentinel values are flagged; unrecognised values are flagged (kept by
    default) or nulled.
    """
    name = "state_ng"

    def __init__(self, **params):
        super().__init__(**params)
        data = json.loads(Path(self.params["reference"]).read_text(encoding="utf-8"))
        self._lookup: dict[str, str] = {}
        for canonical, variations in data["states"].items():
            for v in variations:
                self._lookup[v] = canonical
        self._on_unrecognized = self.params.get("on_unrecognized", "flag")

    def _clean(self, value: Any) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        s = str(value)
        s = _PARENS.sub("", s)
        s = _NON_ALPHA.sub(" ", s)
        return _WS.sub(" ", s).strip()

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        cleaned = self._clean(value)
        if cleaned == "" or cleaned in _SENTINELS:
            return "", True, "no usable state (blank or sentinel)"
        official = self._lookup.get(cleaned)
        if official is not None:
            return official, False, ""
        if self._on_unrecognized == "null":
            return "", True, f"state not recognised: '{cleaned}'"
        return value, True, f"state not recognised: '{cleaned}'"


class LGANGTransform(Transform):
    """Reference / prefix matcher for LGAs. params: reference (LGA json)."""
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
