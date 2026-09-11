# Presentation outline — 12 slides, 15 minutes + demo

Language: Turkish or English, your call; slide titles below are English so they match the repo.
Rule: one idea per slide, numbers on the slide, talk over screenshots. Demo after slide 9.

| # | Title | Content | Asset |
|---|---|---|---|
| 1 | Lead-to-Sale Data Platform on Microsoft Fabric | name, date, one-line summary (the "big picture" sentence from the walkthrough) | — |
| 2 | The business problem | importer + dealer network; 15k leads/2 yrs, 18% convert; web brings volume, referral brings conversion; advisors work leads in CRM order | funnel numbers from Gold sanity cell |
| 3 | One dataset, two deliverables | ER diagram (customers → leads → test drives / offers / sales / interactions; vehicles, dealers); why synthetic, why deliberately dirty | README diagram |
| 4 | Source systems and their quirks | CRM CSV, web JSON, DMS `;`/decimal comma/dd.MM.yyyy/Turkish headers; 22 injected defect types with counts | `docs/dq_injections.md` table (top 10) |
| 5 | Architecture | Bronze → Silver → Gold in one schema-enabled lakehouse; Data Factory pipeline; Direct Lake semantic model; report; AI product reading Gold | diagram + lakehouse explorer screenshot |
| 6 | Bronze: land as-is | lineage columns; everything string; why | notebook cell screenshot |
| 7 | Silver: clean, conform, validate | the four rules; golden record dedup (180 merged); 25 DQ checks → `dq_results`; ground-truth comparison (12/18 exact) | DQ comparison output |
| 8 | Gold: star schema | fact_leads wide table, 6 dims, UNK rows, dim_date; funnel numbers | model diagram screenshot |
| 9 | Semantic model & report | Direct Lake, 40 measures, two conversion definitions, 4 pages | report page 1 screenshot |
| — | **Live demo** | Fabric: lakehouse → pipeline run → report page 1 & 2 → DQ page. Then Streamlit: ranked leads → one lead → next best action | — |
| 10 | AI product: Lead Intelligence Assistant | problem, what it does, hybrid rules+LLM, why | app screenshot |
| 11 | Model: how I avoided fooling myself | snapshots (point-in-time), outcome note removed, temporal split; AUC 0.82 / 0.84 pre-offer / lift 3.7×; calibration chart; limits | metrics + calibration |
| 12 | What I would do next | incremental MERGE, SCD2, RLS, SHAP, monthly retrain, LLM extraction at scale, Fabric-native app page | — |

Backup slides: pipeline Monitor screenshot; DAX for the two conversion measures; `signals.py` rule table; "how I used AI assistance".

Demo fallback order: live Fabric → screenshots → local `run_local.sh` output.
