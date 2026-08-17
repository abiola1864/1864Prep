"""Context and the Decisions ledger.

Two things the pipeline carries end to end (see docs/PIPELINE.md):

  * Context — what we know about the dataset and each column, growing as we go.
  * Decisions — every proposed or taken action, with a concrete before -> after,
    a safety label, and a status. Nothing reaches export that is not in here, and
    the review shows every entry.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ColumnContext:
    raw_header: str
    proposed_name: str = ""
    confirmed_name: str = ""
    semantic_type: str = "unknown"
    expected: dict = field(default_factory=dict)     # {format?, allowed_set?, range?, pattern?, nullable?}
    evidence: str = ""
    context_note: str = ""                            # one line: what this column represents

    def to_dict(self):
        return asdict(self)


@dataclass
class DatasetContext:
    source: str = ""
    file_type: str = ""
    encoding: str = ""
    sheet_name: str = ""
    sheets_all: list = field(default_factory=list)
    structure: dict = field(default_factory=dict)     # banner_rows, header_rows, data_start, orientation, ...
    domain_guess: str = ""
    columns: list = field(default_factory=list)        # list[ColumnContext]

    def to_dict(self):
        d = asdict(self)
        return d


@dataclass
class Decision:
    column: str
    kind: str                    # rename|retype|reformat|reference_fix|repair|flag|merge|drop|dedupe|outlier
    before: Any
    after: Any
    safety: str = "meaning"      # "safe" (auto, listed) | "meaning" (needs approval)
    status: str = "proposed"     # proposed|accepted|rejected|applied
    reason: str = ""

    def to_dict(self):
        return asdict(self)


class Ledger:
    """Ordered record of every decision. The review renders this; export saves it."""

    def __init__(self):
        self._items: list[Decision] = []

    def add(self, **kw) -> Decision:
        d = Decision(**kw)
        self._items.append(d)
        return d

    def propose(self, column, kind, before, after, reason="", safety="meaning"):
        return self.add(column=column, kind=kind, before=before, after=after,
                        reason=reason, safety=safety, status="proposed")

    def note_safe(self, column, kind, before, after, reason=""):
        return self.add(column=column, kind=kind, before=before, after=after,
                        reason=reason, safety="safe", status="applied")

    def accept(self, i): self._items[i].status = "accepted"
    def reject(self, i): self._items[i].status = "rejected"

    def pending(self):
        return [d for d in self._items if d.safety == "meaning" and d.status == "proposed"]

    def safe_changes(self):
        return [d for d in self._items if d.safety == "safe"]

    def to_list(self):
        return [d.to_dict() for d in self._items]

    def summary(self):
        return {
            "total": len(self._items),
            "safe": len(self.safe_changes()),
            "needs_approval": len(self.pending()),
            "by_kind": {k: sum(1 for d in self._items if d.kind == k)
                        for k in sorted({d.kind for d in self._items})},
        }
