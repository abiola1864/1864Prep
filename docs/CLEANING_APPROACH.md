# The cleaning approach: robust standardisation, not hand-written rules

The tool's job is to turn any agency's messy records into the shared standard
**without a human enumerating every possible misspelling first**. Hard-coded
alias lists (the pattern in the original R scripts) don't scale: a new agency, a
new state, or a spelling nobody listed all break them silently. This document
sets out the method the engine uses instead.

## The core idea: match to ground truth, don't catalogue the mess

For any field with a known set of valid values — the 36 states + FCT, the 774
LGAs, the licensed operators, the sector's category vocabulary — the tool holds
only the **authoritative canonical list** and *resolves* messy inputs to it.
The mess is open-ended; the truth is finite. So we model the truth.

Resolution runs as a ladder, cheapest and most certain first:

1. **Normalise + exact match.** Case, accents, punctuation, whitespace. Catches
   the bulk instantly.
2. **Fuzzy + phonetic matching** (`engine/resolve.py`). A blend of edit-distance
   similarity (RapidFuzz) and phonetic similarity (Metaphone / Match-Rating via
   Jellyfish) scores every canonical candidate. This resolves misspellings that
   are in **no** dictionary — `kadna`, `Plateu`, `Phlateau`, `Adamewa`, `Zamfra`,
   `Sokoyo` — because it reasons about *similarity*, not membership. Deterministic
   and fast.
3. **Gazetteer** (reference data, not built here yet). String similarity cannot
   turn `Port Harcourt` into `Rivers` or `Ibadan` into `Oyo` — that is
   geography, not spelling. The official Nigerian administrative hierarchy
   (settlement → LGA → state) is open reference data; loading it once resolves
   place→admin for the whole country, with no per-agency aliases.
4. **Embeddings + a local model** for the genuine residuals — free-text
   addresses, novel category phrasings, or contradictory annotations like
   `Onitsha(Abia)` (a model can note Onitsha is in Anambra and flag the Abia
   tag). This is the same small, local, owned model from the architecture doc —
   it runs on the machine and sees only distinct values.

Everything the ladder cannot settle with confidence is **routed to review, never
guessed** — the confidence bands (high / review / unresolved) drive the same
queue you see in the mockup's step 4.

## Two properties that make this safe as well as robust

**It runs on distinct values, not rows.** A register of 18,000 rows has maybe a
few hundred distinct state strings. The resolver works on that small set and the
result is applied to every row locally. So even at the embedding/LLM rung, the
only thing processed is a list of a few hundred non-identifying strings —
never a NIN, never a row, never the file. The brief's promise holds by
construction.

**It is deterministic and logged.** Fuzzy + phonetic scoring gives the same
answer for the same input every time, so a run is repeatable and auditable —
unlike letting a model freely rewrite values. Every decision (input → canonical,
score, method, band) is recorded, which is what NDPA review needs.

## Where AI belongs — and where it must not

Not every field is an NLP problem, and pretending otherwise is where these tools
get dangerous:

- **Entity standardisation** (states, LGAs, providers, categories, names) —
  *yes*, this is exactly what robust matching is for.
- **Identifiers and dates** (NIN length, phone format, date parsing) — *no*.
  These are exact, rule-governed transforms. A model "correcting" a NIN or
  guessing a date is a data-integrity hazard, not a feature. They stay
  deterministic, and the tool validates and flags rather than invents.

## The learning loop

Every mapping a reviewer confirms or corrects is a labelled example. Collected
over pilots, these tune the thresholds, extend the gazetteer, and (rung 4)
fine-tune the local model on real Nigerian government data. The tool gets better
with use, and that accumulated, confirmed mapping data — not any single model —
is the durable asset.

## What is in the repo now vs next

- **Now:** rungs 1–2 (`engine/resolve.py`, the `resolve` transform), demonstrated
  resolving unseen misspellings against the canonical list, with confidence
  bands and the distinct-values design. The strict R-dictionary transforms remain
  available as an optional exact-reproduction mode, not the default.
- **Next:** the gazetteer loader (rung 3) from the official admin hierarchy, and
  the local-model proposer interface (rung 4) behind the same distinct-values
  boundary.
