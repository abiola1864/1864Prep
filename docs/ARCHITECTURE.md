# Architecture and the open-source boundary

## The three components (keep them separate)

The brief describes two things an institution runs — a **Tool** that standardises
data and an **adapter** that answers questions — plus the shared network. In code
these are three distinct components, deliberately kept apart:

| Component | What it does | This repo? | Suggested licence |
|-----------|--------------|------------|-------------------|
| **Cleaning engine** | Standardises an agency's file locally; emits cleaned data + audit | **Yes** | Apache-2.0 (open) |
| **Desktop shell** | Wraps the engine in an installable app (the mockup's UI) | Separate repo | Apache-2.0 (open) |
| **Network adapter** | The Beckn provider node that answers signed questions from the cleaned file | Separate repo | Apache-2.0 (open) |

Keep the word **"engine"** for the local cleaner and **"adapter"** for the
network node. Using "engine" for both will confuse a dev team.

The cleaning engine ends its job at a clean local file (plus, optionally, wiring
that file to the adapter). The adapter never reads raw data — only the
standardised output, in place, returning only answers.

## The AI mapping ladder

The mapping task is small: column headers + a few sample rows + the target
schema. Most of it is solved before any model is involved. Four rungs, from the
technical design:

1. **Rules + dictionary (no AI).** `engine/mapper.py`. An alias dictionary plus
   fuzzy matching. Fully offline. This is the default and the "Rules only" mode.
2. **A small local model that 1864 owns.** For the columns rules can't settle, an
   open-weight model runs on the machine or an on-premise server the state
   controls. It connects to nothing external. *(Not in this repo; a pluggable
   proposer interface is the integration point.)*
3. **Fine-tune it over time.** Every mapping an agency confirms is a labelled
   example. Collect them, retrain the local model periodically (e.g. LoRA). This
   is the real proprietary asset.
4. **Bring your own, off by default.** An agency can configure its own endpoint
   (an internal ministry model, or a hosted model). Even then, only headers +
   samples are ever sent — see `mapper.sample_payload()`.

### What is open, and what is not

- **Open (Apache-2.0):** the engine, the transform library, the reference data,
  the plan format, the desktop shell, the adapter. These should be forkable so
  other agencies and countries can adopt them.
- **Not open:** the **fine-tuning dataset** built from real agencies' confirmed
  mappings. It is cheap to build, hard to copy (it comes from doing the work),
  and it is where the durable advantage sits. Do **not** pretrain a foundation
  model — it costs millions, needs a specialist team, and produces something
  worse than a free open-weight model for this narrow task.

## Enforcing the data-never-leaves promise

Two mechanisms carry the trust story and both belong in CI:

1. **A "what gets sent" preview.** `sample_payload()` returns exactly what would
   leave the machine. The UI must show it before anything is sent.
2. **A build-failing test.** A test should assert that no code path passes a full
   DataFrame to any network client — the guarantee is enforced by the test
   suite, not by a promise in a README.

## Packaging (for the installable app, separate repo)

- **UI:** the web front-end (the mockup), rendered inside a desktop shell.
- **Local engine:** this repo, bundled and invoked in-process or via a small
  local FastAPI service on `localhost`. It reads the file from local disk.
- **Shell:** **Tauri** recommended over Electron — smaller installer, stronger
  security posture (which matters for a government pitch). Produces a signed
  `.msi`/`.exe` for Windows and a notarised `.dmg` for Mac.
- **Testing without deploying:** run the front-end dev server and the engine on
  `localhost` with the sample files. Code-signing/notarisation is a one-time
  step only when handing a partner an installer; internal pilots can ship
  unsigned.

## Note on provenance

The cleaning rules are general and derived from common data-quality patterns
(mixed date formats, inconsistent spellings, concatenated place names, varied
phone formats). No agency's private data or scripts are included in this
repository; sample data under `samples/` is synthetic.
