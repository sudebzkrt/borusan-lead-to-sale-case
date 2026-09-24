"""Builds the PBIR report (Lead-to-Sale v2) - four pages, theme, slicers, finding-style titles."""
import json, os, shutil, uuid

VC_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json'
PAGE_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json'
REPORT_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.0.0/schema.json'
PAGES_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json'
VERSION_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json'
PBIR_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json'
PLATFORM_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json'

# Power BI's stock base theme, copied into build/ so the script has no external dependency.
BASE_THEME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CY24SU10.json')

# ---- design tokens -----------------------------------------------------------------------------
C = dict(blue='#1C5CAB', orange='#EB6834', aqua='#1BAF7A', yellow='#EDA100', violet='#4A3AA7', mute='#8DA2BD',
         crit='#D03B3B', good='#0CA30C', ink='#1B1F27', ink2='#5B6472', ink3='#8A93A1', grid='#EEF0F3',
         page='#F3F4F6', card='#FFFFFF', f1='#86B6EF', f2='#3987E5', f3='#1C5CAB', lightgrey='#B9C2CE')
FONT = "Segoe UI"
FONT_SEMI = "Segoe UI Semibold"

# ---- expression helpers ---------------------------------------------------------------------
def lit(v):
    if isinstance(v, bool):
        return {"expr": {"Literal": {"Value": "true" if v else "false"}}}
    if isinstance(v, int):
        return {"expr": {"Literal": {"Value": f"{v}L"}}}
    if isinstance(v, float):
        return {"expr": {"Literal": {"Value": f"{v}D"}}}
    return {"expr": {"Literal": {"Value": "'" + str(v).replace("'", "''") + "'"}}}

def D(v):  # double literal
    return {"expr": {"Literal": {"Value": f"{v}D"}}}

def color(hexv):
    return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{hexv}'"}}}}}

def measure_ref(name, table='_Measures'):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}

def column_ref(table, name):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}

def color_by_measure(name):
    return {"solid": {"color": {"expr": measure_ref(name)}}}

def M(name, display=None):
    p = {"field": measure_ref(name), "queryRef": f"_Measures.{name}", "nativeQueryRef": name}
    if display:
        p["displayName"] = display
    return p

def Col(table, name, display=None, active=True):
    p = {"field": column_ref(table, name), "queryRef": f"{table}.{name}", "nativeQueryRef": name}
    if active:
        p["active"] = True
    if display:
        p["displayName"] = display
    return p

def sort_by(field, direction='Descending'):
    return {"sort": [{"field": field, "direction": direction}], "isDefaultSort": True}

def title_obj(text, show=True, size=12.0):
    return [{"properties": {"show": lit(show), "text": lit(text), "fontSize": D(size), "fontFamily": lit(FONT_SEMI),
                            "fontColor": color(C['ink']), "alignment": lit('left'), "titleWrap": lit(True)}}]

def subtitle_obj(text=None, measure=None, show=True, size=9.5):
    props = {"show": lit(show), "fontSize": D(size), "fontFamily": lit(FONT), "fontColor": color(C['ink3']),
             "alignment": lit('left'), "titleWrap": lit(True)}
    if measure:
        props["text"] = {"expr": measure_ref(measure)}
    elif text is not None:
        props["text"] = lit(text)
    return [{"properties": props}]

def container(title=None, subtitle=None, subtitle_measure=None, bg=True, title_size=12.0):
    vco = {}
    vco["title"] = title_obj(title) if title else [{"properties": {"show": lit(False)}}]
    if subtitle or subtitle_measure:
        vco["subTitle"] = subtitle_obj(subtitle, subtitle_measure)
    else:
        vco["subTitle"] = [{"properties": {"show": lit(False)}}]
    vco["background"] = [{"properties": {"show": lit(bg), "color": color(C['card']), "transparency": D(0)}}]
    vco["border"] = [{"properties": {"show": lit(bg), "color": color(C['card']), "radius": D(8), "width": D(1)}}]
    vco["dropShadow"] = [{"properties": {"show": lit(False)}}]
    vco["visualHeader"] = [{"properties": {"show": lit(False)}}]
    return vco

def wildcard_selector():
    return {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}

# ---- filters ------------------------------------------------------------------------------------
def filter_not_in(table, col, values):
    alias = table[0]
    return {"name": uuid.uuid4().hex[:20], "field": column_ref(table, col), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": alias, "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"Not": {"Expression": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": col}}],
                           "Values": [[{"Literal": {"Value": "'" + v + "'"}}] for v in values]}}}}}]},
            "howCreated": "User", "objects": {"general": [{"properties": {"isInvertedSelectionMode": lit(True)}}]}}

def filter_topn(table, col, n, by_measure):
    alias = table[0]
    return {"name": uuid.uuid4().hex[:20], "field": column_ref(table, col), "type": "TopN",
            "filter": {"Version": 2, "From": [{"Name": alias, "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"VisualTopN": {
                           "Expression": {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": col}},
                           "Count": {"Literal": {"Value": f"{n}L"}}, "OrderBy": measure_ref(by_measure),
                           "IsAscending": False}}}]}, "howCreated": "User"}

def filter_measure_gt(measure, value, kind=1):
    return {"name": uuid.uuid4().hex[:20], "field": measure_ref(measure), "type": "Advanced",
            "filter": {"Version": 2, "From": [{"Name": "m", "Entity": "_Measures", "Type": 0}],
                       "Where": [{"Condition": {"Comparison": {"ComparisonKind": kind,
                           "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measure}},
                           "Right": {"Literal": {"Value": f"{value}D"}}}}}]}, "howCreated": "User"}

# ---- visual factory ---------------------------------------------------------------------------
class Page:
    def __init__(self, name, display, header_title, header_q):
        self.name, self.display = name, display
        self.visuals = []
        self.interactions = []
        self.z = 0
        self.header(header_title, header_q)

    def add(self, name, x, y, w, h, visual, filters=None, hidden=False):
        self.z += 1000
        v = {"$schema": VC_SCHEMA, "name": name, "position": {"x": x, "y": y, "z": self.z, "width": w, "height": h,
             "tabOrder": self.z}, "visual": visual}
        if filters:
            v["filterConfig"] = {"filters": filters}
        self.visuals.append(v)
        return v

    # -- text --------------------------------------------------------------------------------
    def header(self, title, question):
        paras = [{"textRuns": [{"value": title, "textStyle": {"fontFamily": FONT_SEMI, "fontSize": "13pt", "color": C['ink']}}]},
                 {"textRuns": [{"value": question, "textStyle": {"fontFamily": FONT, "fontSize": "9.5pt", "color": C['ink2']}}]}]
        vis = {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paras}}]},
               "visualContainerObjects": container(bg=False), "drillFilterOtherVisuals": True}
        self.add('header', 20, 14, 724, 66, vis)

    def note(self, name, x, y, w, h, title, paragraphs):
        paras = []
        for p in paragraphs:
            paras.append({"textRuns": [{"value": p, "textStyle": {"fontFamily": FONT, "fontSize": "9.5pt", "color": C['ink2']}}]})
            paras.append({"textRuns": [{"value": "", "textStyle": {"fontSize": "4pt"}}]})
        vis = {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paras[:-1]}}]},
               "visualContainerObjects": container(title=title), "drillFilterOtherVisuals": True}
        return self.add(name, x, y, w, h, vis)

    # -- slicers --------------------------------------------------------------------------------
    def slicer(self, name, x, y, w, table, col, label, mode='Dropdown', sync=None):
        objs = {"data": [{"properties": {"mode": lit(mode)}}],
                "header": [{"properties": {"show": lit(True), "text": lit(label), "fontColor": color(C['ink2']),
                                           "fontSize": D(9), "fontFamily": lit(FONT)}}],
                "items": [{"properties": {"fontColor": color(C['ink']), "fontSize": D(9.5), "fontFamily": lit(FONT)}}]}
        if mode == 'Dropdown':
            objs["selection"] = [{"properties": {"selectAllCheckboxEnabled": lit(True), "singleSelect": lit(False)}}]
        vis = {"visualType": "slicer", "query": {"queryState": {"Values": {"projections": [Col(table, col)]}}},
               "objects": objs, "visualContainerObjects": container(bg=True), "drillFilterOtherVisuals": True}
        if sync:
            vis["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
        return self.add(name, x, y, w, 42 if mode == 'Dropdown' else 48, vis)

    def slicer_row(self, y=20):
        # four synced slicers, top right
        self.slicer('sl_date', 756, y, 180, 'dim_date', 'date', 'Lead date', mode='Between', sync='date')
        self.slicer('sl_brand', 944, y, 92, 'dim_vehicle', 'brand', 'Brand', sync='brand')
        self.slicer('sl_region', 1044, y, 100, 'dim_dealer', 'region', 'Region', sync='region')
        self.slicer('sl_source', 1152, y, 108, 'dim_lead_source', 'source_group', 'Source group', sync='source')

    # -- cards ----------------------------------------------------------------------------------
    def card(self, name, x, y, w, label, measure, sub_measure=None, sub_text=None, accent=False, h=84):
        objs = {"labels": [{"properties": {"fontSize": D(20), "fontFamily": lit(FONT_SEMI), "labelDisplayUnits": D(1),
                                           "color": color(C['orange'] if accent else C['ink'])}}],
                "categoryLabels": [{"properties": {"show": lit(False)}}]}
        vco = container(title=label, subtitle=sub_text, subtitle_measure=sub_measure)
        vco["padding"] = [{"properties": {"top": D(6), "bottom": D(2), "left": D(12), "right": D(12)}}]
        vco["title"][0]["properties"]["fontFamily"] = lit(FONT)
        vco["title"][0]["properties"]["fontColor"] = color(C['ink2'])
        vco["title"][0]["properties"]["fontSize"] = D(10)
        vis = {"visualType": "card", "query": {"queryState": {"Values": {"projections": [M(measure)]}}},
               "objects": objs, "visualContainerObjects": vco, "drillFilterOtherVisuals": True}
        return self.add(name, x, y, w, h, vis)

    # -- charts ---------------------------------------------------------------------------------
    def _axis_objs(self, cat_axis=True, val_axis=True, val_fmt=None, val_max=None):
        objs = {"categoryAxis": [{"properties": {"show": lit(cat_axis), "showAxisTitle": lit(False),
                                                 "labelColor": color(C['ink2']), "fontSize": D(9), "fontFamily": lit(FONT),
                                                 "gridlineShow": lit(False), "concatenateLabels": lit(False),
                                                 "maxMarginFactor": lit(40)}}],
                "valueAxis": [{"properties": {"show": lit(val_axis), "showAxisTitle": lit(False),
                                              "labelColor": color(C['ink3']), "fontSize": D(9), "fontFamily": lit(FONT),
                                              "gridlineShow": lit(True), "gridlineColor": color(C['grid']),
                                              "gridlineStyle": lit('solid'), "gridlineThickness": D(1), "labelDisplayUnits": D(1)}}]}
        if val_max is not None:
            objs["valueAxis"][0]["properties"]["end"] = D(val_max)
            objs["valueAxis"][0]["properties"]["start"] = D(0)
        return objs

    def bar(self, name, x, y, w, h, category, measures, title, subtitle=None, sub_measure=None, horizontal=True,
            colors=None, color_measure=None, labels=True, legend=False, sort_field=None, sort_dir='Descending',
            stacked=False, series=None, filters=None, ref_measure=None, ref_label=None, val_axis=False, val_max=None,
            clustered=None, label_fmt=None):
        if horizontal:
            vt = 'barChart' if (stacked or len(measures) == 1) else 'clusteredBarChart'
        else:
            vt = 'columnChart' if (stacked or len(measures) == 1) else 'clusteredColumnChart'
        if clustered:
            vt = 'clusteredBarChart' if horizontal else 'clusteredColumnChart'
        qs = {"Category": {"projections": [category]}, "Y": {"projections": measures}}
        if series:
            qs["Series"] = {"projections": [series]}
        query = {"queryState": qs}
        if sort_field is not None:
            query["sortDefinition"] = sort_by(sort_field, sort_dir)
        objs = self._axis_objs(val_axis=val_axis, val_max=val_max)
        objs["categoryAxis"][0]["properties"]["preferredCategoryWidth"] = lit(10)
        objs["categoryAxis"][0]["properties"]["innerPadding"] = lit(30)
        objs["legend"] = [{"properties": {"show": lit(legend), "position": lit('Bottom'), "showTitle": lit(False),
                                          "fontSize": D(9), "fontFamily": lit(FONT), "labelColor": color(C['ink2'])}}]
        lab = {"show": lit(labels), "fontSize": D(9), "fontFamily": lit(FONT), "color": color(C['ink2']),
               "labelPosition": lit('OutsideEnd'), "labelOverflow": lit(True), "labelDisplayUnits": D(1)}
        if label_fmt == 'pct1':
            lab["labelPrecision"] = {"expr": {"Literal": {"Value": "1L"}}}
        if label_fmt == 'pct0':
            lab["labelPrecision"] = {"expr": {"Literal": {"Value": "0L"}}}
        if stacked and series is not None:
            lab["color"] = color(C['card']); lab["labelPosition"] = lit('InsideCenter')
        objs["labels"] = [{"properties": lab}]
        dp = []
        if color_measure:
            dp.append({"properties": {"fill": color_by_measure(color_measure)}, "selector": wildcard_selector()})
        elif colors:
            for m, c in colors.items():
                dp.append({"properties": {"fill": color(c)}, "selector": {"metadata": m}})
        else:
            dp.append({"properties": {"fill": color(C['blue'])}})
        objs["dataPoint"] = dp
        if ref_measure:
            objs["y1AxisReferenceLine"] = [{"properties": {"show": lit(True), "value": {"expr": measure_ref(ref_measure)},
                                                           "lineColor": color(C['ink']), "transparency": D(30),
                                                           "style": lit('dashed'), "position": lit('front'),
                                                           "dataLabelShow": lit(True),
                                                           "displayName": lit(ref_label or 'network')}, "selector": {"id": "0"}}]
        vis = {"visualType": vt, "query": query, "objects": objs,
               "visualContainerObjects": container(title=title, subtitle=subtitle, subtitle_measure=sub_measure),
               "drillFilterOtherVisuals": True}
        return self.add(name, x, y, w, h, vis, filters=filters)

    def line(self, name, x, y, w, h, category, measures, title, subtitle=None, colors=None, sort_field=None,
             val_max=None, filters=None):
        query = {"queryState": {"Category": {"projections": [category]}, "Y": {"projections": measures}}}
        if sort_field is not None:
            query["sortDefinition"] = sort_by(sort_field, 'Ascending')
        objs = self._axis_objs(val_axis=True, val_max=val_max)
        objs["categoryAxis"][0]["properties"]["preferredCategoryWidth"] = lit(8)
        objs["legend"] = [{"properties": {"show": lit(len(measures) > 1), "position": lit('Bottom'), "showTitle": lit(False),
                                          "fontSize": D(9), "fontFamily": lit(FONT), "labelColor": color(C['ink2'])}}]
        objs["lineStyles"] = [{"properties": {"strokeWidth": D(2), "lineChartType": lit('straight'), "showMarker": lit(False)}}]
        objs["labels"] = [{"properties": {"show": lit(False)}}]
        dp = []
        for i, m in enumerate(measures):
            c = (colors or {}).get(m["nativeQueryRef"], [C['blue'], C['orange'], C['aqua']][i % 3])
            dp.append({"properties": {"fill": color(c)}, "selector": {"metadata": m["queryRef"]}})
        objs["dataPoint"] = dp
        vis = {"visualType": "lineChart", "query": query, "objects": objs,
               "visualContainerObjects": container(title=title, subtitle=subtitle), "drillFilterOtherVisuals": True}
        return self.add(name, x, y, w, h, vis, filters=filters)

    def funnel(self, name, x, y, w, h, measures, title, subtitle=None):
        query = {"queryState": {"Y": {"projections": measures}}, "sortDefinition": {"isDefaultSort": True}}
        objs = {"dataPoint": [{"properties": {"fill": color(c)}, "selector": {"metadata": m["queryRef"]}}
                              for m, c in zip(measures, [C['f1'], C['f2'], C['f3']])],
                "labels": [{"properties": {"show": lit(True), "fontSize": D(10), "fontFamily": lit(FONT_SEMI), "labelDisplayUnits": D(1),
                                           "color": color(C['card']), "labelPosition": lit('InsideCenter')}}],
                "percentBarLabel": [{"properties": {"show": lit(True), "color": color(C['ink2']), "fontSize": D(9)}}],
                "categoryAxis": [{"properties": {"show": lit(True), "labelColor": color(C['ink']), "fontSize": D(9.5),
                                                 "fontFamily": lit(FONT)}}]}
        vis = {"visualType": "funnel", "query": query, "objects": objs,
               "visualContainerObjects": container(title=title, subtitle=subtitle), "drillFilterOtherVisuals": True}
        return self.add(name, x, y, w, h, vis)

    def table(self, name, x, y, w, h, projections, title, subtitle=None, sort_field=None, sort_dir='Descending',
              filters=None, color_cols=None, widths=None):
        query = {"queryState": {"Values": {"projections": projections}}}
        if sort_field is not None:
            query["sortDefinition"] = sort_by(sort_field, sort_dir)
        values = [{"properties": {"fontColor": color(C['ink']), "fontSize": D(9.5), "fontFamily": lit(FONT),
                                  "backColor": color(C['card']), "backColorSecondary": color(C['card'])}}]
        for qref, measure in (color_cols or {}).items():
            values.append({"properties": {"fontColor": color_by_measure(measure)},
                           "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": qref}})
        objs = {"grid": [{"properties": {"gridVertical": lit(False), "gridHorizontal": lit(True),
                                         "gridHorizontalColor": color(C['grid']), "gridHorizontalWeight": D(1),
                                         "rowPadding": D(4), "outlineColor": color(C['grid']), "outlineWeight": D(1)}}],
                "columnHeaders": [{"properties": {"fontColor": color(C['ink2']), "fontSize": D(9.5), "fontFamily": lit(FONT_SEMI),
                                                  "backColor": color(C['card']), "outline": lit('BottomOnly'), "wordWrap": lit(True)}}],
                "values": values,
                "total": [{"properties": {"totals": lit(False)}}]}
        if widths:
            objs["columnWidth"] = [{"properties": {"value": D(wd)}, "selector": {"metadata": q}} for q, wd in widths.items()]
        vis = {"visualType": "tableEx", "query": query, "objects": objs,
               "visualContainerObjects": container(title=title, subtitle=subtitle), "drillFilterOtherVisuals": True}
        return self.add(name, x, y, w, h, vis, filters=filters)

    def matrix(self, name, x, y, w, h, rows, cols, values, title, subtitle=None):
        query = {"queryState": {"Rows": {"projections": rows}, "Columns": {"projections": cols}, "Values": {"projections": values}}}
        objs = {"grid": [{"properties": {"gridVertical": lit(False), "gridHorizontal": lit(True), "gridHorizontalColor": color(C['grid']),
                                         "rowPadding": D(4), "outlineColor": color(C['grid'])}}],
                "columnHeaders": [{"properties": {"fontColor": color(C['ink2']), "fontSize": D(9.5), "fontFamily": lit(FONT_SEMI), "backColor": color(C['card'])}}],
                "rowHeaders": [{"properties": {"fontColor": color(C['ink']), "fontSize": D(9.5), "fontFamily": lit(FONT), "backColor": color(C['card'])}}],
                "values": [{"properties": {"fontColor": color(C['ink']), "fontSize": D(9.5), "fontFamily": lit(FONT), "backColor": color(C['card']), "backColorSecondary": color(C['card'])}},
                           {"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {"Input": measure_ref('DQ Failed Rows'), "FillRule": {"linearGradient2": {
                               "min": {"color": {"Literal": {"Value": "'#FFFFFF'"}}}, "max": {"color": {"Literal": {"Value": "'#86B6EF'"}}},
                               "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}}}}}}}}}},
                            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": "_Measures.DQ Failed Rows"}}],
                "subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]}
        vis = {"visualType": "pivotTable", "query": query, "objects": objs,
               "visualContainerObjects": container(title=title, subtitle=subtitle), "drillFilterOtherVisuals": True}
        return self.add(name, x, y, w, h, vis)

    def page_json(self):
        return {"$schema": PAGE_SCHEMA, "name": self.name, "displayName": self.display, "displayOption": "FitToPage",
                "height": 720, "width": 1280,
                "objects": {"background": [{"properties": {"color": color(C['page']), "transparency": D(0)}}]},
                "visualInteractions": self.interactions}


# ---- theme --------------------------------------------------------------------------------------
def theme():
    return {
        "name": "BorusanLeadTheme",
        "dataColors": [C['blue'], C['orange'], C['aqua'], C['yellow'], C['violet'], C['mute'], C['crit'], C['good']],
        "background": C['card'], "foreground": C['ink'], "tableAccent": C['blue'],
        "good": C['good'], "neutral": C['mute'], "bad": C['crit'],
        "maximum": C['f3'], "center": C['f2'], "minimum": C['f1'], "null": C['lightgrey'],
        "textClasses": {
            "title": {"fontFace": FONT_SEMI, "fontSize": 12, "color": C['ink']},
            "label": {"fontFace": FONT, "fontSize": 9, "color": C['ink2']},
            "callout": {"fontFace": FONT_SEMI, "fontSize": 22, "color": C['ink']},
            "header": {"fontFace": FONT_SEMI, "fontSize": 11, "color": C['ink']},
        },
        "visualStyles": {
            "*": {"*": {
                "title": [{"show": True, "alignment": "left", "fontFamily": FONT_SEMI, "fontSize": 12, "fontColor": {"solid": {"color": C['ink']}}, "titleWrap": True}],
                "subTitle": [{"alignment": "left", "fontFamily": FONT, "fontSize": 9.5, "fontColor": {"solid": {"color": C['ink3']}}}],
                "background": [{"show": True, "color": {"solid": {"color": C['card']}}, "transparency": 0}],
                "border": [{"show": True, "color": {"solid": {"color": C['card']}}, "radius": 8, "width": 1}],
                "dropShadow": [{"show": False}],
                "padding": [{"top": 10, "bottom": 10, "left": 12, "right": 12}],
                "visualHeader": [{"show": False}],
                "categoryAxis": [{"showAxisTitle": False, "gridlineShow": False, "labelColor": {"solid": {"color": C['ink2']}}, "fontFamily": FONT, "fontSize": 9}],
                "valueAxis": [{"showAxisTitle": False, "gridlineShow": True, "gridlineColor": {"solid": {"color": C['grid']}}, "gridlineStyle": "solid", "gridlineThickness": 1, "labelColor": {"solid": {"color": C['ink3']}}, "fontFamily": FONT, "fontSize": 9}],
                "legend": [{"position": "Bottom", "showTitle": False, "fontFamily": FONT, "fontSize": 9, "labelColor": {"solid": {"color": C['ink2']}}}],
                "labels": [{"fontFamily": FONT, "fontSize": 9, "color": {"solid": {"color": C['ink2']}}}],
                "dataPoint": [{"borderShow": False}],
                "lineStyles": [{"strokeWidth": 2, "lineChartType": "straight", "showMarker": False}],
                "outspacePane": [{"backgroundColor": {"solid": {"color": C['card']}}, "transparency": 0, "border": False}],
            }},
            "page": {"*": {"background": [{"color": {"solid": {"color": C['page']}}, "transparency": 0}],
                           "outspace": [{"color": {"solid": {"color": C['page']}}, "transparency": 0}]}},
            "slicer": {"*": {"background": [{"show": True, "color": {"solid": {"color": C['card']}}, "transparency": 0}],
                             "border": [{"show": True, "color": {"solid": {"color": '#E5E7EB'}}, "radius": 6, "width": 1}],
                             "header": [{"show": True, "fontColor": {"solid": {"color": C['ink2']}}, "fontSize": 9, "fontFamily": FONT}],
                             "items": [{"fontColor": {"solid": {"color": C['ink']}}, "fontSize": 9.5, "fontFamily": FONT}]}},
            "textbox": {"*": {"background": [{"show": False}], "border": [{"show": False}]}},
        },
    }


# ---- pages --------------------------------------------------------------------------------------
def build_pages():
    pages = []

    # ------------------------------------------------------------------ 1 Funnel Overview
    p = Page('funnel_overview', 'Funnel Overview',
             '18% of leads become sales — the leak is in the digital channels',
             'Funnel Overview · How is the lead-to-sale funnel performing, and where does it leak?')
    p.slicer_row()
    kx = lambda i: 20 + i * 250
    p.card('kpi_leads', kx(0), 88, 240, 'Leads', 'Leads', sub_measure='KPI Sub Leads')
    p.card('kpi_td', kx(1), 88, 240, 'Test drive rate', 'Test Drive Rate', sub_measure='KPI Sub Test Drives')
    p.card('kpi_offer', kx(2), 88, 240, 'Offer rate', 'Offer Rate', sub_measure='KPI Sub Offers')
    p.card('kpi_conv', kx(3), 88, 240, 'Lead-to-sale conversion', 'Lead-to-Sale Conversion', sub_measure='KPI Sub Conversion', accent=True)
    p.card('kpi_rev', kx(4), 88, 240, 'Revenue (bn TRY)', 'Revenue (bn TRY)', sub_measure='KPI Sub Revenue')
    p.funnel('funnel', 20, 180, 300, 246, [M('Funnel Leads', 'Leads'), M('Funnel Offers', 'Offers'), M('Funnel Won', 'Won')],
             'Half of leads get an offer; 38% of offers close', 'Leads → Offers → Won · hover for % of previous stage')
    p.bar('src_conv', 330, 180, 512, 246, Col('dim_lead_source', 'source_label', 'Source'), [M('Lead-to-Sale Conversion', 'Conversion')],
          'Referral and showroom convert 6× better than digital sources',
          'Lead-to-sale conversion by source · orange = digital', color_measure='Source Bar Colour',
          sort_field=measure_ref('Lead-to-Sale Conversion'), ref_measure='Network Conversion', ref_label='network', label_fmt='pct1')
    p.bar('quarterly', 852, 180, 408, 246, Col('dim_date', 'year_quarter', 'Quarter'),
          [M('Leads Non-digital', 'Non-digital'), M('Leads Digital', 'Digital')],
          'Digital brings 55% of leads at 7% conversion — the queue the assistant ranks',
          'Leads per quarter · orange = web form, social media, campaign', horizontal=False, stacked=True, labels=False, legend=True,
          colors={'_Measures.Leads Non-digital': C['blue'], '_Measures.Leads Digital': C['orange']},
          sort_field=column_ref('dim_date', 'year_quarter'), sort_dir='Ascending', val_axis=True)
    p.line('trend', 20, 436, 822, 264, Col('dim_date', 'year_month', 'Month'), [M('Conversion Rate (Closed)', 'Closed-lead conversion')],
           'Closed-lead conversion holds near 20% while volume tripled — December peaks, January–February dips',
           'Conversion among leads that already have an outcome, by lead month (open leads excluded, so the latest months are not understated)',
           sort_field=column_ref('dim_date', 'year_month'), val_max=0.32)
    p.card('kpi_open', 852, 436, 130, 'Open leads', 'Open Leads', h=74)
    p.card('kpi_stale', 990, 436, 130, 'Stale', 'Stale Open Leads', accent=True, h=74)
    p.card('kpi_stale_pct', 1128, 436, 132, 'Stale share', 'Stale Pipeline %', h=74)
    p.note('stale_note', 852, 518, 408, 182, 'A third of the open pipeline is stale',
           ['Stale = open for more than 30 days with no contact in the last 14 days.',
            'Advisors work 40–80 open leads in CRM order. The Lead Intelligence Assistant (part 2) re-orders that queue by conversion probability and drafts the next action — the high-volume, low-conversion digital channels are where that pays off.'])
    pages.append(p)

    # ------------------------------------------------------------------ 2 Dealer & Advisor
    p = Page('dealer_performance', 'Dealer & Advisor Performance',
             'Two authorized dealers convert below 75% of the network — on every channel',
             'Dealer & Advisor Performance · Which dealers are behind, and is it speed or closing?')
    p.slicer_row()
    p.card('kpi_net', kx(0), 88, 240, 'Network conversion', 'Network Conversion', sub_measure='KPI Sub Network')
    p.card('kpi_resp', kx(1), 88, 240, 'Avg first response (hours)', 'Avg First Response (h)', sub_measure='KPI Sub Response')
    p.card('kpi_risk', kx(2), 88, 240, 'Dealers at risk', 'Dealers At Risk', sub_text='< 75% of network conversion', accent=True)
    p.card('kpi_best', kx(3), 88, 240, 'Best dealer', 'Best Dealer Conversion', sub_measure='Best Dealer Name')
    p.card('kpi_sla', kx(4), 88, 240, 'Response SLA met (24 h)', 'Response SLA Met %', sub_text='share of leads contacted within a day')
    unk = filter_not_in('dim_dealer', 'dealer_name', ['Unknown dealer'])
    p.bar('dealer_bars', 20, 180, 500, 520, Col('dim_dealer', 'dealer_name', 'Dealer'), [M('Lead-to-Sale Conversion', 'Conversion')],
          'Conversion by dealer vs network average', 'Red = at risk (< 75% of network) · green = star (> 125%) · click a bar to filter the page',
          color_measure='Dealer Bar Colour', sort_field=measure_ref('Lead-to-Sale Conversion'), ref_measure='Network Conversion',
          ref_label='network', filters=[unk], label_fmt='pct1')
    p.bar('response', 530, 180, 730, 246, Col('fact_leads', 'response_band', 'First response'),
          [M('Conversion Non-digital', 'Non-digital (showroom, referral, call center)'), M('Conversion Digital', 'Digital (web, social, campaign)')],
          'Answering within an hour lifts conversion in both digital and non-digital leads',
          'Lead-to-sale conversion by first-response band', horizontal=False, clustered=True, legend=True, labels=True,
          colors={'_Measures.Conversion Non-digital': C['blue'], '_Measures.Conversion Digital': C['orange']},
          sort_field=column_ref('fact_leads', 'response_band'), sort_dir='Ascending', val_axis=True,
          filters=[filter_not_in('fact_leads', 'response_band', ['n/a'])], label_fmt='pct1')
    p.table('scorecard', 530, 436, 730, 264,
            [Col('dim_dealer', 'dealer_name', 'Dealer', active=False), M('Leads'), M('Lead-to-Sale Conversion', 'Conversion'),
             M('Dealer Conversion Rank', 'Rank'), M('Avg First Response (h)', 'Avg response (h)'), M('Response SLA Met %', 'SLA met'),
             M('Revenue (M TRY)'), M('Dealer Performance Flag', 'Flag')],
            'Dealer scorecard', 'Sorted by conversion · advisors: click a dealer, then use the Advisor page filter',
            sort_field=measure_ref('Lead-to-Sale Conversion'), filters=[filter_not_in('dim_dealer', 'dealer_name', ['Unknown dealer'])],
            color_cols={'_Measures.Dealer Performance Flag': 'Dealer Bar Colour'})
    pages.append(p)

    # ------------------------------------------------------------------ 3 Model & Segment Mix
    p = Page('model_mix', 'Model & Segment Mix',
             'MINI Cooper and the X1 / iX1 pair carry volume; conversion halves above 10M TRY',
             'Model & Segment Mix · What sells, at what discount, and how is electrification moving?')
    p.slicer_row()
    p.card('kpi_units', kx(0), 88, 240, 'Units sold', 'Units Sold', sub_measure='KPI Sub Units')
    p.card('kpi_price', kx(1), 88, 240, 'Avg sale price (M TRY)', 'Avg Sale Price (M TRY)', sub_text='final price per unit')
    p.card('kpi_disc', kx(2), 88, 240, 'Realised discount', 'Realised Discount %', sub_text='discount given / list value')
    p.card('kpi_fin', kx(3), 88, 240, 'Financing share', 'Financing Share', sub_text='of units sold')
    p.card('kpi_pipe', kx(4), 88, 240, 'Open pipeline value (bn TRY)', 'Pipeline Value (bn TRY)', sub_measure='KPI Sub Pipeline')
    p.bar('models', 20, 180, 500, 520, Col('dim_vehicle', 'model_label', 'Model'), [M('Units Sold', 'Units')],
          'Units sold by model — top 15', 'Colour = brand', series=Col('dim_vehicle', 'brand', 'Brand'), legend=True,
          colors={'BMW': C['blue'], 'MINI': C['orange'], 'Land Rover': C['aqua']},
          sort_field=measure_ref('Units Sold'), filters=[filter_measure_gt('Model Units Rank', 15, kind=3)], stacked=True)
    # brand colours are per series member: use scopeId-free approach -> data colours by series name via theme order is unreliable,
    # so we set them explicitly with a series selector below (patched after creation)
    p.bar('electrified', 530, 180, 730, 246, Col('dim_date', 'year_quarter', 'Quarter'),
          [M('Units Electrified', 'Electrified (EV + PHEV)'), M('Units Combustion', 'Combustion')],
          'Electrified models hold about half of sales every quarter', 'Share of units sold by powertrain · sale date',
          horizontal=False, stacked=True, legend=True, labels=True,
          colors={'_Measures.Units Electrified': C['blue'], '_Measures.Units Combustion': C['lightgrey']},
          sort_field=column_ref('dim_date', 'year_quarter'), sort_dir='Ascending', val_axis=True,
          filters=[filter_measure_gt('Units Sold', 20)], label_fmt='pct0')
    p.visuals[-1]['visual']['visualType'] = 'hundredPercentStackedColumnChart'
    p.bar('price_band', 530, 436, 730, 264, Col('dim_vehicle', 'price_band', 'List price band'), [M('Lead-to-Sale Conversion', 'Conversion')],
          'Conversion falls from 23% under 4M TRY to 9% above 10M TRY', 'Lead-to-sale conversion by list-price band',
          sort_field=column_ref('dim_vehicle', 'price_band'), sort_dir='Ascending',
          filters=[filter_not_in('dim_vehicle', 'price_band', ['Unknown'])], label_fmt='pct1')
    pages.append(p)

    # ------------------------------------------------------------------ 4 Data Quality
    p = Page('data_quality', 'Data Quality Monitor',
             '5,031 rows repaired or flagged in 25 checks — only exact duplicates were dropped',
             'Data Quality Monitor · How much did Silver repair, and can the numbers on the other pages be trusted?')
    p.card('kpi_checks', kx(0), 88, 240, 'Checks run', 'DQ Checks Run', sub_text='Silver notebook, every run')
    p.card('kpi_errchk', kx(1), 88, 240, 'Error checks with failures', 'DQ Error Checks', sub_measure='KPI Sub Error Checks', accent=True)
    p.card('kpi_rows', kx(2), 88, 240, 'Rows repaired or flagged', 'DQ Failed Rows', sub_text='sum over all checks')
    p.card('kpi_flagpct', kx(3), 88, 240, 'Leads carrying a flag', 'Leads With DQ Flags %', sub_measure='Leads With DQ Flags Text')
    p.card('kpi_lastrun', kx(4), 88, 240, 'Last run', 'DQ Last Run', sub_text='pl_lead_to_sale_daily')
    p.bar('dq_checks', 20, 180, 640, 520, Col('dq_results', 'check_name', 'Check'), [M('DQ Failed Rows', 'Rows')],
          'Most repairs are formatting; the errors are orphan keys and duplicates', 'Failed rows by check · orange = error severity',
          color_measure='Severity Colour', sort_field=measure_ref('DQ Failed Rows'), filters=[filter_measure_gt('DQ Failed Rows', 0)])
    p.bar('dq_actions', 670, 180, 590, 292, Col('dq_results', 'action', 'Action'), [M('DQ Failed Rows', 'Rows')],
          'What Silver did with each problem', 'Rows by action · a flag never deletes a row',
          sort_field=measure_ref('DQ Failed Rows'))
    p.note('dq_note', 670, 482, 590, 218, 'How to read this page',
           ['A flag means the check found a problem and Silver either corrected it (standardized, imputed, repointed) or marked it explicitly (flagged, nulled). Flagged rows stay in Gold with a dq_flags entry, so every KPI on the other pages can be reproduced with or without them.',
            'Ground truth: the synthetic generator injected 22 defect types with known counts; 12 of 18 comparable checks match exactly, the rest within ±8 rows (docs/dq_injections.md).'])
    pages.append(p)
    return pages


def patch_brand_colors(page):
    """Series colours for the model bar chart: selector by series member (scopeId on the brand column)."""
    v = next(v for v in page.visuals if v['name'] == 'models')
    dp = []
    for brand, c in {'BMW': C['blue'], 'MINI': C['orange'], 'Land Rover': C['aqua']}.items():
        dp.append({"properties": {"fill": color(c)},
                   "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0,
                       "Left": column_ref('dim_vehicle', 'brand'), "Right": {"Literal": {"Value": f"'{brand}'"}}}}}]}})
    v['visual']['objects']['dataPoint'] = dp


def build(out_dir, report_name='LeadToSale', model_name='LeadToSale'):
    rp = os.path.join(out_dir, f'{report_name}.Report')
    dfn = os.path.join(rp, 'definition')
    os.makedirs(os.path.join(dfn, 'pages'), exist_ok=True)
    os.makedirs(os.path.join(rp, 'StaticResources', 'RegisteredResources'), exist_ok=True)
    os.makedirs(os.path.join(rp, 'StaticResources', 'SharedResources', 'BaseThemes'), exist_ok=True)
    shutil.copy(BASE_THEME_SRC, os.path.join(rp, 'StaticResources', 'SharedResources', 'BaseThemes', 'CY24SU10.json'))
    json.dump(theme(), open(os.path.join(rp, 'StaticResources', 'RegisteredResources', 'BorusanLeadTheme.json'), 'w'), indent=2)

    pages = build_pages()
    patch_brand_colors(pages[2])
    for p in pages:
        pd_ = os.path.join(dfn, 'pages', p.name)
        os.makedirs(os.path.join(pd_, 'visuals'), exist_ok=True)
        json.dump(p.page_json(), open(os.path.join(pd_, 'page.json'), 'w'), indent=2, ensure_ascii=False)
        for v in p.visuals:
            vd = os.path.join(pd_, 'visuals', v['name'])
            os.makedirs(vd, exist_ok=True)
            json.dump(v, open(os.path.join(vd, 'visual.json'), 'w'), indent=2, ensure_ascii=False)
    json.dump({"$schema": PAGES_SCHEMA, "pageOrder": [p.name for p in pages], "activePageName": pages[0].name},
              open(os.path.join(dfn, 'pages', 'pages.json'), 'w'), indent=2)
    json.dump({"$schema": VERSION_SCHEMA, "version": "2.0.0"}, open(os.path.join(dfn, 'version.json'), 'w'), indent=2)
    json.dump({
        "$schema": REPORT_SCHEMA,
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": {"visual": "1.8.95", "report": "2.0.95", "page": "1.3.95"}, "type": "SharedResources"},
            "customTheme": {"name": "BorusanLeadTheme.json", "reportVersionAtImport": {"visual": "2.1.0", "report": "2.1.0", "page": "2.0.0"}, "type": "RegisteredResources"}},
        "filterConfig": {"filters": []},
        "objects": {"outspacePane": [{"properties": {"visible": lit(False), "expanded": lit(False)}}]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources", "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources", "items": [{"name": "BorusanLeadTheme.json", "path": "BorusanLeadTheme.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized", "defaultDrillFilterOtherVisuals": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
    }, open(os.path.join(dfn, 'report.json'), 'w'), indent=2)
    json.dump({"$schema": PBIR_SCHEMA, "version": "4.0", "datasetReference": {"byPath": {"path": f"../{model_name}.SemanticModel"}}},
              open(os.path.join(rp, 'definition.pbir'), 'w'), indent=2)
    json.dump({"$schema": PLATFORM_SCHEMA, "metadata": {"type": "Report", "displayName": report_name},
               "config": {"version": "2.0", "logicalId": str(uuid.uuid4())}}, open(os.path.join(rp, '.platform'), 'w'), indent=2)
    json.dump({"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
               "version": "1.0", "artifacts": [{"report": {"path": f"{report_name}.Report"}}], "settings": {"enableAutoRecovery": True}},
              open(os.path.join(out_dir, f'{report_name}.pbip'), 'w'), indent=2)
    return pages

if __name__ == '__main__':
    import sys
    ps = build(sys.argv[1])
    for p in ps:
        print(p.name, len(p.visuals), 'visuals')
