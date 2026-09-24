#!/usr/bin/env bash
# Runs the whole Medallion pipeline on a laptop (no Fabric needed) and then trains the lead scorer.
# Needs: Java 17+, python 3.10+, `pip install -r requirements.txt`.
# Tables land in data/warehouse (parquet) with a Derby metastore in data/metastore_db; Gold is also exported to data/gold/.
set -euo pipefail
cd "$(dirname "$0")"
export REPO_ROOT="$PWD"
PY=${PYTHON:-python}
$PY data_gen/generate.py
$PY fabric/notebooks/01_bronze_ingest.py
$PY fabric/notebooks/02_silver_clean.py
$PY fabric/notebooks/03_gold_star_schema.py
$PY ai_product/train_lead_scorer.py
echo "done — start the app with: streamlit run ai_product/app.py"
