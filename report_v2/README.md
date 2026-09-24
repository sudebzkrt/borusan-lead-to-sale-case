# report_v2 — Power BI project (PBIP)

Open `LeadToSale.pbip` in Power BI Desktop (2025-06 or newer). The project has two parts:

* `LeadToSale.SemanticModel/` — an **import-mode** copy of the gold star schema, read from the parquet files with the
  `DataFolder` parameter. Same tables, columns, relationships and measure names as `sm_lead_to_sale` on Fabric, so the
  report is interchangeable between the two.
* `LeadToSale.Report/` — the four pages in PBIR (JSON) format plus the theme (`StaticResources/RegisteredResources/BorusanLeadTheme.json`).

The project was opened, refreshed and saved in Power BI Desktop, so it carries a data cache (`.pbi/cache.abf`) and
opens with data already loaded.

## First open on your laptop

1. Transform data → Edit parameters → set `DataFolder` to your `…/borusan-case/data/gold` folder (one sub-folder per table).
2. Refresh. All 12 tables load from parquet in a few seconds.
3. View → Sync slicers if the Date / Brand / Region / Source group slicers are not already synced.

## Pointing the report at the Fabric semantic model instead

The report is a "thin report" waiting to happen. To bind it to `sm_lead_to_sale`:

1. Add the measures from `../semantic_model/measures_v2_additions.dax` to `sm_lead_to_sale` (names must match exactly).
2. Replace `LeadToSale.Report/definition.pbir` with:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
  "version": "4.0",
  "datasetReference": {
    "byConnection": {
      "connectionString": "Data Source=powerbi://api.powerbi.com/v1.0/myorg/<WORKSPACE NAME>;Initial Catalog=sm_lead_to_sale"
    }
  }
}
```

3. Open the `.pbip` again — Desktop connects live to the Fabric model. Publish to the workspace from Desktop.

Alternative: publish the import version as-is (Home → Publish) and keep it next to the Direct Lake model as the
"laptop fallback" — this is also the safest demo path if the Fabric tenant is slow on the day.

## Files you may want to edit

| Where | What |
|---|---|
| `definition/pages/<page>/visuals/<visual>/visual.json` → `visualContainerObjects.title.text` | Visual titles (the findings) |
| `definition/pages/<page>/visuals/header/visual.json` | Page title and question |
| `StaticResources/RegisteredResources/BorusanLeadTheme.json` | Colours, fonts |
| `LeadToSale.SemanticModel/definition/tables/_Measures.tmdl` | All 78 measures with format strings |

The generator that produced the project is in `../build/` (`model.py`, `report.py`) — re-run it if you change the
layout in bulk; otherwise edit in Desktop and save.
