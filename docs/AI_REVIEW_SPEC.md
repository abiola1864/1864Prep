# 1864 Prep — AI Review (whole-file, upfront, recommended)

## Why this exists
The old AI behaviour called the model once per "uncertain" column. That was slow
(N sequential calls to a local model), gave the model no view of the table, and
left the user unsure what was happening. This spec replaces it with a single,
context-aware, whole-file review that the app only recommends when it is likely
to help.

## Principles
- The built-in engine always runs first and does the bulk, locally.
- AI is optional and, when used, sees the whole table in ONE pass.
- Whole-file review is **local-only** (Ollama). Nothing leaves the machine.
  Cloud providers (OpenAI/Claude) stay masked/minimal and do NOT get whole-file mode.
- The user is always told what is happening and approves every change.

## Flow
1. **Upload → fast engine pass** (as today): structure detection + rule-based
   column types, plus a per-column confidence score.
2. **Confidence gate.** Compute how many columns are "uncertain"
   (no clear header, low type confidence, or free_text fallback).
   - 0 uncertain → no AI prompt. Go straight to the columns review.
   - ≥ THRESHOLD uncertain (default 3) AND a local AI is configured → show the
     **AI recommendation popup** (below).
   - Uncertain but no local AI configured → show the columns review with a small
     one-line hint that AI could help (no nag, no popup).
3. **AI recommendation popup** (only when it clears the gate):
   - Title: "Want AI to review this file?"
   - Body: "N columns look uncertain. A local model can review the whole file once
     and suggest a cleaner structure. Nothing leaves your computer."
   - Buttons: [Review with AI]  [No, I'll do it myself]
   - Never auto-runs. The user chooses.
4. **Whole-file AI pass (one call).** If the user accepts:
   - Build ONE prompt: the resolved header + a compact sample (up to ~15 rows,
     all columns), values masked for sensitive-looking columns.
   - Send to the local model via /api/ai/review.
   - Show a clear activity state: "AI is reviewing your file… (local model — may
     take up to a minute)."
   - The model returns, per column: suggested name, suggested type, short reason;
     and an overall note on whether the header/structure looks right.
5. **Annotated results.** On the columns review, each column the AI commented on is
   marked (small ✦), showing the suggestion and reason on hover/click. The user
   accepts or rejects. Nothing is applied without approval.

## Endpoint: POST /api/ai/review  (local-only)
Request: { headers: [...], sample: [ {col: val, ...}, ... up to 15 ],
           provider, url, model }
- Rejects unless provider resolves to a local Ollama (leaves_device == false).
- Masks sensitive-looking columns in the sample before sending.
- One model call. Parses a JSON-ish reply into:
  Response: { ok, where, columns: [ {name, suggested_type, reason} ], note, raw, error? }
- On model-not-installed or timeout, returns a clear, actionable error.

## Timeouts & performance
- Whole-file review timeout: 90s (local models are slow to load first call).
- Only ONE request regardless of column count (fixes the old N-call slowness).
- First call warms the model; later calls are faster.

## Fallbacks
- Manual "use AI" control remains, but points at the same whole-file review.
- If AI is unreachable / model missing / times out: keep the engine's reading,
  show the actionable message, never block the user.

## Out of scope (for now)
- Cloud whole-file review (privacy). Cloud stays masked, per-column, opt-in.
- AI editing data values directly. AI only suggests structure/types; the engine
  applies approved transforms.
