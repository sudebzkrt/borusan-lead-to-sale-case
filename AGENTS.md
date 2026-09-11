# AGENTS.md

Instructions for any coding agent (Claude Code, Cursor, Copilot, Codex) working in this repository.
`CLAUDE.md` has the project context and status; this file is about *how to work* here.

## Ground rules

1. **Verify before claiming.** A notebook change is done when it has been run (`REPO_ROOT=$PWD python fabric/notebooks/02_silver_clean.py`) and the DQ ground-truth comparison at the end still prints `OK`/`~` for every check. A model change is done when `train_lead_scorer.py` runs and `metrics.json` is regenerated. An app change is done when the AppTest smoke test below passes.
2. **Small, explained changes.** The owner will present this code in an interview and must be able to explain every cell. Prefer a clear 10-line cell over a clever 3-line one. Add a one-sentence "why" comment when you add logic.
3. **Keep the dual runtime.** Everything under `fabric/notebooks/` and `ai_product/train_lead_scorer.py` must run both in Fabric (default lakehouse attached, Delta) and locally (parquet). Do not introduce Fabric-only APIs outside the `if IS_FABRIC:` blocks.
4. **Token budget is real.** The owner has a limited AI usage plan. Read `CLAUDE.md` and the one file you need; do not read the raw CSVs (use `head -3`), the `.ipynb` files (read the `.py`), or `data/warehouse`.
5. **No scope creep.** The deadline is two days. If a request is not on the status checklist in `CLAUDE.md`, ask whether it should replace something before building it.

## Smoke tests

```
# pipeline (≈3 min)
REPO_ROOT=$PWD python fabric/notebooks/01_bronze_ingest.py
REPO_ROOT=$PWD python fabric/notebooks/02_silver_clean.py   # last cell: ground-truth comparison
REPO_ROOT=$PWD python fabric/notebooks/03_gold_star_schema.py   # last cell: funnel totals
REPO_ROOT=$PWD python ai_product/train_lead_scorer.py            # prints metrics; expect AUC > 0.8

# app
REPO_ROOT=$PWD python -c "
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('ai_product/app.py', default_timeout=120).run()
assert not at.exception, at.exception
for p in ['Lead detayı','Model kartı','Veri hattı']:
    at.sidebar.radio[0].set_value(p).run(); assert not at.exception, (p, at.exception)
print('app ok')"
```

## After editing a notebook `.py`

```
jupytext --to ipynb fabric/notebooks/02_silver_clean.py -o fabric/notebooks/02_silver_clean.ipynb
```

## Style

- Python 3.10+, PySpark 3.5 API (works on Spark 4 too — avoid removed APIs, avoid `spark.sql.legacy.*` beyond the one `timeParserPolicy` line).
- pandas for the ML part, scikit-learn only (no LightGBM/XGBoost — one fewer install on Fabric).
- Markdown cells: what the cell does and *why this way*, in 2–5 sentences. No emoji in notebooks.
- Commit messages: imperative, one line, e.g. `silver: quarantine orphan interactions instead of flagging`.
