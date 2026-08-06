# Working on data the tool has never seen

The tool cannot assume it knows an agency's columns, field types, or category
vocabularies. A health file, an agriculture file, a pension file, a scholarship
file — different schemas, different entities, different mess, mostly unknown in
advance. So the engine does not ship a cleaner per known field. It works out an
arbitrary file for itself, using two general, data-driven capabilities plus the
resolver.

## 1. Type inference — figure out what each column IS (`engine/profile.py`)

For every column it reads the values and infers a semantic type from evidence
(format hit-rates, cardinality, value lengths, gazetteer match-rates): identifier,
phone, email, date, boolean, gender, geographic, numeric measure, categorical,
name, or free text. Each type implies a transform. Nothing is tied to a fixed
schema, so the same code profiled health, agric, and pension files with **no
sector configuration** and routed each column to the right cleaner.

`profile_to_plan()` turns the profiles into a proposed, review-ready plan — this
is how *any* uploaded file gets a first-draft cleaning plan automatically.

## 2. Vocabulary induction — build the category set from the data (`engine/induce.py`)

When a column is categorical but its canonical vocabulary is unknown (a health
agency's `Diagnosis`, an agric agency's `Crop`), the tool discovers the
vocabulary: it clusters the distinct values by fuzzy + phonetic similarity so
spelling variants of the same category collapse together, and proposes the most
frequent spelling as the standard. `12 messy diagnosis spellings -> 5 clean
categories`, `10 crop spellings -> 4`, with no list supplied. The
`auto_categorical` transform applies this end to end.

## 3. Resolution — match to ground truth where it exists (`engine/resolve.py`)

Where an authoritative list does exist (the 37 states, later the full LGA and
operator lists), the resolver maps messy inputs to it with fuzzy + phonetic
matching — no dictionary of variants needed.

Together: profile → (resolve where there's a canonical list | induce where there
isn't) → deterministic cleaners for IDs/dates/phones/numbers. All on the distinct
values, all local, all logged.

## Honest limitations (and how each is handled)

These are real, and pretending otherwise would be the failure mode:

1. **Modal spelling ≠ correct spelling.** Induction picks the *most frequent*
   variant as the label, so a column dominated by `Maiz` yields `Maiz`, not
   `Maize`. The cluster is right; the label needs a human tick. This is exactly
   what the review step is for — the reviewer confirms or renames the induced
   canonical, and that edit becomes training signal.
2. **Place → admin needs a gazetteer, not string similarity.** `Ibadan` will not
   resolve to `Oyo` by spelling. The profiler flags it (`geo` only fires on
   gazetteer hits); the fix is loading the official settlement→LGA→state
   hierarchy, which is the next build.
3. **Two IDs with the same format are indistinguishable by data alone.** An
   11-digit `NIN` and an 11-digit `BVN` look identical to the profiler; it types
   both as an 11-digit identifier. The *column name* disambiguates, which the
   header mapper and the reviewer use.
4. **Date order (day-first vs month-first) is genuinely ambiguous.** `01/02/2026`
   could be 1 Feb or 2 Jan. The parser defaults per source and flags mixed
   columns; the reviewer sets the convention once per file.
5. **Name vs. low-cardinality categorical.** A name column with few distinct
   people can look categorical from values alone; realistic cardinality and the
   column name resolve it.
6. **Statistical inference is heuristic.** Every profile carries a confidence and
   its evidence; low-confidence columns and every unresolved value go to the
   review queue rather than being trusted silently.

## Where a model raises the ceiling (the enhancement rung)

Fuzzy + phonetic + statistics is deterministic, offline, and already general.
A local model lifts the hard cases: reading column *semantics* from headers +
samples (so `NIN` vs `BVN` is inferred, not guessed), resolving place→admin with
world knowledge, clustering categories by meaning rather than spelling
(`HTN` ≈ `Hypertension`, which sound different), and parsing free-text addresses.
It runs locally and sees only distinct values — never rows, never the file —
so the privacy guarantee is unchanged. That is rung 4 of the ladder in
CLEANING_APPROACH.md.


## Generic core, swappable region packs

The engine stands on established locale-aware libraries (phonenumbers, dateparser, price-parser, ftfy, email-validator, rapidfuzz) so it handles *any* country's values, not one dataset's quirks. Country specifics — default phone region, date order, currency symbols, and optional state/place/LGA lists — live in a swappable `regions/` pack. Nigeria is one pack; `GENERIC` assumes nothing. See `regions/README.md`.
