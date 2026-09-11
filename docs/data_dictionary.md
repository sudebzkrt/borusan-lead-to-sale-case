# Data dictionary – raw extracts

All prices are TRY, illustrative 2026 list prices. Timestamps are Europe/Istanbul local time.

## master/dealers.csv

| Column | Type | Description |
|---|---|---|
| dealer_id | string PK | `D001`…`D014` |
| dealer_name | string | Branch name |
| city, region | string | Location |
| dealer_type | string | `own_retail` (Borusan Oto) or `authorized_dealer` |
| opened_year | int | |
| is_active | bool | |

## master/vehicles.csv (model/trim catalog)

| Column | Type | Description |
|---|---|---|
| vehicle_id | string PK | `V001`… |
| brand | string | BMW, MINI, Land Rover |
| model, trim | string | |
| body_type | string | Sedan, SUV, Hatchback, Gran Coupe, Crossover |
| fuel_type | string | Petrol, Diesel, PHEV, Electric |
| segment | string | Compact, Premium Mid, Executive, Luxury, Compact SUV, Mid SUV, Large SUV, Luxury SUV, Premium Small |
| list_price_try | int | List price |
| model_year | int | |

## master/advisors.csv

| Column | Type | Description |
|---|---|---|
| advisor_id | string PK | `A<dealer#><seq>` |
| advisor_name | string | |
| dealer_id | string FK | |

## crm/crm_customers.csv

| Column | Type | Description |
|---|---|---|
| customer_id | string PK | Duplicates with a different id exist (see DQ log) |
| full_name | string | Casing inconsistent in duplicates |
| customer_type | string | `individual` / `corporate` |
| gender | string | `M`/`F`, null for corporate |
| birth_date | date | null for corporate |
| email | string | may be null or malformed |
| phone | string | canonical `+905XXXXXXXXX`; ~12% in other formats |
| city | string | spelling variants exist (`Istanbul`, `ISTANBUL`, trailing space) |
| kvkk_consent, marketing_consent | bool | |
| created_at, updated_at | timestamp ISO | |

## crm/crm_leads.csv (all sources **except** `web_form`)

| Column | Type | Description |
|---|---|---|
| lead_id | string PK | exact duplicate rows exist |
| customer_id | string FK | some orphans |
| dealer_id | string FK | some orphans / malformed |
| advisor_id | string FK | |
| vehicle_id | string FK | ~1.5% null |
| source | string | showroom_walkin, call_center, campaign, social_media, referral, existing_customer |
| campaign_name | string | only for `campaign` |
| created_at | timestamp | ISO; ~1% `dd/MM/yyyy HH:mm` |
| first_contact_at | timestamp | null if not yet contacted |
| first_response_hours | float | hours from lead creation to first contact; a few negative |
| status | string | new, contacted, qualified, test_drive, offer, won, lost — casing inconsistent |
| lost_reason | string | price, bought_competitor, no_response, financing_rejected, timing, stock_unavailable, chose_other_model |
| closed_at | timestamp | null while open |
| budget_try | int | customer-stated budget, ~40% null |
| trade_in | bool | wants to trade in current car |

## web/web_leads.json (only `web_form` leads)

```
export.system, export.exportedAt, export.recordCount
leads[]:
  leadId, submittedAt (+03:00)
  form.type, form.campaign, form.utm.source, form.utm.medium
  customer.customerId
  interest.vehicleId, interest.preferredDealerId, interest.budget, interest.tradeIn
  crm.assignedAdvisorId, crm.status, crm.lostReason, crm.firstContactAt, crm.firstResponseHours, crm.closedAt
```
Maps 1:1 to `crm_leads.csv` columns after flattening; `source` = `web_form`.

## crm/crm_interactions.csv

| Column | Type | Description |
|---|---|---|
| interaction_id | string PK | |
| lead_id | string FK | some orphans |
| customer_id, advisor_id | string FK | |
| channel | string | phone, whatsapp, email, showroom_visit, sms |
| direction | string | inbound / outbound |
| interaction_at | timestamp | ISO; ~1% `dd.MM.yyyy HH:mm:ss` |
| duration_sec | int | phone and showroom only |
| notes | string | advisor free text (Turkish); ~2% empty. Input for the AI product |

## dms/dms_test_drives.csv (`;` separated)

| DMS column | Silver name | Description |
|---|---|---|
| TESTSURUS_ID | test_drive_id | PK |
| LEAD_ID | lead_id | FK |
| BAYI_KODU | dealer_id | |
| ARAC_KODU | vehicle_id | |
| PLANLANAN_TARIH | scheduled_at | `dd.MM.yyyy HH:mm` |
| TAMAMLANDI | completed | `E`/`H` |
| SURE_DK | duration_min | some null |
| MEMNUNIYET_PUANI | satisfaction_score | 1–5; a few out of range |
| DANISMAN_ID | advisor_id | |

## dms/dms_offers.csv (`;` separated, decimal comma)

| DMS column | Silver name | Description |
|---|---|---|
| TEKLIF_NO | offer_id | PK |
| LEAD_ID | lead_id | FK |
| ARAC_KODU, BAYI_KODU | vehicle_id, dealer_id | |
| TEKLIF_TARIHI | offer_date | `dd.MM.yyyy` |
| LISTE_FIYATI | list_price_try | |
| ISKONTO_ORANI | discount_pct | decimal comma; a few impossible (>100, <0) |
| NET_FIYAT | final_price_try | some null |
| FINANSMAN | financing | `E`/`H` |
| GECERLILIK_TARIHI | valid_until | |
| TEKLIF_DURUMU | offer_status | accepted, rejected, expired, open |

## dms/dms_sales.csv (`;` separated, decimal comma)

| DMS column | Silver name | Description |
|---|---|---|
| SATIS_NO | sale_id | PK; exact duplicate rows exist |
| LEAD_ID | sale lead | FK; some orphans |
| MUSTERI_ID | customer_id | |
| BAYI_KODU, ARAC_KODU, DANISMAN_ID | dealer_id, vehicle_id, advisor_id | |
| SATIS_TARIHI | sale_date | `dd.MM.yyyy`; a few before lead creation |
| TESLIMAT_TARIHI | delivery_date | |
| NET_FIYAT | final_price_try | |
| ODEME_TIPI | payment_type | financing, cash, bank_transfer |
| TAKAS_DEGERI | trade_in_value_try | null when no trade-in |
| SASE_NO | vin | |

## Gold layer (target)

Facts: `fact_leads` (grain: lead; funnel flags + durations), `fact_test_drives`, `fact_offers`, `fact_sales`, `fact_interactions`.
Dimensions: `dim_customer` (deduplicated, golden record), `dim_vehicle`, `dim_dealer`, `dim_advisor`, `dim_lead_source`, `dim_date`.
Plus `dq_results` (check name, table, rows failed, run timestamp) for the DQ monitor page.
