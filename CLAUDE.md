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
- [x] Run notebooks in the Fabric trial workspace (`fabric/fabric_setup_guide.md`) — see `report/screenshots/05_lakehouse_schemas.png`, `06_bronze_output.png`, `07_silver_dq_comparison.png`
- [ ] Build the Data Factory pipeline, run once, screenshot Monitor — pipeline canvas done (`16a_pipeline_canvas.png`), still missing the Monitor run-view screenshot for the "operational" slide
- [x] Build semantic model + 4 report pages, screenshots into `report/screenshots/` — `09a`–`09d` (4 report pages + model diagram) plus lakehouse explorer shot
- [ ] Slides (`docs/presentation_outline.md`)
- [ ] Rehearse demo; fallback = screenshots + `run_local.sh`

Round 2 (feedback: data model liked; report visuals and slides not; show how the LLM/prompt is used):

- [x] Report v2 — `report_v2/LeadToSale.pbip`, spec `report/report_spec_v2.md`, 37 extra measures `semantic_model/measures_v2_additions.dax`, PNGs `report/screenshots_v2/` (also in `docs/img/`), PDF `report/report_v2_pages.pdf`
- [x] Prompt package + eval — `ai_product/prompts/`, `ai_product/eval/` (`run_eval.py` reproduces `RESULTS.md`); app has the "Modele ne gönderiliyor?" expander, smoke-tested
- [x] Slide numbers recomputed from Gold — `docs/build_fact_sheet.py` → `docs/presentation_facts.md`
- [x] Eval labels: two AI labelling passes against `prompts/signal_extraction.system.md` (first pass in `ai_product/eval/labels_first_pass.csv`, agreement 90–97.5%), 6 disagreements reviewed, second pass is `ref_*`. Say "AI-labelled, reviewed", never "hand-labelled"
- [ ] Add the 37 measures to the Fabric model and publish report v2 against it; take Fabric screenshots of the 4 pages
- [x] Report v2 fixed in Fabric (report "LeadToSale v2"): font fallback stacks on 159 visuals, text fixes; page PNGs re-exported with `report_v2/export_pages.py` into `docs/img/page1-4.png`. Never run `fabric_publish.py report` again — the local PBIP predates these fixes; pull the definition from Fabric first
- [ ] Slides v3 — `docs/build_deck_v3.js` → `docs/presentation_v3.pptx` (20 main + 5 backup, English slides, no speaker notes — talk track is a Word file outside the repo); data story = slides 6–10 (architecture, one lead through the layers, Bronze+Silver rules, Gold, semantic model); charts render in PowerPoint, not Keynote. "40–80" was an Istanbul-branch assumption; use "Istanbul advisors: 40–70 open leads" (Gold: Istanbul 44–66, network median 35) — report text already updated in Fabric

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
