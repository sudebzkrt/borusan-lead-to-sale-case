"""Builds the TMDL semantic model for the Lead-to-Sale PBIP project.

Import mode over the gold parquet files (parameter DataFolder), same table / column / measure
names as the Direct Lake model so the report can be re-pointed at either.
"""
import glob, json, os, re, uuid
import pandas as pd

REPO_ROOT = os.environ.get('REPO_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLD = os.path.join(REPO_ROOT, 'data', 'gold') + os.sep
MEASURES_DAX = os.path.join(REPO_ROOT, 'semantic_model', 'measures.dax')

TABLES = ['fact_leads', 'fact_sales', 'fact_offers', 'fact_test_drives', 'dim_date', 'dim_dealer',
          'dim_vehicle', 'dim_advisor', 'dim_customer', 'dim_lead_source', 'dq_results']

# ----------------------------------------------------------------------------------------------
# Column typing
# ----------------------------------------------------------------------------------------------
OBJECT_TYPES = {  # object-typed parquet columns, resolved by hand from a data scan
    ('fact_leads', 'response_within_24h'): 'boolean', ('fact_leads', 'last_offer_date'): 'dateTime',
    ('fact_leads', 'offer_financing'): 'boolean', ('fact_leads', 'sale_date'): 'dateTime',
    ('fact_sales', 'sale_date'): 'dateTime', ('fact_sales', 'delivery_date'): 'dateTime',
    ('fact_offers', 'offer_date'): 'dateTime', ('fact_offers', 'valid_until'): 'dateTime',
    ('dim_date', 'date'): 'dateTime', ('dim_dealer', 'is_active'): 'boolean',
    ('dim_customer', 'birth_date'): 'dateTime', ('dim_customer', 'kvkk_consent'): 'boolean',
    ('dim_customer', 'marketing_consent'): 'boolean',
}

def dtype_to_tmdl(table, col, dt):
    s = str(dt)
    if (table, col) in OBJECT_TYPES:
        return OBJECT_TYPES[(table, col)]
    if s in ('str', 'string', 'object'):
        return 'string'
    if s.startswith('int'):
        return 'int64'
    if s.startswith('float'):
        return 'double'
    if s == 'bool':
        return 'boolean'
    if s.startswith('datetime'):
        return 'dateTime'
    raise ValueError(f'{table}.{col}: {s}')

# columns hidden from the field list (keys, sort helpers, raw numerics that measures cover)
HIDDEN = {
    'fact_leads': {'customer_id', 'dealer_id', 'advisor_id', 'vehicle_id', 'source', 'created_date_key',
                   'closed_date_key', 'response_band_order', 'first_response_hours', 'budget_try',
                   'offer_discount_pct', 'offer_final_price_try', 'sale_amount_try', 'days_to_sale',
                   'days_to_close', 'days_to_offer', 'days_to_test_drive', 'test_drive_satisfaction',
                   'lead_age_days', 'days_since_last_interaction', 'dq_flag_count', 'interaction_count',
                   'inbound_count', 'showroom_visits', 'whatsapp_count', 'test_drive_count', 'offer_count'},
    'fact_sales': {'vehicle_id', 'lead_id', 'customer_id', 'dealer_id', 'advisor_id', 'sale_date_key',
                   'delivery_date_key', 'final_price_try', 'list_price_try', 'discount_try',
                   'realized_discount_pct', 'trade_in_value_try', 'days_to_delivery', 'vin'},
    'fact_offers': {'lead_id', 'vehicle_id', 'dealer_id', 'offer_date_key', 'list_price_try', 'final_price_try',
                    'discount_try', 'discount_pct'},
    'fact_test_drives': {'lead_id', 'dealer_id', 'vehicle_id', 'advisor_id', 'scheduled_date_key', 'duration_min',
                         'satisfaction_score'},
    'dim_date': {'date_key', 'year_month_key', 'month', 'day_of_week'},
    'dim_dealer': {'dealer_id', 'opened_year'},
    'dim_vehicle': {'vehicle_id', 'price_band_order', 'list_price_try'},
    'dim_advisor': {'advisor_id', 'dealer_id'},
    'dim_customer': {'customer_id', 'birth_date', 'source_record_count'},
    'dim_lead_source': {'source'},
    'dq_results': set(),
}
SORT_BY = {('dim_date', 'year_month'): 'year_month_key', ('dim_date', 'month_name'): 'month',
           ('dim_date', 'day_name'): 'day_of_week', ('dim_vehicle', 'price_band'): 'price_band_order',
           ('fact_leads', 'response_band'): 'response_band_order'}
COL_FORMAT = {('dq_results', 'failed_pct'): '0.00', ('dq_results', 'run_ts'): 'yyyy-mm-dd hh:nn',
              ('dim_date', 'date'): 'yyyy-mm-dd'}

# ----------------------------------------------------------------------------------------------
# Measures: parse measures.dax + add the v2 measures
# ----------------------------------------------------------------------------------------------
def parse_measures(path):
    text = open(path, encoding='utf-8').read()
    blocks, cur = [], []
    for line in text.splitlines():
        if line.strip() == '':
            if cur:
                blocks.append(cur); cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        lines = [l for l in b if not l.strip().startswith('//')]
        if not lines:
            continue
        m = re.match(r'^([A-Za-z][^=]*?)\s*=\s*(.*)$', lines[0])
        if not m or lines[0].startswith(' '):
            continue
        name, first = m.group(1).strip(), m.group(2)
        body = ([first] if first.strip() else []) + lines[1:]
        # strip trailing // comments inside DAX (none are inside strings)
        body = [re.sub(r'\s*//.*$', '', l) for l in body]
        body = [l for l in body if l.strip()]
        out.append((name, body))
    return out

FORMATS = [
    (re.compile(r'(Conversion|Rate|Share|%|SLA)'), '0.0%'),
    (re.compile(r'\(h\)|Days'), '0.0'),
    (re.compile(r'Rank'), '0'),
    (re.compile(r'Flag'), None),
    (re.compile(r'\(M TRY\)|\(TRY\)|Leads|Drives|Offers|Sold|Rows|Checks'), '#,0'),
]
FORMAT_OVERRIDES = {
    'Leads YoY %': '+0.0%;-0.0%;0.0%', 'Revenue YoY %': '+0.0%;-0.0%;0.0%',
    'Conversion 3M Rolling': '0.0%', 'Realised Discount %': '0.0%', 'Avg Offer Discount %': '0.0%',
    'Financing Share': '0%', 'Leads With DQ Flags %': '0.0%', 'DQ Failed %': '0.00%',
    'Stale Pipeline %': '0%', 'Lead-to-Sale Conversion': '0.0%', 'Avg First Response (h)': '0.0',
    'Revenue (M TRY)': '#,0', 'Pipeline Value (TRY)': '#,0', 'Avg Sale Price (TRY)': '#,0', 'Dealer Conversion Rank': '0',
}

def fmt_for(name):
    if name in FORMAT_OVERRIDES:
        return FORMAT_OVERRIDES[name]
    for rx, f in FORMATS:
        if rx.search(name):
            return f
    return None

# Extra measures for the v2 report. (name, dax, format, description)
EXTRA = [
    ('Network Conversion', 'CALCULATE ( [Lead-to-Sale Conversion], ALL ( dim_dealer ), ALL ( dim_advisor ) )', '0.0%',
     'Conversion across the whole network in the current date/brand/source context - the reference line on dealer charts.'),
    ('Dealer Bar Colour', 'SWITCH ( [Dealer Performance Flag], "At risk", "#D03B3B", "Star", "#0CA30C", "#8DA2BD" )', None,
     'Hex colour for dealer bars and table cells: red = at risk, green = star, grey-blue = on track.'),
    ('Source Bar Colour', 'IF ( SELECTEDVALUE ( dim_lead_source[is_digital] ) = TRUE (), "#EB6834", "#1C5CAB" )', None,
     'Orange for digital sources (web, social, campaign), blue for everything else.'),
    ('Severity Colour', 'IF ( MAX ( dq_results[severity] ) = "error", "#EB6834", "#1C5CAB" )', None,
     'Orange for error-severity DQ checks, blue for warnings.'),
    ('Leads Digital', 'CALCULATE ( [Leads], dim_lead_source[is_digital] = TRUE () )', '#,0', 'Leads from web form, social media and campaigns.'),
    ('Leads Non-digital', 'CALCULATE ( [Leads], dim_lead_source[is_digital] = FALSE () )', '#,0', 'Leads from showroom, referral, existing customers and call center.'),
    ('Conversion Digital', 'CALCULATE ( [Lead-to-Sale Conversion], dim_lead_source[is_digital] = TRUE () )', '0.0%', 'Lead-to-sale conversion of digital leads.'),
    ('Conversion Non-digital', 'CALCULATE ( [Lead-to-Sale Conversion], dim_lead_source[is_digital] = FALSE () )', '0.0%', 'Lead-to-sale conversion of non-digital leads.'),
    ('Units Electrified', 'CALCULATE ( [Units Sold], dim_vehicle[is_electrified] = TRUE () )', '#,0', 'Units sold that are EV or PHEV.'),
    ('Units Combustion', 'CALCULATE ( [Units Sold], dim_vehicle[is_electrified] = FALSE () )', '#,0', 'Units sold that are petrol or diesel.'),
    ('Dealers At Risk', 'COUNTROWS ( FILTER ( VALUES ( dim_dealer[dealer_name] ), [Dealer Performance Flag] = "At risk" ) )', '0', 'Number of dealers converting below 75% of the network.'),
    ('Best Dealer Conversion', 'MAXX ( FILTER ( VALUES ( dim_dealer[dealer_name] ), dim_dealer[dealer_name] <> "Unknown dealer" && [Leads] > 0 ), [Lead-to-Sale Conversion] )', '0.0%', 'Highest dealer conversion in the current context.'),
    ('Best Dealer Name',
     'VAR _t = TOPN ( 1, FILTER ( VALUES ( dim_dealer[dealer_name] ), dim_dealer[dealer_name] <> "Unknown dealer" && [Leads] > 0 ), [Lead-to-Sale Conversion], DESC )\nRETURN MAXX ( _t, dim_dealer[dealer_name] )', None, 'Name of the best-converting dealer.'),
    ('Revenue (bn TRY)', 'DIVIDE ( [Revenue (TRY)], 1000000000 )', '0.0', 'Revenue in billions of TRY.'),
    ('Avg Sale Price (M TRY)', 'DIVIDE ( [Avg Sale Price (TRY)], 1000000 )', '0.00', 'Average final price per unit, millions of TRY.'),
    ('Pipeline Value (bn TRY)', 'DIVIDE ( [Pipeline Value (TRY)], 1000000000 )', '0.00', 'Open leads with an offer on the table, billions of TRY.'),
    ('Dealer Count', 'CALCULATE ( DISTINCTCOUNT ( fact_leads[dealer_id] ), dim_dealer[dealer_name] <> "Unknown dealer" )', '0', 'Dealers with at least one lead.'),
    ('Advisor Count', 'DISTINCTCOUNT ( fact_leads[advisor_id] )', '0', 'Advisors with at least one lead.'),
    ('DQ Checks Run', 'COUNTROWS ( dq_results )', '0', 'Number of checks in the last Silver run.'),
    ('DQ Error Checks Defined', 'CALCULATE ( COUNTROWS ( dq_results ), dq_results[severity] = "error" )', '0', 'Error-severity checks defined.'),
    ('DQ Last Run', 'FORMAT ( MAX ( dq_results[run_ts] ), "dd mmm yyyy hh:mm" )', None, 'Timestamp of the last Silver run.'),
    ('Leads With DQ Flags Text', 'FORMAT ( [Leads With DQ Flags], "#,0" ) & " of " & FORMAT ( [Leads], "#,0" ) & " leads"', None, 'Card subtitle.'),
    ('KPI Sub Leads', 'FORMAT ( MIN ( fact_leads[created_at] ), "mmm yyyy" ) & " – " & FORMAT ( MAX ( fact_leads[created_at] ), "mmm yyyy" )', None, 'Card subtitle: lead date range in context.'),
    ('KPI Sub Test Drives', 'FORMAT ( [Test Drives], "#,0" ) & " test drives"', None, 'Card subtitle.'),
    ('KPI Sub Offers', 'FORMAT ( [Offers Made], "#,0" ) & " offers"', None, 'Card subtitle.'),
    ('KPI Sub Conversion', 'FORMAT ( [Won Leads], "#,0" ) & " won · closed-lead basis " & FORMAT ( [Conversion Rate (Closed)], "0.0%" )', None, 'Card subtitle.'),
    ('KPI Sub Revenue', 'FORMAT ( [Units Sold], "#,0" ) & " units · illustrative list prices"', None, 'Card subtitle.'),
    ('KPI Sub Network', 'FORMAT ( [Dealer Count], "0" ) & " dealers · " & FORMAT ( [Advisor Count], "0" ) & " advisors"', None, 'Card subtitle.'),
    ('KPI Sub Response', '"SLA (24 h) met " & FORMAT ( [Response SLA Met %], "0%" )', None, 'Card subtitle.'),
    ('KPI Sub Stale', 'FORMAT ( [Stale Open Leads], "#,0" ) & " of " & FORMAT ( [Open Leads], "#,0" ) & " open leads"', None, 'Card subtitle.'),
    ('KPI Sub Pipeline', 'FORMAT ( CALCULATE ( [Open Leads], fact_leads[has_offer] = TRUE () ), "#,0" ) & " open leads with an offer"', None, 'Card subtitle.'),
    ('KPI Sub Units', 'FORMAT ( [Revenue (bn TRY)], "0.0" ) & " bn TRY revenue"', None, 'Card subtitle.'),
    ('KPI Sub Error Checks', '"of " & FORMAT ( [DQ Error Checks Defined], "0" ) & " error-severity checks"', None, 'Card subtitle.'),
    ('Model Units Rank', 'RANKX ( ALL ( dim_vehicle[model_label], dim_vehicle[brand] ), [Units Sold], , DESC, DENSE )', '0', 'Rank of the model by units sold - used as a visual filter (<= 15) instead of a Top N filter.'),
    ('Funnel Leads', '[Leads]', '#,0', 'Funnel stage 1 (alias so the funnel visual can carry stage labels).'),
    ('Funnel Offers', '[Offers Made]', '#,0', 'Funnel stage 2.'),
    ('Funnel Won', '[Won Leads]', '#,0', 'Funnel stage 3.'),
]

def all_measures():
    base = parse_measures(MEASURES_DAX)
    out = [(n, '\n'.join(b), fmt_for(n), None) for n, b in base]
    names = {n for n, *_ in out}
    for n, dax, f, d in EXTRA:
        assert n not in names, n
        out.append((n, dax, f, d))
    return out

# ----------------------------------------------------------------------------------------------
# TMDL writers
# ----------------------------------------------------------------------------------------------
def tmdl_name(n):
    return n if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', n) else "'" + n.replace("'", "''") + "'"

def table_tmdl(name, df, measures=None, date_table=False):
    lines = [f'table {tmdl_name(name)}', f'\tlineageTag: {uuid.uuid4()}']
    if date_table:
        lines.append('\tdataCategory: Time')
    lines.append('')
    for m_name, dax, fmt, desc in (measures or []):
        if desc:
            lines.append(f'\t/// {desc}')
        dax_lines = dax.split('\n')
        if len(dax_lines) == 1:
            lines.append(f'\tmeasure {tmdl_name(m_name)} = {dax_lines[0]}')
        else:
            lines.append(f'\tmeasure {tmdl_name(m_name)} =')
            for dl in dax_lines:
                lines.append('\t\t\t' + dl.strip())
        if fmt:
            lines.append(f'\t\tformatString: {fmt}')
        lines.append(f'\t\tlineageTag: {uuid.uuid4()}')
        lines.append('')
    for col in df.columns:
        dt = dtype_to_tmdl(name, col, df[col].dtype)
        lines.append(f'\tcolumn {tmdl_name(col)}')
        lines.append(f'\t\tdataType: {dt}')
        if name in HIDDEN and col in HIDDEN[name]:
            lines.append('\t\tisHidden')
        if date_table and col == 'date':
            lines.append('\t\tisKey')
        if (name, col) in COL_FORMAT:
            lines.append(f'\t\tformatString: {COL_FORMAT[(name, col)]}')
        elif dt == 'dateTime':
            lines.append('\t\tformatString: yyyy-mm-dd')
        lines.append(f'\t\tlineageTag: {uuid.uuid4()}')
        lines.append('\t\tsummarizeBy: none')
        lines.append(f'\t\tsourceColumn: {col}')
        if (name, col) in SORT_BY:
            lines.append(f'\t\tsortByColumn: {SORT_BY[(name, col)]}')
        lines.append('')
        lines.append('\t\tannotation SummarizationSetBy = User')
        lines.append('')
    fname = 'part-0.parquet' if name == 'lead_scores' else f'{name}.parquet'
    lines.append(f'\tpartition {tmdl_name(name)} = m')
    lines.append('\t\tmode: import')
    lines.append('\t\tsource =')
    lines.append('\t\t\t\tlet')
    lines.append(f'\t\t\t\t    Source = Parquet.Document(File.Contents(DataFolder & "\\{name}\\{fname}"))')
    lines.append('\t\t\t\tin')
    lines.append('\t\t\t\t    Source')
    lines.append('')
    lines.append('\tannotation PBI_ResultType = Table')
    lines.append('')
    return '\n'.join(lines)

def measures_table_tmdl(measures):
    lines = ['table _Measures', f'\tlineageTag: {uuid.uuid4()}', '']
    for m_name, dax, fmt, desc in measures:
        if desc:
            lines.append(f'\t/// {desc}')
        dax_lines = dax.split('\n')
        if len(dax_lines) == 1:
            lines.append(f'\tmeasure {tmdl_name(m_name)} = {dax_lines[0]}')
        else:
            lines.append(f'\tmeasure {tmdl_name(m_name)} =')
            for dl in dax_lines:
                lines.append('\t\t\t' + dl.strip())
        if fmt:
            lines.append(f'\t\tformatString: {fmt}')
        lines.append(f'\t\tlineageTag: {uuid.uuid4()}')
        lines.append('')
    lines += ['\tcolumn x', '\t\tdataType: int64', '\t\tisHidden', f'\t\tlineageTag: {uuid.uuid4()}',
              '\t\tsummarizeBy: none', '\t\tsourceColumn: x', '', '\t\tannotation SummarizationSetBy = User', '',
              '\tpartition _Measures = m', '\t\tmode: import', '\t\tsource =', '\t\t\t\tlet',
              '\t\t\t\t    Source = #table(type table [x = Int64.Type], {{1}})', '\t\t\t\tin', '\t\t\t\t    Source', '',
              '\tannotation PBI_ResultType = Table', '']
    return '\n'.join(lines)

RELATIONSHIPS = [  # (from table, from col, to table, to col, active)
    ('fact_leads', 'created_date_key', 'dim_date', 'date_key', True),
    ('fact_leads', 'closed_date_key', 'dim_date', 'date_key', False),
    ('fact_leads', 'dealer_id', 'dim_dealer', 'dealer_id', True),
    ('fact_leads', 'advisor_id', 'dim_advisor', 'advisor_id', True),
    ('fact_leads', 'vehicle_id', 'dim_vehicle', 'vehicle_id', True),
    ('fact_leads', 'customer_id', 'dim_customer', 'customer_id', True),
    ('fact_leads', 'source', 'dim_lead_source', 'source', True),
    ('fact_sales', 'sale_date_key', 'dim_date', 'date_key', True),
    ('fact_sales', 'dealer_id', 'dim_dealer', 'dealer_id', True),
    ('fact_sales', 'advisor_id', 'dim_advisor', 'advisor_id', True),
    ('fact_sales', 'vehicle_id', 'dim_vehicle', 'vehicle_id', True),
    ('fact_sales', 'customer_id', 'dim_customer', 'customer_id', True),
    ('fact_offers', 'offer_date_key', 'dim_date', 'date_key', True),
    ('fact_offers', 'dealer_id', 'dim_dealer', 'dealer_id', True),
    ('fact_offers', 'vehicle_id', 'dim_vehicle', 'vehicle_id', True),
    ('fact_test_drives', 'scheduled_date_key', 'dim_date', 'date_key', True),
    ('fact_test_drives', 'dealer_id', 'dim_dealer', 'dealer_id', True),
    ('fact_test_drives', 'vehicle_id', 'dim_vehicle', 'vehicle_id', True),
]

def relationships_tmdl():
    out = []
    for ft, fc, tt, tc, active in RELATIONSHIPS:
        out.append(f'relationship {uuid.uuid4()}')
        if not active:
            out.append('\tisActive: false')
        out.append(f'\tfromColumn: {ft}.{fc}')
        out.append(f'\ttoColumn: {tt}.{tc}')
        out.append('')
    return '\n'.join(out)

def diagram_layout(tables):
    """Star layout: facts in the middle row, dimensions above and below."""
    lineage = {}  # filled by caller
    return None

def build(out_dir, data_folder_default, model_name='LeadToSale'):
    sm = os.path.join(out_dir, f'{model_name}.SemanticModel')
    os.makedirs(os.path.join(sm, 'definition', 'tables'), exist_ok=True)
    os.makedirs(os.path.join(sm, 'definition', 'cultures'), exist_ok=True)
    measures = all_measures()
    table_lineage = {}
    for t in TABLES:
        df = pd.read_parquet(glob.glob(GOLD + t + '/*.parquet')[0])
        txt = table_tmdl(t, df, date_table=(t == 'dim_date'))
        table_lineage[t] = re.search(r'lineageTag: (\S+)', txt).group(1)
        open(os.path.join(sm, 'definition', 'tables', f'{t}.tmdl'), 'w', encoding='utf-8').write(txt)
    txt = measures_table_tmdl(measures)
    table_lineage['_Measures'] = re.search(r'lineageTag: (\S+)', txt).group(1)
    open(os.path.join(sm, 'definition', 'tables', '_Measures.tmdl'), 'w', encoding='utf-8').write(txt)
    open(os.path.join(sm, 'definition', 'relationships.tmdl'), 'w', encoding='utf-8').write(relationships_tmdl())
    open(os.path.join(sm, 'definition', 'database.tmdl'), 'w', encoding='utf-8').write(
        'database\n\tcompatibilityLevel: 1567\n')
    refs = '\n'.join(f'ref table {tmdl_name(t)}' for t in TABLES + ['_Measures'])
    open(os.path.join(sm, 'definition', 'model.tmdl'), 'w', encoding='utf-8').write(
        'model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n'
        '\tsourceQueryCulture: en-US\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n'
        f'annotation PBI_QueryOrder = {json.dumps(["DataFolder"] + TABLES + ["_Measures"])}\n\n'
        'annotation __PBI_TimeIntelligenceEnabled = 0\n\n' + refs + '\n\nref cultureInfo en-US\n')
    df_escaped = data_folder_default  # M strings take backslashes literally
    open(os.path.join(sm, 'definition', 'expressions.tmdl'), 'w', encoding='utf-8').write(
        f'/// Folder that holds the gold parquet tables (one sub-folder per table). Change it after opening the project: Transform data > Edit parameters.\n'
        f'expression DataFolder = "{df_escaped}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f'\tlineageTag: {uuid.uuid4()}\n\n\tannotation PBI_ResultType = Text\n')
    open(os.path.join(sm, 'definition', 'cultures', 'en-US.tmdl'), 'w', encoding='utf-8').write(
        'cultureInfo en-US\n\n\tlinguisticMetadata = {"Version":"1.0.0","Language":"en-US"}\n\t\tcontentType: json\n')
    json.dump({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
               "version": "4.2", "settings": {}}, open(os.path.join(sm, 'definition.pbism'), 'w'), indent=2)
    json.dump({"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
               "metadata": {"type": "SemanticModel", "displayName": model_name},
               "config": {"version": "2.0", "logicalId": str(uuid.uuid4())}},
              open(os.path.join(sm, '.platform'), 'w'), indent=2)
    # star-shaped diagram layout: dimensions on top, facts in the middle, dq/measures on the side
    top = ['dim_date', 'dim_dealer', 'dim_vehicle', 'dim_lead_source']
    mid = ['fact_leads', 'fact_sales', 'fact_offers', 'fact_test_drives']
    bot = ['dim_advisor', 'dim_customer', 'dq_results', '_Measures']
    nodes = []
    def place(names, y):
        for i, n in enumerate(names):
            nodes.append({"location": {"x": 40 + i * 260, "y": y}, "nodeIndex": n, "nodeLineageTag": table_lineage[n],
                          "size": {"height": 200, "width": 220}, "zIndex": 0})
    place(top, 20); place(mid, 300); place(bot, 580)
    json.dump({"version": "1.1.0", "diagrams": [{"ordinal": 0, "scrollPosition": {"x": 0, "y": 0}, "nodes": nodes,
               "name": "All tables", "zoomValue": 100, "pinKeyFieldsToTop": False, "showExtraHeaderInfo": False,
               "hideKeyFieldsWhenCollapsed": False, "tablesLocked": False}],
               "selectedDiagram": "All tables", "defaultDiagram": "All tables"},
              open(os.path.join(sm, 'diagramLayout.json'), 'w'), indent=2)
    return measures

if __name__ == '__main__':
    import sys
    ms = build(sys.argv[1], sys.argv[2])
    print(len(ms), 'measures')
