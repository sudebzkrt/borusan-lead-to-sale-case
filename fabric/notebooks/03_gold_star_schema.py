# %% [markdown]
# # 03 · Gold — star schema for the semantic model
#
# **Goal:** reshape the clean Silver entities into a **star schema** that Power BI can consume through Direct Lake
# without any further transformation: a handful of *dimension* tables (who / what / where / when) and *fact* tables
# (events with numbers), joined on simple keys.
#
# Why a star schema instead of pointing Power BI at Silver directly?
#
# * Measures stay simple — `SUM(fact_sales[final_price_try])` instead of a join inside DAX.
# * One filter (e.g. a dealer in a slicer) flows through every fact table via the shared dimension.
# * Direct Lake performs best on narrow facts with integer/date keys and few columns.
#
# Design decisions to explain in the interview:
#
# * **Natural keys** (`dealer_id`, `vehicle_id`…) are kept as keys. Surrogate integer keys and SCD2 history are the
#   obvious next step when dealers get renamed or reassigned.
# * Every foreign key that can be unknown gets an explicit **`UNK` row** in its dimension, so a lead with a broken
#   dealer id still shows in the funnel (under "Unknown dealer") instead of vanishing from a left-join.
# * `fact_leads` is a **wide, one-row-per-lead** table with the whole funnel pre-joined (test drive? offer? sale?).
#   This makes conversion measures trivial and is also the feature table for the AI product.
# * Interaction notes are kept in `fact_interactions.notes` and pre-aggregated into `lead_notes` — the semantic
#   model hides these text columns, the AI product reads them.
# * `dq_results` is copied into Gold so the report can show a data-quality page.

# %%
import os
from datetime import datetime, timezone
from pyspark.sql import functions as F, Window as W
from pyspark.sql.types import IntegerType, DoubleType, LongType

try:
    import notebookutils  # noqa: F401
    IS_FABRIC = True
except ImportError:
    IS_FABRIC = False

if IS_FABRIC:
    TABLE_FORMAT = "delta"
    EXPORT_DIR = "Files/export/gold"          # downloadable copies for the AI product / local demo
else:
    from pyspark.sql import SparkSession
    REPO = os.environ.get("REPO_ROOT", os.getcwd())
    TABLE_FORMAT = os.environ.get("TABLE_FORMAT", "parquet")
    EXPORT_DIR = os.path.join(REPO, "data", "gold")
    spark = (SparkSession.builder.appName("gold").master("local[*]")
             .config("spark.sql.warehouse.dir", os.path.join(REPO, "data", "warehouse"))
             .config("spark.hadoop.javax.jdo.option.ConnectionURL",
                     f"jdbc:derby:;databaseName={os.path.join(REPO, 'data', 'metastore_db')};create=true")
             .enableHiveSupport().getOrCreate())

spark.conf.set("spark.sql.session.timeZone", "Europe/Istanbul")
spark.sql("CREATE SCHEMA IF NOT EXISTS gold")
RUN_TS = datetime.now(timezone.utc)

def silver(name):
    return spark.table(f"silver.{name}")

def write_gold(df, name, export=True):
    (df.write.format(TABLE_FORMAT).mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"gold.{name}"))
    n = df.count()
    if export:
        df.coalesce(1).write.mode("overwrite").parquet(f"{EXPORT_DIR}/{name}")
        if not IS_FABRIC:  # stable file name locally so re-runs replace instead of accumulate
            import glob, shutil
            for f in glob.glob(f"{EXPORT_DIR}/{name}/*"):
                if f.endswith(".parquet") and not f.endswith(f"{name}.parquet"):
                    shutil.move(f, f"{EXPORT_DIR}/{name}/{name}.parquet")
                elif not f.endswith(".parquet"):
                    os.remove(f)
    print(f"gold.{name:<18} {n:>7} rows")

def date_key(col):
    return F.date_format(col, "yyyyMMdd").cast(IntegerType())

# %% [markdown]
# ## Load Silver

# %%
leads, customers, xref = silver("leads"), silver("customers"), silver("customer_xref")
inter, td, offers, sales = silver("interactions"), silver("test_drives"), silver("offers"), silver("sales")
dealers, vehicles, advisors = silver("dealers"), silver("vehicles"), silver("advisors")

# "Today" for the dataset = the last lead creation date. Open-lead ageing is computed against this instead of
# the wall clock so the numbers stay stable when the demo is re-run months later.
DATA_END = leads.agg(F.max("created_at")).first()[0]
print("DATA_END =", DATA_END)

# %% [markdown]
# ## dim_date
#
# A conformed calendar covering the whole data range plus a year of headroom. Power BI needs it for time
# intelligence (`SAMEPERIODLASTYEAR`, month-over-month) and for a single date slicer that drives every fact.

# %%
# Range = the earliest and latest date on ANY fact, not just leads. The 13 sales flagged "sale_date_before_lead_created"
# sit ~400 days before their lead; if dim_date started at the first lead they would fall into a "(Blank)" month in Power BI.
d_min = min(leads.agg(F.min(F.to_date("created_at"))).first()[0], sales.agg(F.min("sale_date")).first()[0])
d_max = max(leads.agg(F.max(F.to_date("closed_at"))).first()[0], sales.agg(F.max("delivery_date")).first()[0])
dim_date = (spark.sql(f"SELECT explode(sequence(to_date('{d_min}'), date_add(to_date('{d_max}'), 365), interval 1 day)) AS date")
            .select(date_key("date").alias("date_key"), "date",
                    F.year("date").alias("year"), F.quarter("date").alias("quarter"), F.month("date").alias("month"),
                    F.date_format("date", "MMM").alias("month_name"), F.date_format("date", "yyyy-MM").alias("year_month"),
                    F.date_format("date", "yyyyMM").cast(IntegerType()).alias("year_month_key"),   # "Sort by column" target for year_month
                    F.concat(F.year("date"), F.lit("-Q"), F.quarter("date")).alias("year_quarter"),
                    F.weekofyear("date").alias("week_of_year"), F.dayofweek("date").alias("day_of_week"),
                    F.date_format("date", "EEE").alias("day_name"), F.dayofweek("date").isin(1, 7).alias("is_weekend")))
write_gold(dim_date, "dim_date")

# %% [markdown]
# ## Dimensions
#
# Each dimension = Silver entity + a few *descriptive* attributes that make slicing pleasant (price band, age band,
# source group) + an `UNK` member for broken foreign keys.

# %%
unk_dealer = spark.createDataFrame([("UNK", "Unknown dealer", "Unknown", "Unknown", "unknown", None, None)], dealers.schema)
dim_dealer = dealers.unionByName(unk_dealer).withColumn("dealer_label", F.concat("dealer_id", F.lit(" · "), "dealer_name"))
write_gold(dim_dealer, "dim_dealer")

unk_vehicle = spark.createDataFrame([("UNK", "Unknown", "Unknown", "Unknown", "Unknown", "Unknown", "Unknown", None, None)], vehicles.schema)
dim_vehicle = (vehicles.unionByName(unk_vehicle)
               .withColumn("model_label", F.when(F.col("vehicle_id") == "UNK", "Unknown vehicle").otherwise(F.concat("brand", F.lit(" "), "model")))
               .withColumn("trim_label", F.when(F.col("vehicle_id") == "UNK", "Unknown vehicle").otherwise(F.concat("brand", F.lit(" "), "model", F.lit(" "), "trim")))
               .withColumn("price_band", F.when(F.col("list_price_try").isNull(), "Unknown")
                                          .when(F.col("list_price_try") < 4_000_000, "< 4M")
                                          .when(F.col("list_price_try") < 6_000_000, "4–6M")
                                          .when(F.col("list_price_try") < 10_000_000, "6–10M")
                                          .otherwise("10M+"))
               # Power BI sorts text alphabetically; give every band a number to "Sort by column"
               .withColumn("price_band_order", F.when(F.col("list_price_try").isNull(), 9)
                                                .when(F.col("list_price_try") < 4_000_000, 1)
                                                .when(F.col("list_price_try") < 6_000_000, 2)
                                                .when(F.col("list_price_try") < 10_000_000, 3)
                                                .otherwise(4))
               .withColumn("is_electrified", F.col("fuel_type").isin("Electric", "PHEV")))
write_gold(dim_vehicle, "dim_vehicle")

dim_advisor = (advisors.join(dealers.select("dealer_id", "dealer_name"), "dealer_id", "left")
               .select("advisor_id", "advisor_name", "dealer_id", "dealer_name"))
write_gold(dim_advisor, "dim_advisor")

age = F.floor(F.months_between(F.lit(DATA_END), F.col("birth_date")) / 12)
dim_customer = (customers.select("customer_id", "full_name", "customer_type", "gender", "city", "birth_date",
                                 "kvkk_consent", "marketing_consent", "created_at", "source_record_count")
                .withColumn("age_band", F.when(F.col("birth_date").isNull(), "n/a")
                                         .when(age < 30, "< 30").when(age < 40, "30–39").when(age < 50, "40–49")
                                         .when(age < 60, "50–59").otherwise("60+"))
                .withColumn("is_corporate", F.col("customer_type") == "corporate"))
unk_customer = spark.createDataFrame([("UNK", "Unknown customer", "unknown", None, "Unknown", None, None, None, None, None, "n/a", False)],
                                     dim_customer.schema)
dim_customer = dim_customer.unionByName(unk_customer)
write_gold(dim_customer, "dim_customer")

dim_lead_source = spark.createDataFrame([
    ("web_form", "Web form", "Digital", True), ("social_media", "Social media", "Digital", True),
    ("campaign", "Campaign", "Digital", True), ("call_center", "Call center", "Assisted", False),
    ("showroom_walkin", "Showroom walk-in", "Physical", False), ("referral", "Referral", "Relationship", False),
    ("existing_customer", "Existing customer", "Relationship", False)],
    ["source", "source_label", "source_group", "is_digital"])
write_gold(dim_lead_source, "dim_lead_source")

# %% [markdown]
# ## fact_leads — one row per lead, whole funnel pre-joined
#
# Sub-aggregations (first test drive, best offer, the sale, interaction stats) are computed per lead and joined
# back. `UNK` replaces null foreign keys so relationships in the semantic model never lose rows.

# %%
known_customers = set(r.customer_id for r in customers.select("customer_id").collect())

td_agg = (td.filter(~F.array_contains("dq_flags", "orphan_lead"))
            .groupBy("lead_id").agg(F.min("scheduled_at").alias("first_test_drive_at"),
                                    F.count("*").alias("test_drive_count"),
                                    F.max("satisfaction_score").alias("test_drive_satisfaction"),
                                    F.max(F.col("completed").cast("int")).alias("test_drive_completed")))
w_off = W.partitionBy("lead_id").orderBy(F.col("offer_date").desc())
off_agg = (offers.filter(~F.array_contains("dq_flags", "orphan_lead"))
                 .withColumn("_rn", F.row_number().over(w_off)).filter("_rn = 1")
                 .select("lead_id", F.col("offer_date").alias("last_offer_date"), F.col("discount_pct").alias("offer_discount_pct"),
                         F.col("final_price_try").alias("offer_final_price_try"), F.col("financing").alias("offer_financing"),
                         F.col("offer_status").alias("last_offer_status"))
                 .join(offers.groupBy("lead_id").agg(F.count("*").alias("offer_count")), "lead_id"))
sale_agg = (sales.filter(~F.array_contains("dq_flags", "orphan_lead"))
                 .groupBy("lead_id").agg(F.min("sale_date").alias("sale_date"), F.max("final_price_try").alias("sale_amount_try"),
                                         F.max("payment_type").alias("payment_type"),
                                         F.max((F.col("trade_in_value_try") > 0).cast("int")).alias("has_trade_in_sale")))
int_agg = (inter.filter(~F.array_contains("dq_flags", "orphan_lead"))
                .groupBy("lead_id").agg(F.count("*").alias("interaction_count"),
                                        F.sum((F.col("direction") == "inbound").cast("int")).alias("inbound_count"),
                                        F.sum((F.col("channel") == "showroom_visit").cast("int")).alias("showroom_visits"),
                                        F.sum((F.col("channel") == "whatsapp").cast("int")).alias("whatsapp_count"),
                                        F.max("interaction_at").alias("last_interaction_at"),
                                        F.min("interaction_at").alias("first_interaction_at")))

fact_leads = (leads
    .withColumn("dealer_id", F.coalesce("dealer_id", F.lit("UNK")))
    .withColumn("vehicle_id", F.coalesce("vehicle_id", F.lit("UNK")))
    .withColumn("customer_id", F.when(F.col("customer_id").isin(list(known_customers)), F.col("customer_id")).otherwise("UNK"))
    .join(td_agg, "lead_id", "left").join(off_agg, "lead_id", "left").join(sale_agg, "lead_id", "left").join(int_agg, "lead_id", "left")
    .withColumn("created_date_key", date_key("created_at"))
    .withColumn("closed_date_key", date_key("closed_at"))
    .withColumn("has_test_drive", F.col("test_drive_count").isNotNull())
    .withColumn("has_offer", F.col("offer_count").isNotNull())
    .withColumn("has_sale", F.col("sale_amount_try").isNotNull())
    .withColumn("response_within_24h", F.col("first_response_hours") <= 24)
    .withColumn("response_band", F.when(F.col("first_response_hours").isNull(), "n/a")
                                  .when(F.col("first_response_hours") <= 1, "≤ 1h").when(F.col("first_response_hours") <= 4, "1–4h")
                                  .when(F.col("first_response_hours") <= 24, "4–24h").when(F.col("first_response_hours") <= 72, "1–3 days")
                                  .otherwise("3+ days"))
    .withColumn("response_band_order", F.when(F.col("first_response_hours").isNull(), 9)
                                        .when(F.col("first_response_hours") <= 1, 1).when(F.col("first_response_hours") <= 4, 2)
                                        .when(F.col("first_response_hours") <= 24, 3).when(F.col("first_response_hours") <= 72, 4)
                                        .otherwise(5))
    .withColumn("days_to_test_drive", F.round((F.unix_timestamp("first_test_drive_at") - F.unix_timestamp("created_at")) / 86400.0, 1))
    .withColumn("days_to_offer", F.datediff("last_offer_date", F.to_date("created_at")))
    .withColumn("days_to_sale", F.datediff("sale_date", F.to_date("created_at")))
    .withColumn("lead_age_days", F.when(F.col("is_open"), F.datediff(F.lit(DATA_END), F.to_date("created_at"))))
    .withColumn("days_since_last_interaction", F.when(F.col("is_open"), F.datediff(F.lit(DATA_END), F.to_date("last_interaction_at"))))
    .withColumn("dq_flag_count", F.size("dq_flags"))
    .withColumn("dq_flags", F.concat_ws(",", "dq_flags"))   # string is friendlier for Power BI than an array
    .fillna({"test_drive_count": 0, "offer_count": 0, "interaction_count": 0, "inbound_count": 0,
             "showroom_visits": 0, "whatsapp_count": 0})
    .select("lead_id", "customer_id", "dealer_id", "advisor_id", "vehicle_id", "source", "campaign_name", "utm_source", "utm_medium",
            "created_at", "created_date_key", "first_contact_at", "closed_at", "closed_date_key",
            "status", "lost_reason", "is_won", "is_lost", "is_open",
            "first_response_hours", "response_within_24h", "response_band", "response_band_order", "budget_try", "trade_in",
            "has_test_drive", "test_drive_count", "first_test_drive_at", "test_drive_satisfaction", "days_to_test_drive",
            "has_offer", "offer_count", "last_offer_date", "offer_discount_pct", "offer_final_price_try", "offer_financing",
            "last_offer_status", "days_to_offer",
            "has_sale", "sale_date", "sale_amount_try", "payment_type", "days_to_sale", "days_to_close",
            "interaction_count", "inbound_count", "showroom_visits", "whatsapp_count",
            "first_interaction_at", "last_interaction_at", "lead_age_days", "days_since_last_interaction",
            "dq_flag_count", "dq_flags"))
write_gold(fact_leads, "fact_leads")

# %% [markdown]
# ## Event-grain facts
#
# Kept at their natural grain for the detail pages and for the AI product. Orphans (events whose lead does not
# exist) are excluded here — they are already counted in `dq_results`.

# %%
fact_test_drives = (td.filter(~F.array_contains("dq_flags", "orphan_lead"))
                      .withColumn("scheduled_date_key", date_key("scheduled_at"))
                      .withColumn("dq_flags", F.concat_ws(",", "dq_flags")))
write_gold(fact_test_drives, "fact_test_drives")

fact_offers = (offers.filter(~F.array_contains("dq_flags", "orphan_lead"))
                     .withColumn("offer_date_key", date_key("offer_date"))
                     .withColumn("discount_try", F.col("list_price_try") - F.col("final_price_try"))
                     .withColumn("is_accepted", F.col("offer_status") == "accepted")
                     .withColumn("dq_flags", F.concat_ws(",", "dq_flags")))
write_gold(fact_offers, "fact_offers")

fact_sales = (sales.join(vehicles.select("vehicle_id", "list_price_try"), "vehicle_id", "left")
                   .withColumn("customer_id", F.when(F.col("customer_id").isin(list(known_customers)), F.col("customer_id")).otherwise("UNK"))
                   .withColumn("sale_date_key", date_key("sale_date"))
                   .withColumn("delivery_date_key", date_key("delivery_date"))
                   .withColumn("discount_try", F.col("list_price_try") - F.col("final_price_try"))
                   .withColumn("realized_discount_pct", F.round(F.col("discount_try") / F.col("list_price_try") * 100, 2))
                   .withColumn("days_to_delivery", F.datediff("delivery_date", "sale_date"))
                   .withColumn("dq_flags", F.concat_ws(",", "dq_flags")))
write_gold(fact_sales, "fact_sales")

fact_interactions = (inter.filter(~F.array_contains("dq_flags", "orphan_lead"))
                          .withColumn("interaction_date_key", date_key("interaction_at"))
                          .withColumn("dq_flags", F.concat_ws(",", "dq_flags")))
write_gold(fact_interactions, "fact_interactions")

# %% [markdown]
# ## lead_notes — text feature table for the AI product
#
# All interaction notes of a lead in chronological order, one row per lead. The semantic model does not use it.

# %%
lead_notes = (fact_interactions.filter(F.col("notes").isNotNull())
              .withColumn("_line", F.concat(F.date_format("interaction_at", "yyyy-MM-dd"), F.lit(" ["), "channel", F.lit("] "), "notes"))
              .groupBy("lead_id").agg(F.concat_ws("\n", F.sort_array(F.collect_list(F.struct("interaction_at", "_line")))["_line"]).alias("notes_text"),
                                      F.count("*").alias("notes_count")))
# sort_array(struct) sorts by interaction_at, then we pull the text back out
write_gold(lead_notes, "lead_notes")

# %% [markdown]
# ## dq_results → Gold (for the Data Quality Monitor report page)

# %%
write_gold(silver("dq_results"), "dq_results")

# %% [markdown]
# ## Sanity: the funnel in numbers
#
# These are the numbers the Power BI measures must reproduce. If a DAX measure disagrees with this cell, the DAX is wrong.

# %%
f = spark.table("gold.fact_leads")
f.agg(F.count("*").alias("leads"),
      F.sum(F.col("has_test_drive").cast("int")).alias("test_drives"),
      F.sum(F.col("has_offer").cast("int")).alias("offers"),
      F.sum(F.col("is_won").cast("int")).alias("won"),
      F.sum(F.col("is_lost").cast("int")).alias("lost"),
      F.sum(F.col("is_open").cast("int")).alias("open"),
      F.round(F.avg(F.col("is_won").cast("int")) * 100, 1).alias("conv_pct"),
      F.round(F.avg("first_response_hours"), 1).alias("avg_resp_h"),
      F.round(F.avg(F.when(F.col("is_won"), F.col("days_to_close"))), 1).alias("avg_days_to_win")).show()
f.groupBy("source").agg(F.count("*").alias("leads"), F.round(F.avg(F.col("is_won").cast("int")) * 100, 1).alias("conv_pct")).orderBy(F.desc("conv_pct")).show()
f.groupBy("response_band_order", "response_band").agg(F.count("*").alias("leads"), F.round(F.avg(F.col("is_won").cast("int")) * 100, 1).alias("conv_pct")).orderBy("response_band_order").show()
spark.table("gold.fact_sales").agg(F.count("*").alias("sales"), F.sum("final_price_try").alias("revenue_try")).show()
