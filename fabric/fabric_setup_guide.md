# Fabric setup — step by step (≈ 2 hours incl. first pipeline run)

Assumes a Fabric trial capacity is active on the tenant. Screens change often; the names below are from the
2026 UI, look for the equivalent if a button moved.

## 0. Before you start

* Chrome/Edge signed in to the trial tenant. Open **app.fabric.microsoft.com**.
* Have the repo on your laptop: you will upload `data/raw/**` and import the three `.ipynb` files.

## 1. Workspace

1. Workspaces → **New workspace** → name `borusan-lead-to-sale`. Advanced → License mode **Trial**. Create.
2. Workspace settings → **Spark settings** (optional): default is fine; note the runtime version — 1.3 (Spark 3.5) or 2.0 (Spark 4). The notebooks work on both.

## 2. Lakehouse with schemas

1. **+ New item → Lakehouse** → name `lh_borusan` → tick **Lakehouse schemas** (this is what lets us write `bronze.x`, `silver.x`, `gold.x` inside one lakehouse). Create.
   *If the checkbox is missing, create the lakehouse anyway and change every `schema.table` reference to `schema_table` — search for `f"bronze.` / `f"silver.` / `f"gold.` in the notebooks.*
2. In the lakehouse explorer, **Files → … → New subfolder** `raw`. Inside `raw`, upload the four folders `crm`, `dms`, `web`, `master` (Upload → Upload folder). Verify `Files/raw/crm/crm_leads.csv` shows up.
   *Alternative that impresses more: OneLake file explorer on Windows, drag-and-drop. Or the Data Factory Copy activity from a GitHub raw URL — see §5.*

## 3. Notebooks

1. **+ New item → Notebook → Import notebook** → select `fabric/notebooks/01_bronze_ingest.ipynb`, `02_silver_clean.ipynb`, `03_gold_star_schema.ipynb`, and `ai_product/train_lead_scorer.ipynb`.
2. Open each notebook → left pane **Lakehouses → Add** → pick `lh_borusan` → it must show as **default lakehouse** (pin icon). The notebooks use relative `Files/raw/...` paths, which only resolve against the default lakehouse.
3. Run `01` (Run all). Expected: 10 tables under `bronze` in the lakehouse explorer (refresh). ~2 min on first Spark start.
4. Run `02`. Expected: 12 tables under `silver`, the DQ table printed, and the ground-truth comparison mostly `OK`.
5. Run `03`. Expected: 13 tables under `gold` plus parquet exports under `Files/export/gold/`.
6. Run `train_lead_scorer`. First cell: `%pip install scikit-learn>=1.4` is **not** needed on Fabric runtime (it ships sklearn), but if the import fails add a cell `%pip install scikit-learn --quiet` at the top and restart. Expected: `gold.lead_scores` and the metrics printout.
7. For the app: download `Files/export/gold/*` (right-click folder → Download) into the repo's `data/gold/`, then run `streamlit run ai_product/app.py` locally. (Streamlit does not run inside Fabric; a Fabric-native alternative is a Power BI page on `gold.lead_scores` — mention that in the demo.)

## 4. Pipeline (Data Factory)

1. **+ New item → Data pipeline** → name `pl_lead_to_sale_daily`.
2. Add three **Notebook** activities in a row: `01_bronze_ingest` → `02_silver_clean` → `03_gold_star_schema` → (optional) `train_lead_scorer`. Connect them with the green **On success** arrows. Set each activity's *Workspace/Notebook*.
3. Add an **Outlook / Teams** activity (or a *Fail* activity) on the red **On failure** arrow of the Silver step — "pipeline failed" mail. This is the *izleme* (monitoring) story.
4. **Schedule**: daily 06:00 Europe/Istanbul. Save. Run once manually and take a screenshot of the run view (Monitor tab): that is the "operational" slide.
5. Optional variable: pipeline parameter `run_date`; not wired yet, mention as next step for incremental loads.

## 5. Optional: Copy activity for Bronze landing

Adds a real ingestion step instead of a manual upload. In the pipeline, before Bronze:

* **Copy data** activity → Source: **HTTP** connection, base URL `https://raw.githubusercontent.com/<user>/<repo>/main/data/raw/`, relative URL `crm/crm_leads.csv`, file format DelimitedText (but treat everything as string). Destination: Lakehouse `lh_borusan`, Files, folder `raw/crm`.
* Use a **ForEach** over a list of the 10 file paths if you want one activity to do all files.
* If GitHub is not reachable from the tenant, keep the manual upload and say so.

## 6. Semantic model + report

Follow `semantic_model/model_guide.md`, then `report/report_spec.md`. Create the report in the browser from the semantic model (**New report**). Power BI Desktop is optional; the browser is enough for four pages.

## 7. Things that go wrong, and the fix

| Symptom | Fix |
|---|---|
| `Path does not exist: Files/raw/...` | Default lakehouse not pinned, or `raw` uploaded to Tables instead of Files |
| `Schema bronze not found` / `saveAsTable` fails with schema | Lakehouse created without schemas — see §2 |
| Silver: `INCONSISTENT_BEHAVIOR_CROSS_VERSION` | The `timeParserPolicy=CORRECTED` line was skipped; run the config cell |
| Direct Lake model shows tables but no data | Refresh the SQL endpoint (lakehouse → SQL endpoint → Refresh) after new tables |
| Relationship shows many-to-many warning | `UNK` row missing or a dimension has duplicate keys; check `dim_customer` count = customers + 1 |
| Streamlit `FileNotFoundError data/gold/...` | Export not downloaded, or run `run_local.sh` to build Gold locally |
