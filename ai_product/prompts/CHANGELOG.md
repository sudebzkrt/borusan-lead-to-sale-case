# Prompt changelog

Kept so the iteration is visible: what changed, why, and how it is checked. Entries say "review" when the change came
from reading the prompt against a risk list, and "observed" when it came from an actual failing output — keep that
distinction honest when you add entries.

## next_best_action

| Version | Change | Why |
|---|---|---|
| v1 (Sept 9, string in `llm.py`) | Role, "return JSON with keys summary / action / draft_message", 25/60-word caps, "siz" form, "no discount promises unless an offer already exists", "say WHEN" | First shipped version; the discount guard and the deadline requirement were the two constraints considered non-negotiable from the start (a drafted message that offers money is a real business risk, an action without a date is not an action). |
| v2 (Sept 23, this file) | Prompt moved out of code into a file; an "inputs" section documents the exact payload; rules 3–8 added (closed leads, quiet leads, never mention the model/AI to the customer, keep advisor and customer audiences separate, missing data); two few-shot examples; new `confidence` key; JSON schema validation with one retry in `llm.py` | Review of v1 against a failure checklist: nothing stopped a pushy message to a lead that went quiet, nothing stopped "modelimize göre" leaking into a customer message, and an empty-notes lead had no defined behaviour. Schema validation makes a malformed answer impossible to reach the UI (it falls back to the template). |

## signal_extraction

| Version | Change | Why |
|---|---|---|
| v1 (string in `llm.py`) | Schema given as a JSON example with one-line descriptions | Worked for the demo button. |
| v2 (this file) | Explicit labelling rules with a precedence order; "went quiet" defined as the *latest* state of the thread; `buying_signal` added so the LLM extractor and the keyword rules share the same fields; three few-shot examples (buying signal vs happy test drive; financing; quiet) | Needed a stable definition to evaluate against the 40 labelled threads in `eval/`. A label without a written rule cannot be measured, and `main_objection` is exactly the kind of field that drifts between runs without a tie-break rule. |

## How changes are checked

1. Run `python ai_product/eval/run_eval.py` (keyword rules) and, with a key, `python ai_product/eval/run_eval.py --llm`.
   Compare `eval/RESULTS.md` before and after a prompt change; a change that lowers agreement on any field is reverted.
2. Open three leads in the app (one with an offer, one that went quiet, one closed) and read the draft messages aloud.
   If it would embarrass an advisor in front of a customer, it does not ship.
3. Every new rule in the prompt gets at least one thread in `eval/eval_notes.csv` that exercises it.
