# %% [markdown]
# # 02 · Silver — clean, conform, validate
#
# **Goal:** turn the raw Bronze tables into one consistent, typed, deduplicated set of entities with the *same*
# column names and formats regardless of which source system they came from. Silver is where every data-quality
# decision is made explicit and logged.
#
# Rules we follow in this layer:
#
# 1. **Never silently drop a row.** A row with a problem is kept and gets a flag in `dq_flags` (an array of strings),
#    unless it is an exact duplicate. Gold decides what to do with flagged rows.
# 2. **Never silently null a value.** Every value we null or impute is counted in `silver.dq_results`.
# 3. **One entity, one table, one schema** — CRM leads and web leads become a single `silver.leads`.
# 4. **Ground truth exists.** `docs/dq_injections.md` lists the defects the generator injected; the last cell compares
#    our counts with it. In a real project you don't have that luxury, which is exactly why logging matters.
#
# Output tables: `customers`, `customer_xref`, `leads`, `interactions`, `test_drives`, `offers`, `sales`,
# `dealers`, `vehicles`, `advisors`, `dq_results`.

# %%
import os
from datetime import datetime, timezone
from pyspark.sql import functions as F, Window as W
from pyspark.sql.types import IntegerType, DoubleType, BooleanType, LongType

try:
    import notebookutils  # noqa: F401
    IS_FABRIC = True
except ImportError:
    IS_FABRIC = False

if IS_FABRIC:
    TABLE_FORMAT = "delta"
else:
    from pyspark.sql import SparkSession
    REPO = os.environ.get("REPO_ROOT", os.getcwd())
    TABLE_FORMAT = os.environ.get("TABLE_FORMAT", "parquet")
    # A Derby-backed Hive metastore under data/ keeps the bronze/silver/gold schemas visible across notebook runs,
    # mimicking what the lakehouse catalog does for us in Fabric.
    spark = (SparkSession.builder.appName("silver").master("local[*]")
             .config("spark.sql.warehouse.dir", os.path.join(REPO, "data", "warehouse"))
             .config("javax.jdo.option.ConnectionURL",
                     f"jdbc:derby:;databaseName={os.path.join(REPO, 'data', 'metastore_db')};create=true")
             .enableHiveSupport().getOrCreate())

# All source timestamps are Istanbul local time. Setting the session zone means ISO strings without an offset
# ("2026-04-14T16:43:42") and web strings with one ("...+03:00") land on the same instant.
spark.conf.set("spark.sql.session.timeZone", "Europe/Istanbul")
# CORRECTED = "a string that does not match the pattern is invalid (null)", instead of the Spark 2 fallback behaviour
# that raises INCONSISTENT_BEHAVIOR_CROSS_VERSION. Required for try_to_timestamp() to be a real "try".
spark.conf.set("spark.sql.legacy.timeParserPolicy", "CORRECTED")
spark.sql("CREATE SCHEMA IF NOT EXISTS silver")
RUN_TS = datetime.now(timezone.utc)
DQ = []   # (check_name, table, failed_rows, total_rows, severity, action)

def log_dq(check, table, failed, total, severity="warning", action="flagged"):
    DQ.append((check, table, int(failed), int(total), severity, action, RUN_TS))
    print(f"[DQ] {table:<14} {check:<34} {failed:>6} / {total}")

def write_silver(df, name):
    (df.write.format(TABLE_FORMAT).mode("overwrite").option("overwriteSchema", "true")
       .saveAsTable(f"silver.{name}"))
    print(f"silver.{name:<16} {df.count():>7} rows")

def bronze(name):
    return spark.table(f"bronze.{name}")

# %% [markdown]
# ## Parsing helpers
#
# `try_to_timestamp` returns `null` instead of raising when the pattern does not match, so we can chain several
# patterns with `coalesce` and count what remains unparsed. The DMS uses `dd.MM.yyyy`, an old CRM version used
# `dd/MM/yyyy HH:mm`, the web export adds `+03:00`.

# %%
TS_PATTERNS = ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ssXXX", "yyyy-MM-dd HH:mm:ss",
               "dd/MM/yyyy HH:mm", "dd.MM.yyyy HH:mm:ss", "dd.MM.yyyy HH:mm", "dd.MM.yyyy"]

def parse_ts(col):
    c = F.trim(F.col(col)) if isinstance(col, str) else col
    return F.coalesce(*[F.try_to_timestamp(c, F.lit(p)) for p in TS_PATTERNS])

def parse_date_dms(col):
    return F.to_date(F.try_to_timestamp(F.trim(F.col(col)), F.lit("dd.MM.yyyy")))

def decimal_comma(col):
    # "4,07" -> 4.07 ; already-dotted values pass through
    return F.regexp_replace(F.trim(F.col(col)), ",", ".").cast(DoubleType())

def eh_bool(col):
    return F.when(F.upper(F.trim(F.col(col))) == "E", True).when(F.upper(F.trim(F.col(col))) == "H", False)

def fold_tr(c):
    # Turkish-aware lowercase for matching keys: İstanbul / ISTANBUL / istanbul -> istanbul
    return F.translate(F.lower(F.translate(c, "İI", "ii")), "ıçğöşü", "icgosu")

def add_flag(df, cond, flag):
    return df.withColumn("dq_flags", F.when(cond, F.array_union(F.col("dq_flags"), F.array(F.lit(flag))))
                                       .otherwise(F.col("dq_flags")))

def with_flags(df):
    return df.withColumn("dq_flags", F.array().cast("array<string>"))

# %% [markdown]
# ## Master data
#
# Already clean; we only cast types. These are the reference sets used for referential-integrity checks below.

# %%
dealers = (bronze("dealers").select("dealer_id", "dealer_name", "city", "region", "dealer_type",
                                    F.col("opened_year").cast(IntegerType()), F.col("is_active").cast(BooleanType())))
vehicles = (bronze("vehicles").select("vehicle_id", "brand", "model", "trim", "body_type", "fuel_type", "segment",
                                      F.col("list_price_try").cast(LongType()), F.col("model_year").cast(IntegerType())))
advisors = bronze("advisors").select("advisor_id", "advisor_name", "dealer_id")
write_silver(dealers, "dealers"); write_silver(vehicles, "vehicles"); write_silver(advisors, "advisors")
valid_dealers = set(r.dealer_id for r in dealers.collect())
valid_vehicles = set(r.vehicle_id for r in vehicles.collect())

# %% [markdown]
# ## Customers — standardize, then find the golden record
#
# Problems in the source: phone numbers in five formats, city spelled four ways, missing or malformed e-mails, and
# ~3% of customers exist twice under different ids (same person re-entered by a second advisor).
#
# Strategy:
# * `phone_e164` — strip everything but digits, keep the last 10, require a leading `5` (Turkish mobile), prefix `+90`.
# * `city` — Turkish-aware fold, map to the canonical spelling.
# * `email` — lowercase; if it does not look like an e-mail, null it and flag.
# * **Deduplication** — same normalized phone ⇒ same person. The earliest-created record is the golden one;
#   every id maps to its golden id in `customer_xref`, which Leads/Sales use to re-point their foreign keys.

# %%
CITY_CANON = {"istanbul": "İstanbul", "ankara": "Ankara", "izmir": "İzmir", "bursa": "Bursa", "antalya": "Antalya",
              "kocaeli": "Kocaeli", "adana": "Adana", "gaziantep": "Gaziantep", "samsun": "Samsun",
              "eskisehir": "Eskişehir", "denizli": "Denizli", "konya": "Konya", "mersin": "Mersin", "mugla": "Muğla"}
city_map = F.create_map(*[x for k, v in CITY_CANON.items() for x in (F.lit(k), F.lit(v))])

c = bronze("crm_customers")
n_c = c.count()
digits = F.regexp_replace(F.col("phone"), "[^0-9]", "")
last10 = F.substring(digits, -10, 10)
c = with_flags(c.select(
    "customer_id", "full_name", "customer_type", "gender",
    F.to_date("birth_date").alias("birth_date"),
    F.lower(F.trim("email")).alias("email_raw"),
    F.col("phone").alias("phone_raw"),
    F.when((F.length(last10) == 10) & last10.startswith("5"), F.concat(F.lit("+90"), last10)).alias("phone_e164"),
    F.coalesce(city_map[fold_tr(F.trim(F.col("city")))], F.initcap(F.trim(F.col("city")))).alias("city"),
    F.col("kvkk_consent").cast(BooleanType()), F.col("marketing_consent").cast(BooleanType()),
    parse_ts("created_at").alias("created_at"), parse_ts("updated_at").alias("updated_at"),
))
email_ok = F.col("email_raw").rlike(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
c = c.withColumn("email", F.when(email_ok, F.col("email_raw")))
c = add_flag(c, F.col("email_raw").isNull(), "missing_email")
c = add_flag(c, F.col("email_raw").isNotNull() & ~email_ok, "invalid_email")
c = add_flag(c, F.col("phone_e164").isNull(), "unparseable_phone")
c = add_flag(c, F.col("phone_raw") != F.col("phone_e164"), "phone_reformatted")
log_dq("missing_email", "customers", c.filter(F.array_contains("dq_flags", "missing_email")).count(), n_c, action="kept_null")
log_dq("invalid_email", "customers", c.filter(F.array_contains("dq_flags", "invalid_email")).count(), n_c, action="nulled")
log_dq("phone_reformatted", "customers", c.filter(F.array_contains("dq_flags", "phone_reformatted")).count(), n_c, action="standardized")
log_dq("city_standardized", "customers",
       c.join(bronze("crm_customers").select("customer_id", F.col("city").alias("city_raw")), "customer_id")
        .filter(F.col("city_raw") != F.col("city")).count(), n_c, action="standardized")

# Golden record: earliest created_at per normalized phone; fall back to the id itself when the phone is unusable.
match_key = F.coalesce(F.col("phone_e164"), F.col("customer_id"))
w = W.partitionBy(match_key).orderBy(F.col("created_at").asc(), F.col("customer_id").asc())
c = (c.withColumn("_rn", F.row_number().over(w))
      .withColumn("golden_customer_id", F.first("customer_id").over(w)))
xref = c.select(F.col("customer_id").alias("source_customer_id"), "golden_customer_id",
                (F.col("_rn") > 1).alias("is_duplicate"))
n_dup = xref.filter("is_duplicate").count()
log_dq("duplicate_customer_merged", "customers", n_dup, n_c, severity="error", action="merged_into_golden")
customers = (c.filter("_rn = 1").drop("_rn", "golden_customer_id", "email_raw", "phone_raw")
              .join(xref.groupBy("golden_customer_id").agg(F.count("*").alias("source_record_count"))
                        .withColumnRenamed("golden_customer_id", "customer_id"), "customer_id"))
write_silver(customers, "customers")
write_silver(xref, "customer_xref")

# %% [markdown]
# ## Leads — one table from two systems
#
# Web leads arrive as nested JSON with camelCase keys; every other source comes from the CRM CSV. We map both to the
# same column list, union them, then:
#
# * drop exact duplicate rows (CRM re-export) — the only case where a row is removed;
# * parse three different timestamp formats;
# * normalize `status` casing;
# * re-point `customer_id` to the golden id via `customer_xref`;
# * validate foreign keys: an unknown dealer becomes `null` + flag (it will map to the *Unknown* dealer in Gold);
#   an unknown customer is kept + flagged; a missing vehicle is flagged;
# * negative response times become `null` + flag.

# %%
crm_leads = bronze("crm_leads").select(
    "lead_id", "customer_id", "dealer_id", "advisor_id", "vehicle_id", "source", "campaign_name",
    "created_at", "first_contact_at", "first_response_hours", "status", "lost_reason", "closed_at",
    "budget_try", "trade_in", F.lit(None).cast("string").alias("utm_source"), F.lit(None).cast("string").alias("utm_medium"))
web_leads = bronze("web_leads").select(
    F.col("leadId").alias("lead_id"), F.col("customer.customerId").alias("customer_id"),
    F.col("interest.preferredDealerId").alias("dealer_id"), F.col("crm.assignedAdvisorId").alias("advisor_id"),
    F.col("interest.vehicleId").alias("vehicle_id"), F.lit("web_form").alias("source"),
    F.col("form.campaign").alias("campaign_name"), F.col("submittedAt").alias("created_at"),
    F.col("crm.firstContactAt").alias("first_contact_at"),
    F.col("crm.firstResponseHours").cast("string").alias("first_response_hours"),
    F.col("crm.status").alias("status"), F.col("crm.lostReason").alias("lost_reason"),
    F.col("crm.closedAt").alias("closed_at"), F.col("interest.budget").cast("string").alias("budget_try"),
    F.col("interest.tradeIn").cast("string").alias("trade_in"),
    F.col("form.utm.source").alias("utm_source"), F.col("form.utm.medium").alias("utm_medium"))
raw_leads = crm_leads.unionByName(web_leads)
n_l_raw = raw_leads.count()
leads = raw_leads.dropDuplicates(["lead_id"])
log_dq("exact_duplicate_rows", "leads", n_l_raw - leads.count(), n_l_raw, severity="error", action="dropped")
n_l = leads.count()

leads = with_flags(leads.select(
    "lead_id", "customer_id", "dealer_id", "advisor_id",
    F.when(F.trim("vehicle_id") == "", None).otherwise(F.col("vehicle_id")).alias("vehicle_id"),
    F.lower(F.trim("source")).alias("source"), "campaign_name",
    parse_ts("created_at").alias("created_at"), parse_ts("first_contact_at").alias("first_contact_at"),
    F.col("first_response_hours").cast(DoubleType()).alias("first_response_hours"),
    F.lower(F.trim("status")).alias("status"), F.lower(F.trim("lost_reason")).alias("lost_reason"),
    parse_ts("closed_at").alias("closed_at"),
    F.col("budget_try").cast(DoubleType()).cast(LongType()).alias("budget_try"),
    F.lower(F.trim("trade_in")).isin("true", "1", "e").alias("trade_in"),
    "utm_source", "utm_medium"))

leads = add_flag(leads, F.col("created_at").isNull(), "unparseable_created_at")
log_dq("unparseable_created_at", "leads", leads.filter(F.array_contains("dq_flags", "unparseable_created_at")).count(),
       n_l, severity="error")
# status casing (count rows whose raw status differed from the normalized one)
n_status = raw_leads.dropDuplicates(["lead_id"]).filter(F.col("status") != F.lower(F.trim("status"))).count()
log_dq("status_casing_normalized", "leads", n_status, n_l, action="standardized")

# customer FK via xref (golden id)
leads = (leads.join(xref.select(F.col("source_customer_id").alias("customer_id"), "golden_customer_id"), "customer_id", "left")
              .withColumn("customer_id_src", F.col("customer_id"))
              .withColumn("customer_id", F.coalesce("golden_customer_id", "customer_id")).drop("golden_customer_id"))
leads = add_flag(leads, F.col("customer_id_src") != F.col("customer_id"), "customer_repointed_to_golden")
known_cust = customers.select("customer_id").withColumn("_ok", F.lit(True))
leads = leads.join(known_cust, "customer_id", "left")
leads = add_flag(leads, F.col("_ok").isNull(), "orphan_customer").drop("_ok")
log_dq("orphan_customer_id", "leads", leads.filter(F.array_contains("dq_flags", "orphan_customer")).count(), n_l, severity="error")
log_dq("customer_repointed_to_golden", "leads",
       leads.filter(F.array_contains("dq_flags", "customer_repointed_to_golden")).count(), n_l, action="repointed")

# dealer FK
bad_dealer = ~F.col("dealer_id").isin(list(valid_dealers)) | F.col("dealer_id").isNull()
leads = add_flag(leads, bad_dealer, "orphan_dealer")
leads = leads.withColumn("dealer_id", F.when(bad_dealer, None).otherwise(F.col("dealer_id")))
log_dq("orphan_or_malformed_dealer_id", "leads", leads.filter(F.array_contains("dq_flags", "orphan_dealer")).count(),
       n_l, severity="error", action="nulled_maps_to_unknown")
# vehicle
leads = add_flag(leads, F.col("vehicle_id").isNull(), "missing_vehicle")
leads = add_flag(leads, F.col("vehicle_id").isNotNull() & ~F.col("vehicle_id").isin(list(valid_vehicles)), "orphan_vehicle")
log_dq("missing_vehicle_id", "leads", leads.filter(F.array_contains("dq_flags", "missing_vehicle")).count(), n_l)
# negative response time
neg = F.col("first_response_hours") < 0
leads = add_flag(leads, neg, "negative_response_hours")
log_dq("negative_response_hours", "leads", leads.filter(neg).count(), n_l, action="nulled")
leads = leads.withColumn("first_response_hours", F.when(neg, None).otherwise(F.col("first_response_hours")))
# derived, source-independent business columns
leads = (leads.withColumn("is_won", F.col("status") == "won")
              .withColumn("is_lost", F.col("status") == "lost")
              .withColumn("is_open", ~F.col("status").isin("won", "lost"))
              .withColumn("days_to_close", F.when(F.col("closed_at").isNotNull(),
                                                  F.round((F.unix_timestamp("closed_at") - F.unix_timestamp("created_at")) / 86400.0, 1))))
write_silver(leads, "leads")
valid_leads = leads.select("lead_id").withColumn("_lead_ok", F.lit(True))
lead_created = leads.select("lead_id", F.col("created_at").alias("_lead_created_at"))

# %% [markdown]
# ## Interactions
#
# Mixed timestamp formats, a few orphan `lead_id`s (activity logged against a lead that was later deleted in the CRM),
# empty notes. Notes are trimmed but otherwise untouched — the AI product reads them from Gold.

# %%
i = bronze("crm_interactions")
n_i = i.count()
inter = with_flags(i.select(
    "interaction_id", "lead_id", "customer_id", "advisor_id",
    F.lower(F.trim("channel")).alias("channel"), F.lower(F.trim("direction")).alias("direction"),
    parse_ts("interaction_at").alias("interaction_at"),
    F.col("duration_sec").cast(DoubleType()).cast(IntegerType()).alias("duration_sec"),
    F.when(F.trim("notes") == "", None).otherwise(F.trim("notes")).alias("notes")))
inter = inter.join(valid_leads, "lead_id", "left")
inter = add_flag(inter, F.col("_lead_ok").isNull(), "orphan_lead").drop("_lead_ok")
inter = add_flag(inter, F.col("interaction_at").isNull(), "unparseable_timestamp")
inter = add_flag(inter, F.col("notes").isNull(), "empty_notes")
log_dq("orphan_lead_id", "interactions", inter.filter(F.array_contains("dq_flags", "orphan_lead")).count(), n_i, severity="error")
log_dq("unparseable_timestamp", "interactions", inter.filter(F.array_contains("dq_flags", "unparseable_timestamp")).count(), n_i, severity="error")
log_dq("empty_notes", "interactions", inter.filter(F.array_contains("dq_flags", "empty_notes")).count(), n_i)
write_silver(inter, "interactions")

# %% [markdown]
# ## Test drives (DMS)
#
# Rename Turkish headers, parse `dd.MM.yyyy HH:mm`, map `E/H` to boolean, and range-check the satisfaction score
# (1–5). Out-of-range scores are nulled and flagged rather than clipped — a `0` or a `10` tells us the DMS form
# validation is broken, and clipping would hide that.

# %%
t = bronze("dms_test_drives")
n_t = t.count()
td = with_flags(t.select(
    F.col("TESTSURUS_ID").alias("test_drive_id"), F.col("LEAD_ID").alias("lead_id"),
    F.col("BAYI_KODU").alias("dealer_id"), F.col("ARAC_KODU").alias("vehicle_id"), F.col("DANISMAN_ID").alias("advisor_id"),
    parse_ts("PLANLANAN_TARIH").alias("scheduled_at"), eh_bool("TAMAMLANDI").alias("completed"),
    F.col("SURE_DK").cast(DoubleType()).cast(IntegerType()).alias("duration_min"),
    F.col("MEMNUNIYET_PUANI").cast(DoubleType()).cast(IntegerType()).alias("satisfaction_raw")))
oor = F.col("satisfaction_raw").isNotNull() & ~F.col("satisfaction_raw").between(1, 5)
td = add_flag(td, oor, "satisfaction_out_of_range")
td = td.withColumn("satisfaction_score", F.when(oor, None).otherwise(F.col("satisfaction_raw"))).drop("satisfaction_raw")
td = add_flag(td, F.col("duration_min").isNull(), "missing_duration")
td = td.join(valid_leads, "lead_id", "left")
td = add_flag(td, F.col("_lead_ok").isNull(), "orphan_lead").drop("_lead_ok")
log_dq("satisfaction_out_of_range", "test_drives", td.filter(F.array_contains("dq_flags", "satisfaction_out_of_range")).count(), n_t, action="nulled")
log_dq("missing_duration", "test_drives", td.filter(F.array_contains("dq_flags", "missing_duration")).count(), n_t)
log_dq("orphan_lead_id", "test_drives", td.filter(F.array_contains("dq_flags", "orphan_lead")).count(), n_t, severity="error")
write_silver(td, "test_drives")

# %% [markdown]
# ## Offers (DMS)
#
# Decimal comma → double. A discount outside 0–50% is physically impossible for this business, so it is nulled and
# flagged. A missing net price is **imputed** from list price × (1 − discount) and flagged as `final_price_imputed`,
# because a revenue KPI with silent gaps is worse than one with a documented estimate.

# %%
o = bronze("dms_offers")
n_o = o.count()
offers = with_flags(o.select(
    F.col("TEKLIF_NO").alias("offer_id"), F.col("LEAD_ID").alias("lead_id"), F.col("ARAC_KODU").alias("vehicle_id"),
    F.col("BAYI_KODU").alias("dealer_id"), parse_date_dms("TEKLIF_TARIHI").alias("offer_date"),
    decimal_comma("LISTE_FIYATI").cast(LongType()).alias("list_price_try"),
    decimal_comma("ISKONTO_ORANI").alias("discount_raw"),
    decimal_comma("NET_FIYAT").cast(LongType()).alias("final_price_raw"),
    eh_bool("FINANSMAN").alias("financing"), parse_date_dms("GECERLILIK_TARIHI").alias("valid_until"),
    F.lower(F.trim("TEKLIF_DURUMU")).alias("offer_status")))
bad_disc = F.col("discount_raw").isNotNull() & ~F.col("discount_raw").between(0, 50)
offers = offers.withColumn("discount_pct", F.when(bad_disc, None).otherwise(F.col("discount_raw")))
offers = add_flag(offers, bad_disc, "impossible_discount")
missing_final = F.col("final_price_raw").isNull()
offers = offers.withColumn("final_price_try", F.when(
    missing_final & F.col("discount_pct").isNotNull(),
    F.round(F.col("list_price_try") * (1 - F.col("discount_pct") / 100), -3).cast(LongType())
).otherwise(F.col("final_price_raw")))
offers = add_flag(offers, missing_final, "final_price_imputed").drop("discount_raw", "final_price_raw")
offers = offers.join(valid_leads, "lead_id", "left")
offers = add_flag(offers, F.col("_lead_ok").isNull(), "orphan_lead").drop("_lead_ok")
log_dq("impossible_discount_pct", "offers", offers.filter(F.array_contains("dq_flags", "impossible_discount")).count(), n_o, severity="error", action="nulled")
log_dq("missing_final_price", "offers", offers.filter(F.array_contains("dq_flags", "final_price_imputed")).count(), n_o, action="imputed")
log_dq("orphan_lead_id", "offers", offers.filter(F.array_contains("dq_flags", "orphan_lead")).count(), n_o, severity="error")
write_silver(offers, "offers")

# %% [markdown]
# ## Sales (DMS)
#
# Exact duplicate rows are dropped (same `sale_id`, same content — a re-export). A sale dated before its lead was
# created is a timeline impossibility; we keep it (it *is* revenue) but flag it so the funnel duration measures can
# exclude it. `customer_id` is re-pointed to the golden record like in Leads.

# %%
s = bronze("dms_sales")
n_s_raw = s.count()
s = s.dropDuplicates(["SATIS_NO"])
log_dq("exact_duplicate_rows", "sales", n_s_raw - s.count(), n_s_raw, severity="error", action="dropped")
n_s = s.count()
sales = with_flags(s.select(
    F.col("SATIS_NO").alias("sale_id"), F.col("LEAD_ID").alias("lead_id"), F.col("MUSTERI_ID").alias("customer_id"),
    F.col("BAYI_KODU").alias("dealer_id"), F.col("ARAC_KODU").alias("vehicle_id"), F.col("DANISMAN_ID").alias("advisor_id"),
    parse_date_dms("SATIS_TARIHI").alias("sale_date"), parse_date_dms("TESLIMAT_TARIHI").alias("delivery_date"),
    decimal_comma("NET_FIYAT").cast(LongType()).alias("final_price_try"),
    F.lower(F.trim("ODEME_TIPI")).alias("payment_type"),
    decimal_comma("TAKAS_DEGERI").cast(LongType()).alias("trade_in_value_try"), F.col("SASE_NO").alias("vin")))
sales = (sales.join(xref.select(F.col("source_customer_id").alias("customer_id"), "golden_customer_id"), "customer_id", "left")
              .withColumn("customer_id", F.coalesce("golden_customer_id", "customer_id")).drop("golden_customer_id"))
sales = sales.join(valid_leads, "lead_id", "left").join(lead_created, "lead_id", "left")
sales = add_flag(sales, F.col("_lead_ok").isNull(), "orphan_lead")
before = F.col("_lead_created_at").isNotNull() & (F.col("sale_date") < F.to_date("_lead_created_at"))
sales = add_flag(sales, before, "sale_before_lead_created").drop("_lead_ok", "_lead_created_at")
log_dq("orphan_lead_id", "sales", sales.filter(F.array_contains("dq_flags", "orphan_lead")).count(), n_s, severity="error")
log_dq("sale_date_before_lead_created", "sales", sales.filter(F.array_contains("dq_flags", "sale_before_lead_created")).count(), n_s, severity="error")
write_silver(sales, "sales")

# %% [markdown]
# ## Persist the DQ log
#
# One row per check per run. Gold copies this table so the Power BI report can show a *Data Quality Monitor* page,
# and a pipeline can fail the run if any `error`-severity check exceeds a threshold.

# %%
dq_df = spark.createDataFrame(DQ, ["check_name", "table_name", "failed_rows", "total_rows", "severity", "action", "run_ts"])
dq_df = dq_df.withColumn("failed_pct", F.round(F.col("failed_rows") / F.col("total_rows") * 100, 3))
write_silver(dq_df, "dq_results")
dq_df.orderBy("table_name", "check_name").show(50, truncate=False)

# %% [markdown]
# ## Compare with ground truth (only possible because the data is synthetic)
#
# `docs/dq_injections.md` was written by the generator. Small differences are expected where two injected defects hit
# the same row (e.g. a duplicated customer that also got a phone variant), or where a check counts something slightly
# broader than the injection (e.g. `phone_reformatted` includes the duplicates' variant phones).

# %%
EXPECTED = {  # from docs/dq_injections.md, seed 42
    ("customers", "duplicate_customer_merged"): 180, ("customers", "missing_email"): 124, ("customers", "invalid_email"): 62,
    ("leads", "exact_duplicate_rows"): 75, ("leads", "orphan_or_malformed_dealer_id"): 120, ("leads", "missing_vehicle_id"): 225,
    ("leads", "orphan_customer_id"): 60, ("leads", "negative_response_hours"): 45, ("leads", "status_casing_normalized"): 750,
    ("leads", "customer_repointed_to_golden"): 224,
    ("offers", "impossible_discount_pct"): 42, ("offers", "missing_final_price"): 70,
    ("sales", "exact_duplicate_rows"): 27, ("sales", "orphan_lead_id"): 11, ("sales", "sale_date_before_lead_created"): 13,
    ("test_drives", "missing_duration"): 169, ("test_drives", "satisfaction_out_of_range"): 23,
    ("interactions", "orphan_lead_id"): 203, ("interactions", "empty_notes"): 1353,
}
got = {(r.table_name, r.check_name): r.failed_rows for r in dq_df.collect()}
for k, exp in EXPECTED.items():
    g = got.get(k)
    mark = "OK " if g == exp else ("~  " if g is not None and abs(g - exp) <= max(3, exp * 0.05) else "!! ")
    print(f"{mark} {k[0]:<13} {k[1]:<32} expected {exp:>5}  got {g}")
