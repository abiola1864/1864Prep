# Contributing

Thanks for helping build the on-ramp for the Open Network on Digital ID.

## The one rule that must not be broken

**The engine never sends the full dataset anywhere.** Any change that would pass
a whole file (or a whole column of real values) to a network client will be
rejected. The mapping layer works from headers and a few sample rows only. If
you add a model-backed proposer, it plugs in behind the same minimal payload
(`engine/mapper.sample_payload`).

## Adding a transform

1. Add a `Transform` subclass in the right file under `engine/transforms/`
   (or a new file). Implement `apply_value(value) -> (new_value, flagged, reason)`.
   The base class handles counting, examples, and the audit record.
2. Register it in `engine/transforms/__init__.py`.
3. Add tests in `tests/test_transforms.py` — at least one happy path and one
   flagged/edge case.
4. Keep it deterministic. No network, no randomness, no model calls.

## Adapting reference data

States, LGAs, and phone prefixes are **data**, in `reference/`. To support a new
state, add its LGA JSON on the pattern of `ng_lga_kaduna.json`. To support a new
country, replace the reference files and the prefix set. No engine code changes.

## Adding a sector

A sector is a **plan** in `plans/` — the field vocabulary the data is cleaned
toward — plus any new header aliases in `engine/mapper.py`. No new infrastructure
code.

## Style

- Python 3.11+, standard library + pandas/openpyxl/dateutil only for the core.
- Prefer small, single-purpose transforms over one clever mega-transform.
- Every flag needs a human-readable `reason`; a reviewer must understand it
  without reading the code.

## Tests

```bash
python tests/test_transforms.py      # or: python -m pytest -q
```
