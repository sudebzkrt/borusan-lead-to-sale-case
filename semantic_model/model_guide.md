# Semantic model — build guide (Direct Lake on `gold`)

Estimated time: 45–60 min in the Fabric web modelling view. Everything below is click-path level.

## 1. Create the model

1. Open the lakehouse → **SQL analytics endpoint** view (top-right switch) → **New semantic model**.
2. Name: `sm_lead_to_sale`. Select **only** the `gold` schema tables:
   `dim_date, dim_dealer, dim_vehicle, dim_advisor, dim_customer, dim_lead_source, fact_leads, fact_offers, fact_sales, fact_test_drives, dq_results`.
   Leave out `fact_interactions` and `lead_notes` (free text — no place in a BI model, and Direct Lake would page 67k text rows for nothing).
3. Open the model (**Open data model**). Storage mode shows *Direct Lake* — say that in the demo: no import, no refresh schedule, the report reads the Delta files Gold wrote.

## 2. Relationships

All are **many-to-one, single direction** (fact → dimension), cross-filter "Single". Do not turn on bi-directional filtering; it is the classic way to get ambiguous paths in a star schema.

| From (many) | To (one) | Note |
|---|---|---|
| fact_leads[created_date_key] | dim_date[date_key] | **active** — the funnel is reported by lead creation date |
| fact_leads[closed_date_key] | dim_date[date_key] | inactive; use with `USERELATIONSHIP` for "closed in month" |
| fact_leads[dealer_id] | dim_dealer[dealer_id] | |
| fact_leads[advisor_id] | dim_advisor[advisor_id] | |
| fact_leads[vehicle_id] | dim_vehicle[vehicle_id] | |
| fact_leads[customer_id] | dim_customer[customer_id] | |
| fact_leads[source] | dim_lead_source[source] | |
| fact_sales[sale_date_key] | dim_date[date_key] | active |
| fact_sales[dealer_id] | dim_dealer[dealer_id] | |
| fact_sales[advisor_id] | dim_advisor[advisor_id] | |
| fact_sales[vehicle_id] | dim_vehicle[vehicle_id] | |
| fact_sales[customer_id] | dim_customer[customer_id] | |
| fact_offers[offer_date_key] | dim_date[date_key] | |
| fact_offers[dealer_id] | dim_dealer[dealer_id] | |
| fact_offers[vehicle_id] | dim_vehicle[vehicle_id] | |
| fact_test_drives[scheduled_date_key] | dim_date[date_key] | |
| fact_test_drives[dealer_id] | dim_dealer[dealer_id] | |
| fact_test_drives[vehicle_id] | dim_vehicle[vehicle_id] | |

`dim_advisor[dealer_id]` → `dim_dealer` is deliberately **not** a relationship (snowflake); advisor rows already carry `dealer_name`.

Mark `dim_date` as the **date table** (Table tools → Mark as date table → column `date`). Without this, `SAMEPERIODLASTYEAR` refuses to work.

## 3. Measures

1. Create an empty table for measures: Home → **Enter data** → one column `x`, one row → name it `_Measures`. Hide column `x`.
   (In web modelling, create a *calculated table* `_Measures = ROW("x", 1)` if Enter data is not available.)
2. Paste every measure from `measures.dax` into `_Measures`. Order does not matter; DAX resolves references.
3. Format: rates as **percentage 1 dp**, money as **#,0** with display units *millions*, hours/days **0.0**.
4. Hide the raw numeric columns on facts that should never be summed directly (`first_response_hours`, `discount_pct`, `final_price_try`, …) — users then only see measures.

## 4. Sort & hierarchies

Text columns sort alphabetically unless told otherwise, and a chart axis inherits that. Set these once in the model
(select the column → Column tools → **Sort by column**), otherwise every trend chart comes out in a random-looking order:

* `dim_date[year_month]` → sort by `year_month_key`  ← the month axis on every trend chart
* `dim_date[month_name]` → `month`; `day_name` → `day_of_week`
* `dim_vehicle[price_band]` → `price_band_order`
* `fact_leads[response_band]` → `response_band_order`

Then, in each trend visual, set the visual's sort to the axis field ascending (… menu on the visual → Sort axis).

Hierarchies:

* Hierarchy `Calendar`: year › quarter › month_name.
* Hierarchy `Vehicle`: brand › model_label › trim_label.
* Hierarchy `Network`: region › city › dealer_name.

## 4b. Formats that bite

* Measures already expressed as a ratio (`Lead-to-Sale Conversion`, `Financing Share`, `Realised Discount %`, `Avg Offer Discount %`) → format **Percentage, 1 decimal**. `Avg Offer Discount %` divides by 100 in DAX for exactly this reason.
* `Revenue (M TRY)`, `Avg Sale Price (TRY)`, `Pipeline Value (TRY)` → **Whole number with thousands separator**; for the pipeline card use display units *Billions*, 2 decimals.
* Tables: switch off the **Totals** row where sums are meaningless (`dq_results` percentages, ranks, flags), or set those columns to *Don't summarize*.

## 5. Row-level security (mention, optional)

Role `DealerManager` on `dim_dealer`: `[dealer_id] = LOOKUPVALUE(...)` against a small `user_dealer` mapping table. Not built in two days, but it is the answer to "how would a dealer only see its own numbers?" — and it maps to the JD line about *veri erişimi, yetkilendirme*.

## 6. Verify against Gold

The last cell of `03_gold_star_schema` prints the funnel totals. In the report, a single card for each of
`[Leads]`, `[Test Drives]`, `[Offers Made]`, `[Won Leads]`, `[Revenue (TRY)]` must show the same numbers with no
filters applied. If they differ, a relationship is wrong (usually a missing `UNK` row or a many-to-many warning).
