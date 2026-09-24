# Prompts — how the LLM layer is designed

The assistant uses an LLM in exactly two places, and both prompts live here as files (not as strings in code), so they
can be reviewed, versioned and tested like any other artefact.

| Prompt | Called from | When | Output |
|---|---|---|---|
| `next_best_action.system.md` | `llm.next_best_action` | Advisor opens one lead in the app | summary · action · draft WhatsApp message · confidence |
| `signal_extraction.system.md` | `llm.llm_signals` | "Notları LLM ile özetle" button, and `eval/run_eval.py --llm` | intent · main objection · went quiet · buying signal · summary |

`schemas.json` holds the JSON schema for each output. `llm.py` validates every response against it and retries once
with the validation error appended; if the second answer is still invalid the app falls back to the rule-based
template. The demo therefore never shows a broken LLM answer.

## Design principles (what to say if asked "how did you write the prompts?")

1. **Role + audience + format, in that order.** Who the model is, who reads the output (advisor vs customer — different
   registers), and the exact JSON keys. Free-text output was the first thing that broke the UI.
2. **The model only sees curated facts.** `llm.py` builds the user payload from a whitelist of `fact_leads` columns.
   No raw IDs, no customer PII beyond what the advisor already wrote in the notes, no discount numbers unless an offer exists.
3. **Hard rules for the things that cost money.** "Never promise a discount", "never invent stock or delivery",
   "never mention the model or AI to the customer". These came from failures in v1 (see `CHANGELOG.md`).
4. **Few-shot examples for the judgement calls.** Two examples for next-best-action (offer on the table vs went quiet),
   three for extraction (buying signal vs happy test drive; financing; quiet). Examples are where the rules are ambiguous.
5. **Explicit tie-break order for labels.** The extraction prompt says which signal wins when two apply (most recent).
   Without it the model alternated between `price` and `timing` on the same thread across runs.
6. **Temperature 0.2, JSON mode, schema validation, one retry.** Determinism first; creativity is only wanted in the
   draft message, and even there the constraints (≤ 60 words, one question, no emojis) do most of the work.
7. **Rules at scale, LLM at the last mile.** 15k leads × daily LLM calls is cost and latency for nothing — the scorer
   needs coarse signals and the keyword rules give them. The LLM earns its keep on one lead at a time, where a human reads.
8. **Measured, not assumed.** `eval/` holds 40 threads labelled against the same rules (two AI passes, disagreements reviewed) and a script that reports agreement for the keyword
   rules and (with a key) for the LLM extractor, per field. The numbers are in `eval/RESULTS.md`.

## Running without an API key

Everything degrades gracefully: without `LLM_API_KEY` the app uses `_template_action` (rule-based, deterministic) and the
UI shows a "şablon" badge. With a key (OpenAI, Azure OpenAI, Groq, OpenRouter, Ollama — anything OpenAI-compatible) the
LLM path switches on automatically.
