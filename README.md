# Borusan Otomotiv – Lead-to-Sale Data Platform on Microsoft Fabric

Case study for the *Veri Yönetimi ve Uygulamaları Uzman Yardımcısı* position.
One synthetic dataset, two deliverables:

1. **Medallion architecture on Fabric** (Bronze → Silver → Gold) feeding a Power BI semantic model and report.
2. **AI-assisted data product**: a Lead Intelligence Assistant that scores open leads and suggests the next action, built on the Gold layer.

## Business scenario

Borusan Otomotiv imports BMW, MINI and Land Rover and sells through its own retail branches plus authorized dealers.
Every sale starts as a **lead** (web form, showroom walk-in, call center, campaign, social, referral) that is assigned
to a dealer and a sales advisor, may go through a **test drive** and an **offer**, and ends **won** (a sale) or **lost**.
Every touchpoint is logged as an **interaction** with the advisor's free-text notes.

```
CUSTOMERS ──┐
            ▼
DEALERS ── LEADS ── VEHICLES (catalog)
   ▲         │
   │         ├── TEST_DRIVES
ADVISORS     ├── OFFERS
             ├── SALES
             └── INTERACTIONS (free-text notes)
```

## Source systems (raw extracts)

| Source | Files | Format quirks |
|---|---|---|
| CRM | `crm_customers.csv`, `crm_leads.csv`, `crm_interactions.csv` | comma CSV, ISO timestamps, English column names |
| Web forms | `web_leads.json` | nested JSON, camelCase, `+03:00` offset; **web-sourced leads exist only here** |
| Dealer DMS | `dms_test_drives.csv`, `dms_offers.csv`, `dms_sales.csv` | `;` separator, decimal comma, `dd.MM.yyyy`, Turkish column names, `E/H` booleans, UTF-8 BOM |
| Master data | `dealers.csv`, `vehicles.csv`, `advisors.csv` | clean reference data |

Volumes (seed 42): ~6.2k customers, 15k leads, 5.7k test drives, 7.1k offers, 2.7k sales, 67k interactions, Sep 2024 – Aug 2026.

Defects are injected on purpose (duplicates, phone/city format variants, orphan keys, impossible discounts, mixed
timestamp formats, out-of-range scores). Ground-truth counts are in [`docs/dq_injections.md`](docs/dq_injections.md)
so Silver-layer checks can be verified. Column definitions are in [`docs/data_dictionary.md`](docs/data_dictionary.md).

The funnel has embedded causal structure — lead source, dealer, advisor, response time, test drive, discount, price
and seasonality all move conversion — so the lead-scoring model in part 2 has real signal to learn.

Regenerate: `pip install -r data_gen/requirements.txt && python data_gen/generate.py` (≈30 s).

## Repository layout

```
CLAUDE.md, AGENTS.md   context + working rules for AI assistants (status checklist lives in CLAUDE.md)
run_local.sh           whole pipeline on a laptop: generate → bronze → silver → gold → train
data_gen/              generator + requirements
data/raw/              source-system extracts (upload to Lakehouse Files/raw)
fabric/notebooks/      01_bronze_ingest · 02_silver_clean · 03_gold_star_schema  (.py = source, .ipynb = Fabric import)
fabric/fabric_setup_guide.md   click-path guide: workspace, lakehouse with schemas, notebooks, pipeline
semantic_model/        measures.dax (40 commented measures), model_guide.md (relationships, date table, RLS note)
report/                report_spec.md (4 pages, visual by visual), screenshots/
ai_product/            Lead Intelligence Assistant: signals.py, train_lead_scorer.py, llm.py, app.py, model/
docs/                  data_dictionary, dq_injections (ground truth), presentation_outline
```

## Part 1 – Medallion on Fabric

One schema-enabled lakehouse (`lh_borusan`) with `bronze`, `silver`, `gold` schemas; a Data Factory pipeline runs the three notebooks in order.

| Layer | What happens |
|---|---|
| Bronze | Raw files → Delta as-is, all columns string, plus `_source_system`, `_source_file`, `_ingest_ts`. |
| Silver | Seven timestamp formats, decimal commas, `E/H` booleans; phone → E.164, Turkish-aware city canon; customer golden record + `customer_xref`; CRM ∪ web leads; FK validation; every repair logged to `dq_results`; rows flagged, never silently dropped. Last cell compares counts with the generator's ground truth. |
| Gold | Star schema: `fact_leads` (one row per lead, funnel pre-joined), `fact_test_drives`, `fact_offers`, `fact_sales`, `fact_interactions`; `dim_customer`, `dim_vehicle`, `dim_dealer`, `dim_advisor`, `dim_lead_source`, `dim_date`, with `UNK` members; `lead_notes` for the AI product; `dq_results` copy. |

Semantic model: Direct Lake on Gold, single-direction star, `dim_date` marked as date table, measures in `_Measures`
(`semantic_model/measures.dax`). Report: Funnel overview · Dealer & advisor performance · Model & segment mix · Data quality monitor.

Funnel (seed 42): 15,000 leads → 5,686 test drives → 7,114 offers → 2,736 won (18.2%), 13.1 bn TRY revenue.

## Part 2 – Lead Intelligence Assistant

Ranks open leads by conversion probability with per-lead reasons and a suggested next action; optional LLM for
summary and a drafted customer message. Trained on point-in-time snapshots of closed leads (no outcome leakage),
validated with a temporal split: AUC 0.82 overall, 0.84 before the offer stage, 3.7× lift in the top decile.
Details in `ai_product/README.md`.

## Run everything locally

```
python -m venv .venv && . .venv/bin/activate      # Java 17+ required for PySpark
pip install -r requirements.txt
./run_local.sh
streamlit run ai_product/app.py
```

## Two-day plan

| When | Deliverable |
|---|---|
| Day 1 AM | Fabric workspace, lakehouse with schemas, upload raw, run 01–03 (`fabric/fabric_setup_guide.md`) |
| Day 1 PM | Data Factory pipeline + one run + Monitor screenshot; start semantic model (`semantic_model/model_guide.md`) |
| Day 2 AM | Finish model, 4 report pages, screenshots (`report/report_spec.md`) |
| Day 2 PM | Run `train_lead_scorer` in Fabric, app locally on exported Gold, slides (`docs/presentation_outline.md`), rehearsal |
