# %% [markdown]
# # 01 · Bronze — raw ingestion
#
# **Goal:** land every source file in the lakehouse *exactly as received*, as Delta tables, with lineage columns.
# No cleaning, no type casting, no business logic. Bronze is the audit trail: if Silver ever produces a wrong
# number, we can always come back here and see what the source actually sent.
#
# Three source systems + master data:
#
# | Source | Files | Why it is awkward |
# |---|---|---|
# | CRM | `crm_customers.csv`, `crm_leads.csv`, `crm_interactions.csv` | comma CSV, ISO timestamps, but some rows use `dd/MM/yyyy` |
# | Web forms | `web_leads.json` | nested JSON, camelCase, `+03:00` offset |
# | Dealer DMS | `dms_*.csv` | `;` separator, decimal comma, `dd.MM.yyyy`, Turkish headers, `E/H` booleans, UTF-8 BOM |
# | Master | `dealers.csv`, `vehicles.csv`, `advisors.csv` | clean |
#
# Everything is read **as string** on purpose. Parsing happens in Silver, where a failure can be logged as a data-quality
# issue instead of silently turning into `null` here.
#
# This notebook runs unchanged in Fabric (default lakehouse attached, schema-enabled) and locally (`run_local.sh`).

# %%
import os, sys
from datetime import datetime, timezone
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

# --- environment detection ---------------------------------------------------
# Fabric notebooks expose `notebookutils`; on a laptop it does not exist.
try:
    import notebookutils  # noqa: F401
    IS_FABRIC = True
except ImportError:
    IS_FABRIC = False

if IS_FABRIC:
    FILES_ROOT = "Files/raw"          # relative to the default lakehouse attached to this notebook
    TABLE_FORMAT = "delta"
else:
    from pyspark.sql import SparkSession
    REPO = os.environ.get("REPO_ROOT", os.getcwd())
    FILES_ROOT = os.path.join(REPO, "data", "raw")
    TABLE_FORMAT = os.environ.get("TABLE_FORMAT", "parquet")   # Delta jars need Maven; parquet keeps local runs simple
    # A Derby-backed Hive metastore under data/ keeps the bronze/silver/gold schemas visible across notebook runs,
    # mimicking what the lakehouse catalog does for us in Fabric.
    spark = (SparkSession.builder.appName("bronze").master("local[*]")
             .config("spark.sql.warehouse.dir", os.path.join(REPO, "data", "warehouse"))
             .config("spark.hadoop.javax.jdo.option.ConnectionURL",
                     f"jdbc:derby:;databaseName={os.path.join(REPO, 'data', 'metastore_db')};create=true")
             .enableHiveSupport().getOrCreate())

RUN_TS = datetime.now(timezone.utc)
spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")
print(f"IS_FABRIC={IS_FABRIC}  FILES_ROOT={FILES_ROOT}  TABLE_FORMAT={TABLE_FORMAT}")

# %% [markdown]
# ## Helper: write a raw DataFrame as a Bronze table
#
# Every Bronze table gets the same three lineage columns:
#
# * `_source_system` – crm / web / dms / master
# * `_source_file` – the file it came from
# * `_ingest_ts` – when this run landed it
#
# We use `overwrite` because this is a full-extract batch. With daily incremental files you would switch to
# `append` (and partition by ingest date) so history is preserved.

# %%
def write_bronze(df, name, source_system, source_file):
    df = (df.withColumn("_source_system", F.lit(source_system))
            .withColumn("_source_file", F.lit(source_file))
            .withColumn("_ingest_ts", F.lit(RUN_TS)))
    (df.write.format(TABLE_FORMAT).mode("overwrite")
       .option("overwriteSchema", "true")
       .saveAsTable(f"bronze.{name}"))
    print(f"bronze.{name:<22} {df.count():>7} rows  <- {source_file}")

def read_csv(path, sep=","):
    # header=true, everything as string, multiLine for notes that contain line breaks, quotes escaped
    return (spark.read.option("header", "true").option("sep", sep)
                 .option("multiLine", "true").option("escape", '"')
                 .option("encoding", "UTF-8").csv(path))

# %% [markdown]
# ## CRM extracts (comma CSV)

# %%
for name in ["crm_customers", "crm_leads", "crm_interactions"]:
    path = f"{FILES_ROOT}/crm/{name}.csv"
    write_bronze(read_csv(path), name, "crm", f"{name}.csv")

# %% [markdown]
# ## Web leads (nested JSON)
#
# The file is one JSON document with an `export` header and a `leads` array. `multiLine=true` reads the whole document
# as a single row; `explode` turns the array into one row per lead. We keep the nested struct as-is in Bronze —
# flattening is a Silver decision.

# %%
raw_json = spark.read.option("multiLine", "true").json(f"{FILES_ROOT}/web/web_leads.json")
web = (raw_json.select(F.col("export.exportedAt").alias("_export_ts"),
                       F.explode("leads").alias("lead"))
              .select("_export_ts", "lead.*"))
write_bronze(web, "web_leads", "web", "web_leads.json")

# %% [markdown]
# ## Dealer DMS extracts (Turkish locale)
#
# Separator `;` and a BOM at the start of the file. We do **not** convert decimal commas or dates here — Bronze keeps
# `4,07` as the string `4,07`. Silver will convert and count how many values fail.

# %%
for name in ["dms_test_drives", "dms_offers", "dms_sales"]:
    path = f"{FILES_ROOT}/dms/{name}.csv"
    df = read_csv(path, sep=";")
    # strip the BOM that the DMS puts in front of the first header
    first = df.columns[0]
    if first.startswith("\ufeff"):
        df = df.withColumnRenamed(first, first.lstrip("\ufeff"))
    write_bronze(df, name, "dms", f"{name}.csv")

# %% [markdown]
# ## Master data

# %%
for name in ["dealers", "vehicles", "advisors"]:
    write_bronze(read_csv(f"{FILES_ROOT}/master/{name}.csv"), name, "master", f"{name}.csv")

# %% [markdown]
# ## Sanity check
#
# Row counts per table plus a peek at the DMS offers table to confirm the raw Turkish formatting survived untouched.

# %%
for t in spark.sql("SHOW TABLES IN bronze").collect():
    n = spark.table(f"bronze.{t.tableName}").count()
    print(f"{t.tableName:<20} {n:>8}")

spark.table("bronze.dms_offers").select("TEKLIF_NO", "TEKLIF_TARIHI", "ISKONTO_ORANI", "NET_FIYAT", "FINANSMAN").show(5, truncate=False)
