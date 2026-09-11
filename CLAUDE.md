# CLAUDE.md — project context for AI assistants

Read this first. It is short on purpose; the detail lives in the linked files.

## What this is

Interview case study for Borusan Otomotiv (Veri Yönetimi ve Uygulamaları Uzman Yardımcısı). Two deliverables on one
synthetic lead-to-sale dataset: (1) Medallion architecture on Microsoft Fabric + Power BI semantic model and report,
(2) an AI-assisted data product (lead scoring + next-best-action Streamlit app) that consumes the Gold layer.
Owner: Sude Bozkurt. Deadline: 2 days from 2026-09-09. Deliverable: repo + slides + live demo.

## Status (update this section as you go)

- [x] Synthetic data generator with documented DQ defects — `data_gen/generate.py`, `docs/dq_injections.md`
- [x] Bronze / Silver / Gold notebooks, tested end-to-end locally — `fabric/notebooks/0*.py` (+ `.ipynb`)
- [x] Lead scorer with point-in-time snapshots, tested — `ai_product/train_lead_scorer.py`
- [x] Streamlit app, smoke-tested — `ai_product/app.py`
- [x] DAX measures, model guide, report spec — `semantic_model/`, `report/`
- [ ] Run notebooks in the Fabric trial workspace (`fabric/fabric_setup_guide.md`)
- [ ] Build the Data Factory pipeline, run once, screenshot Monitor
- [ ] Build semantic model + 4 report pages, screenshots into `report/screenshots/`
- [ ] Slides (`docs/presentation_outline.md`)
- [ ] Rehearse demo; fallback = screenshots + `run_local.sh`

## How to run locally

```
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                 # needs Java 17+ for PySpark
./run_local.sh                                  # generate → bronze → silver → gold → train (~4 min)
streamlit run ai_product/app.py
```
Windows without bash: run the five python commands in `run_local.sh` one by one with `set REPO_ROOT=%cd%`.
Local runs write parquet tables (Delta jars need Maven access); Fabric writes Delta. Same code, `TABLE_FORMAT` switches.

## Conventions

- Notebooks are authored as jupytext percent-format `.py` and converted with `jupytext --to ipynb`. Edit the `.py`, regenerate the `.ipynb`. Never edit the `.ipynb` by hand.
- Every notebook has a config cell that detects Fabric (`import notebookutils`) vs local. Keep both paths working.
- Silver rule: never drop a row except exact duplicates; never null a value without a `dq_flags` entry and a `log_dq` call.
- Gold: natural keys, `UNK` rows in every dimension, `fact_leads` is one row per lead.
- Feature engineering for the model must be point-in-time (`<= snapshot_at`). Do not add features derived from `closed_at`, `status`, `lost_reason`, `last_offer_status`, or sale fields.
- Code, comments, docs: English. Streamlit UI and `signals.py` keyword rules: Turkish (users are dealer staff).
- Prices are illustrative TRY; do not "correct" them against real list prices.
- Seed 42 everywhere. Regenerating data changes the DQ counts in `docs/dq_injections.md` and the `EXPECTED` dict at the end of `02_silver_clean.py` — update both together.

## Do not

- Do not regenerate the dataset unless asked; screenshots and numbers in the slides depend on seed 42 output.
- Do not add a Warehouse, SCD2, RLS or SHAP unless explicitly requested — they are documented as "next steps" on purpose.
- Do not put phone numbers or e-mails into Gold; they stay in Silver (KVKK talking point).

## Where to look

| Question | File |
|---|---|
| What is in each raw file | `docs/data_dictionary.md` |
| What was deliberately broken | `docs/dq_injections.md` |
| Fabric click path | `fabric/fabric_setup_guide.md` |
| DAX and relationships | `semantic_model/measures.dax`, `semantic_model/model_guide.md` |
| Report pages | `report/report_spec.md` |
| Slides | `docs/presentation_outline.md` |
