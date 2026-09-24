# Extractor evaluation — 40 labelled threads

Sample: 40 leads ({'lost': 16, 'won': 10, 'contacted': 6, 'test_drive': 4, 'offer': 4}), labelled with the rules in `prompts/signal_extraction.system.md` in two AI passes; disagreements reviewed, second pass is the reference. Accuracy = share of threads where the extractor's label equals the reference.

## Labeller agreement (first pass vs reference)

| field          |   agreement |
|:---------------|------------:|
| intent         |       0.9   |
| main_objection |       0.925 |
| went_quiet     |       0.975 |
| buying_signal  |       0.975 |

6 of 40 threads differed in at least one field and were reviewed.

## Keyword rules (signals.py)

| field          |   accuracy |   precision |   recall |
|:---------------|-----------:|------------:|---------:|
| intent         |      0.875 |         nan |   nan    |
| main_objection |      0.725 |         nan |   nan    |
| went_quiet     |      1     |           1 |     1    |
| buying_signal  |      0.925 |           1 |     0.75 |

## Reading the numbers

* `went_quiet` and `buying_signal` are the two fields the scorer uses as features; precision matters more than recall there (a false 'buying signal' inflates a score).
* `main_objection` is the hardest field: threads often carry two obstacles and the label follows the most recent one. Disagreements are listed in `predictions.csv` (compare `ref_*` with `rules_*` / `llm_*`).
* The keyword rules see substrings only; the LLM reads the whole thread. The LLM column is empty until `run_eval.py --llm` is run with an API key.
