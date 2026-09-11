# Deliberate data-quality defects in the raw extracts

Generated with seed=42, scale=1.0. Counts are ground truth for validating Silver-layer DQ checks.

| Defect | Rows |
|---|---|
| `crm_interactions.mixed_timestamp_format` | 672 |
| `crm_leads.mixed_timestamp_format` | 101 |
| `customers.city_spelling_variants` | 352 |
| `customers.duplicate_records` | 180 |
| `customers.invalid_email` | 62 |
| `customers.missing_email` | 124 |
| `customers.phone_format_variants` | 742 |
| `interactions.empty_notes` | 1345 |
| `interactions.orphan_lead_id` | 202 |
| `leads.customer_id_points_to_duplicate` | 224 |
| `leads.exact_duplicate_rows` | 75 |
| `leads.missing_vehicle_id` | 225 |
| `leads.negative_response_hours` | 45 |
| `leads.orphan_customer_id` | 60 |
| `leads.orphan_or_malformed_dealer_id` | 120 |
| `leads.status_casing_variants` | 750 |
| `offers.impossible_discount_pct` | 43 |
| `offers.missing_final_price` | 71 |
| `sales.exact_duplicate_rows` | 27 |
| `sales.orphan_lead_id` | 11 |
| `sales.sale_date_before_lead_created` | 14 |
| `test_drives.missing_duration` | 171 |
| `test_drives.satisfaction_out_of_range` | 23 |

## Format-level defects (whole file)

- DMS extracts use `;` separator, decimal comma, `dd.MM.yyyy` dates, Turkish column names, `E/H` booleans, UTF-8 BOM.
- Web leads are nested JSON with camelCase keys and `+03:00` timestamps; CRM uses ISO without offset.
- Web-sourced leads exist only in `web_leads.json`; all other sources only in `crm_leads.csv` (Bronze must union).
- `advisors.csv` is master data but leads reference advisors that always exist; dealers referenced by leads may not.
