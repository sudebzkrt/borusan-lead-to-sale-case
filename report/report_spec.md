# Power BI report — page spec

Four pages, built on `sm_lead_to_sale`. Keep the visual count per page low (≤ 7); the interviewers are data
people and will read the numbers, not admire the layout. Suggested theme: default Fabric theme, one accent
colour for "won", grey for "lost", muted for "open".

Global slicers (sync across pages, top strip): **Date range** (dim_date, relative slicer defaulting to *last 12 months*),
**Brand** (dim_vehicle), **Region** (dim_dealer), **Source group** (dim_lead_source).

---

## Page 1 · Funnel Overview

Question the page answers: *How is the lead-to-sale funnel performing, and where does it leak?*

| Visual | Fields |
|---|---|
| KPI cards ×5 | `[Leads]`, `[Test Drive Rate]`, `[Offer Rate]`, `[Lead-to-Sale Conversion]`, `[Revenue (M TRY)]` — each with `Leads YoY %` / `Revenue YoY %` as trend where applicable |
| Funnel visual | Category = stage (use a small disconnected table *Funnel Stage* with rows Leads / Test Drives / Offers / Won and a SWITCH measure), Values = the four counts |
| Line chart | `[Lead-to-Sale Conversion]` and `[Conversion 3M Rolling]` by `dim_date[year_month]` |
| Clustered bar | `[Lead-to-Sale Conversion]` by `dim_lead_source[source_label]`, sorted desc, with `[Leads]` as tooltip |
| Bar | `[Lost Reason Share]` by `fact_leads[lost_reason]` |
| Card | `[Stale Pipeline %]` with `[Stale Open Leads]` as subtitle |

Talking point: web/social bring the volume, referral/showroom bring the conversion — the assistant in part 2 exists because the high-volume channels need triage.

## Page 2 · Dealer & Advisor Performance

Question: *Which dealers and advisors are above/below the network, and is it speed or closing that separates them?*

| Visual | Fields |
|---|---|
| Table (matrix) | rows `dim_dealer[dealer_name]`, columns: `[Leads]`, `[Lead-to-Sale Conversion]`, `[Dealer Conversion Rank]`, `[Avg First Response (h)]`, `[Response SLA Met %]`, `[Realised Discount %]`, `[Revenue (M TRY)]`, `[Dealer Performance Flag]` — conditional formatting on flag |
| Scatter | X `[Avg First Response (h)]`, Y `[Lead-to-Sale Conversion]`, size `[Leads]`, legend `dim_dealer[dealer_type]`, detail `dealer_name`. Shows the response-time effect the generator embedded |
| Bar | `[Lead-to-Sale Conversion]` by `dim_advisor[advisor_name]`, filtered to selected dealer (drill from matrix) |
| Map (optional) | `dim_dealer[city]` bubble size `[Units Sold]` |
| Line | `[Units Sold]` by `year_month`, legend `dealer_type` |

## Page 3 · Model & Segment Mix

Question: *What sells, at what discount, and how is electrification moving?*

| Visual | Fields |
|---|---|
| Treemap | `[Units Sold]` by `dim_vehicle[brand]` › `model_label` |
| Stacked column | `[Units Sold]` by `year_month`, legend `dim_vehicle[fuel_type]` (100% stacked variant for share) |
| Table | `model_label`, `[Leads]`, `[Lead-to-Sale Conversion]`, `[Avg Offer Discount %]`, `[Realised Discount %]`, `[Avg Sale Price (TRY)]`, `[Financing Share]` |
| Bar | `[Lead-to-Sale Conversion]` by `dim_vehicle[price_band]` — conversion falls with price, as expected |
| Card | `[Pipeline Value (TRY)]` |

## Page 4 · Data Quality Monitor

Question: *How much did Silver have to repair, and can I trust the numbers on the other pages?*

| Visual | Fields |
|---|---|
| Cards | `[DQ Error Checks]`, `[DQ Failed Rows]`, `[Leads With DQ Flags %]` |
| Table | `dq_results[table_name]`, `check_name`, `severity`, `action`, `failed_rows`, `total_rows`, `failed_pct` (bar conditional formatting), `run_ts` |
| Bar | `[DQ Failed Rows]` by `table_name`, legend `severity` |
| Text box | Two sentences: what a flag means, and that flagged rows are *kept*, with the action column stating what was done |

Talking point: this page is what the JD calls *veri kalitesi kontrollerinin gerçekleştirilmesi, veri tutarsızlıklarının tespit edilmesi*. The generator's ground truth means the checks were validated, not just written.

---

## Screenshots to put in the deck / repo

Save to `report/screenshots/`: one per page at 1920×1080, plus one of the model diagram view (relationships visible) and one of the lakehouse explorer showing the three schemas. These are the fallback if the live demo breaks.
