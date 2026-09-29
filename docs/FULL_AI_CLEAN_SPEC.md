# Full AI clean (local model only)

## What it is
A distinct, opt-in mode where a LOCAL model attempts a fuller cleaning pass on top
of the engine: structure, column meaning, types, and value normalisation — returning
a fully PROPOSED result the user reviews and approves. Never automatic; never cloud.

## Guardrails
- LOCAL ONLY (Ollama). Refused for cloud providers (data would leave the device).
- The engine still runs first and does the bulk. Full AI clean is an overlay.
- Nothing is applied without the user's approval on the review screen.
- Sensitive-looking columns are masked/skipped in anything sent.

## What it does (per column, one masked pass each; engine result as the baseline)
1. Column meaning + type (already via /api/ai/review) — kept.
2. Value normalisation (already via /api/ai/values, variant merges) — kept.
3. NEW: free-text tidy suggestions — trailing/loose whitespace, casing, obvious
   typos in categorical labels the reference didn't catch — as proposed merges.
The result is the union of engine cleaning + accepted AI proposals.

## Flow
- AI setup gains a mode: "Full AI clean (local)".
- On the columns screen, when that mode is on and the model is local, the single
  AI action runs review + values across ALL eligible columns (not just uncertain),
  shows a clear progress state, and marks every AI-touched column.
- Cloud model selected → the option is disabled with a note ("local only").

## Out of scope
- AI rewriting numeric values, dates, IDs (engine handles those deterministically).
- Any cloud full-clean.
