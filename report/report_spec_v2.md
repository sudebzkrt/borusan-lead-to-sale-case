# Power BI report v2 — page spec

Four pages, same names as v1 so the Fabric report can be updated page by page. Canvas 1280 × 720, theme
`report_v2/LeadToSale.Report/StaticResources/RegisteredResources/BorusanLeadTheme.json` (import it once: View → Themes →
Browse for themes). Every visual title states a finding; the subtitle says what the chart is. Field display names are
set on the visual (right-click the field → Rename for this visual), the model keeps its technical column names.

Design rules that apply everywhere

* One question per page, written under the page title. If a visual does not help answer it, it is not on the page.
* Titles are sentences with a number in them. "Conversion by dealer" is a label; "Two authorized dealers convert below
  75% of the network" is a finding.
* One accent colour per chart. Blue = default series, orange = the thing being pointed at (digital sources, errors),
  red / green only for the dealer flag. Grey for "everything else".
* Data labels on, gridlines light, no axis titles, no legends for single-series charts.
* Numbers formatted in the model (percent 1 dp, thousands separator) — never "450 %" or "15347000" on a page.
* No visual shows a scrollbar at 1280 × 720. If it does, the chart has too many categories or too little height.

Global slicers (top right, synced across pages 1–3): `dim_date[year_quarter]` ("Quarter"), `dim_vehicle[brand]`,
`dim_dealer[region]`, `dim_lead_source[source_group]` ("Source") — four equal dropdowns, 118 × 68 px, header on.
A date range ("between") slicer does not fit the header strip, so the period is picked by quarter.

---

## Page 1 · Funnel Overview

Question: *How is the lead-to-sale funnel performing, and where does it leak?*
Page title: **18% of leads become sales — the leak is in the digital channels**

| # | Visual | Fields | Title / notes |
|---|---|---|---|
| 1 | 5 cards | `[Leads]`, `[Test Drive Rate]`, `[Offer Rate]`, `[Lead-to-Sale Conversion]` (orange), `[Revenue (bn TRY)]` | subtitle = measure text (`KPI Sub …`) so the second line is live: "5,686 test drives", "2,736 won · closed-lead basis 21.0%" |
| 2 | Funnel | `[Funnel Leads]`, `[Funnel Offers]`, `[Funnel Won]` (three measures, no category) | "Half of leads get an offer; 38% of offers close" · sequential blues |
| 3 | Bar | `dim_lead_source[source_label]` × `[Lead-to-Sale Conversion]`, sorted desc; fill = `[Source Bar Colour]`; constant line = `[Network Conversion]` | "Referral and showroom convert 6× better than digital sources" |
| 4 | Stacked column | `dim_date[year_quarter]` × `[Leads Non-digital]`, `[Leads Digital]` | "Digital brings 55% of leads at 7% conversion — the queue the assistant ranks" |
| 5 | Line (full width) | `dim_date[year_month]` × `[Conversion Rate (Closed)]` | "Closed-lead conversion holds near 20% while volume tripled — December peaks, January–February dips". Uses the *closed* rate so the last months are not understated by open leads — say this out loud in the demo. |
| 6 | 3 small cards + text box | `[Open Leads]`, `[Stale Open Leads]` (orange), `[Stale Pipeline %]` | "A third of the open pipeline is stale" — the bridge to part 2 |

Dropped from v1: lost-reason bar (flat at 13–15% for every reason in this data — a chart that cannot change a decision
does not earn its space; say that if asked), the 3-month rolling line (the closed rate is the honest fix).

## Page 2 · Dealer & Advisor Performance

Question: *Which dealers are behind, and is it speed or closing?*
Page title: **Two authorized dealers convert below 75% of the network — on every channel**

| # | Visual | Fields | Title / notes |
|---|---|---|---|
| 1 | 5 cards | `[Network Conversion]`, `[Avg First Response (h)]`, `[Dealers At Risk]` (orange), `[Best Dealer Conversion]` (subtitle `[Best Dealer Name]`), `[Response SLA Met %]` | |
| 2 | Bar (tall, left) | `dim_dealer[dealer_name]` × `[Lead-to-Sale Conversion]`, sorted desc, fill = `[Dealer Bar Colour]`, constant line `[Network Conversion]`, visual filter `dealer_name ≠ Unknown dealer` | "Conversion by dealer vs network average" · red = at risk, green = star, rest grey-blue |
| 3 | Clustered column | `fact_leads[response_band]` × `[Conversion Non-digital]`, `[Conversion Digital]`; filter `response_band ≠ n/a`; sort by `response_band_order` | "Answering within an hour lifts conversion in both digital and non-digital leads" — two series because source mix confounds the raw effect (showroom leads answer in 0.4 h); showing both is what makes the claim honest |
| 4 | Table | `dealer_name`, `[Leads]`, `[Lead-to-Sale Conversion]`, `[Dealer Conversion Rank]`, `[Avg First Response (h)]`, `[Response SLA Met %]`, `[Revenue (M TRY)]`, `[Dealer Performance Flag]` (font colour = `[Dealer Bar Colour]`); totals off; Unknown dealer excluded | "Dealer scorecard" · 8 columns, not 12 |

Dropped from v1: the 15-colour scatter (legend unreadable, x-range 6.4–8.0 h hides the effect — the bands show it),
the advisor bar with a scrollbar (advisors are one click away: click a dealer bar), units-sold line by dealer type.

## Page 3 · Model & Segment Mix

Question: *What sells, at what discount, and how is electrification moving?*
Page title: **MINI Cooper and the X1 / iX1 pair carry volume; conversion halves above 10M TRY**

| # | Visual | Fields | Title / notes |
|---|---|---|---|
| 1 | 5 cards | `[Units Sold]`, `[Avg Sale Price (M TRY)]`, `[Realised Discount %]`, `[Financing Share]`, `[Pipeline Value (bn TRY)]` | |
| 2 | Stacked bar (tall, left) | `dim_vehicle[model_label]` × `[Units Sold]`, legend `dim_vehicle[brand]` (BMW blue, MINI orange, Land Rover green), visual filter `[Model Units Rank] ≤ 15` | "Units sold by model — top 15" |
| 3 | 100% stacked column | `dim_date[year_quarter]` × `[Units Electrified]`, `[Units Combustion]`; filter `[Units Sold] > 20` (drops the 13 back-dated DQ sales) | "Electrified models hold about half of sales every quarter" |
| 4 | Bar | `dim_vehicle[price_band]` × `[Lead-to-Sale Conversion]`; filter `price_band ≠ Unknown`; sort by `price_band_order` | "Conversion falls from 23% under 4M TRY to 9% above 10M TRY" |

Dropped from v1: the 30-colour treemap, the model table with unformatted prices, 4-fuel stacked bars sorted by value.

## Page 4 · Data Quality Monitor

Question: *How much did Silver repair, and can the numbers on the other pages be trusted?*
Page title: **5,031 rows repaired or flagged in 25 checks — only exact duplicates were dropped**

| # | Visual | Fields | Title / notes |
|---|---|---|---|
| 1 | 5 cards | `[DQ Checks Run]`, `[DQ Error Checks]` (orange), `[DQ Failed Rows]`, `[Leads With DQ Flags %]`, `[DQ Last Run]` | |
| 2 | Bar (tall, left) | `dq_results[check_name]` × `[DQ Failed Rows]`, fill = `[Severity Colour]`, filter `[DQ Failed Rows] > 0`, sorted desc | "Most repairs are formatting; the errors are orphan keys and duplicates" |
| 3 | Bar | `dq_results[action]` × `[DQ Failed Rows]` | "What Silver did with each problem — a flag never deletes a row" |
| 4 | Text box | two paragraphs: what a flag means; ground truth 12/18 exact | "How to read this page" |

Dropped from v1: the 8-column dq_results dump with `run_ts` on every row.

---

## Migration from the PBIP to your Fabric semantic model (`sm_lead_to_sale`)

1. Paste `semantic_model/measures_v2_additions.dax` into `_Measures` (37 measures, all additive; names must match exactly).
2. Set the format strings noted in that file (percent 1 dp, `#,0`, `0.0`).
3. Either **(a)** open `report_v2/LeadToSale.pbip` in Power BI Desktop, File → Publish to your Fabric workspace, then in the
   service open the report's settings and re-point it to `sm_lead_to_sale` (or edit `LeadToSale.Report/definition.pbir` to the
   `byConnection` form with your workspace and model name before opening — see `report_v2/README.md`), or **(b)** rebuild the
   four pages in the Fabric report editor from the tables above (≈ 2 hours; the theme JSON gives you the colours and fonts).
4. Sync the four slicers (View → Sync slicers) if they come through unsynced.
5. Take one screenshot per page at 1280 × 720 for the deck; export to PDF for a print-quality version.
