"""Correction memory: the tool learns from every mistake it is shown.

Seeded from corrections the team has already shared (compiled into
knowledge/seed_corrections.json), and appended to every time a user confirms or
adjusts a suggestion. A known correction is treated as a certainty; the resolver
consults this store before any fuzzy/phonetic reasoning.

Conflicts (aliases the shared data mapped to more than one answer) are kept
explicitly so the tool ASKS rather than guessing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())


class CorrectionStore:
    def __init__(self, seed_path: str = "knowledge/seed_corrections.json",
                 user_path: str = "knowledge/user_corrections.json"):
        self.seed_path = Path(seed_path)
        self.user_path = Path(user_path)
        seed = json.loads(self.seed_path.read_text(encoding="utf-8")) if self.seed_path.exists() else {}
        self.confirmed: dict[str, dict[str, str]] = seed.get("confirmed", {})
        self.conflicts: dict[str, dict[str, list]] = seed.get("conflicts", {})
        self.user: dict[str, dict[str, str]] = {}
        if self.user_path.exists():
            u = json.loads(self.user_path.read_text(encoding="utf-8"))
            self.user = u.get("confirmed", {})
            # user decisions override/append to confirmed, and clear conflicts
            for dom, m in self.user.items():
                self.confirmed.setdefault(dom, {}).update(m)
                for k in m:
                    self.conflicts.get(dom, {}).pop(k, None)

    def lookup(self, domain: str, value: str):
        """Return ('canonical', str) if known, ('conflict', [candidates]) if the
        shared data disagreed, or (None, None) if unknown."""
        k = _norm(value)
        if not k:
            return None, None
        if k in self.confirmed.get(domain, {}):
            return "canonical", self.confirmed[domain][k]
        # a genuine conflict on the exact value must surface before any fallback
        if k in self.conflicts.get(domain, {}):
            return "conflict", self.conflicts[domain][k]
        # try parenthetical-stripped form as well
        k2 = _norm(re.sub(r"\(.*?\)", "", str(value)))
        if k2 != k and k2 in self.confirmed.get(domain, {}):
            return "canonical", self.confirmed[domain][k2]
        if k2 != k and k2 in self.conflicts.get(domain, {}):
            return "conflict", self.conflicts[domain][k2]
        return None, None

    def memory(self, domain: str) -> dict[str, str]:
        """The confirmed map for a domain, for the resolver to consult first."""
        return dict(self.confirmed.get(domain, {}))

    def learn(self, domain: str, raw: str, canonical: str, persist: bool = True):
        """Record a user-confirmed correction; it is certain from now on."""
        k = _norm(raw)
        if not k:
            return
        self.confirmed.setdefault(domain, {})[k] = canonical
        self.user.setdefault(domain, {})[k] = canonical
        self.conflicts.get(domain, {}).pop(k, None)
        if persist:
            self._save()

    def _save(self):
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"_meta": {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "note": "User-confirmed corrections. Appended by the review step."},
                   "confirmed": self.user}
        self.user_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    def stats(self) -> dict:
        return {"confirmed": {d: len(m) for d, m in self.confirmed.items()},
                "conflicts": {d: len(m) for d, m in self.conflicts.items()},
                "user_added": {d: len(m) for d, m in self.user.items()}}
