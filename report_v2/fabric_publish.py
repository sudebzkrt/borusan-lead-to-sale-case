"""
Publish the v2 report to Fabric from a Mac (no Power BI Desktop needed), via the Fabric REST API.

    az login --tenant <tenant> --scope https://api.fabric.microsoft.com/.default
    python report_v2/fabric_publish.py inspect  --workspace "<name>"   # read-only: backup model, list missing measures
    python report_v2/fabric_publish.py measures --workspace "<name>"   # add missing measures to sm_lead_to_sale/_Measures
    python report_v2/fabric_publish.py formats  --workspace "<name>"   # align format strings of existing measures with v2
    python report_v2/fabric_publish.py align    --workspace "<name>"   # sort-by columns + v2 DAX for REPLACE_MEASURES
    python report_v2/fabric_publish.py report   --workspace "<name>"   # create/update report 'LeadToSale v2' bound to the model

The measure definitions come from LeadToSale.SemanticModel/definition/tables/_Measures.tmdl (same DAX as
semantic_model/measures.dax + measures_v2_additions.dax). Measures that already exist in Fabric are left untouched.
The access token is taken from `az` per call and never written to disk.
"""
import argparse, base64, json, os, re, subprocess, sys, time, urllib.request, urllib.error

API = "https://api.fabric.microsoft.com/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_NAME = "sm_lead_to_sale"
REPORT_NAME = "LeadToSale v2"
BACKUP = os.path.join(HERE, ".fabric_backup")


def token():
    return subprocess.check_output(["az", "account", "get-access-token", "--resource",
                                    "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
                                   text=True).strip()


def call(method, path, body=None):
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            status, headers, raw = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}: {e.read().decode()[:1500]}")
    if status == 202:  # long-running operation
        loc = headers["Location"]
        while True:
            time.sleep(int(headers.get("Retry-After", 3)))
            op = call("GET", loc)
            if op.get("status") in ("Succeeded", "Failed", "Undefined"):
                if op["status"] != "Succeeded":
                    sys.exit(f"operation failed: {json.dumps(op)[:1500]}")
                try:
                    return call("GET", loc + "/result")
                except SystemExit:
                    return op
    return json.loads(raw) if raw else {}


def find(items, name, what):
    hit = [i for i in items if i["displayName"] == name]
    if not hit:
        sys.exit(f"{what} '{name}' not found. Available: {[i['displayName'] for i in items]}")
    return hit[0]


def workspace(name):
    return find(call("GET", "/workspaces")["value"], name, "workspace")["id"]


def model_definition(ws):
    m = find(call("GET", f"/workspaces/{ws}/semanticModels")["value"], MODEL_NAME, "semantic model")
    d = call("POST", f"/workspaces/{ws}/semanticModels/{m['id']}/getDefinition?format=TMDL")
    parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in d["definition"]["parts"]}
    return m["id"], parts


def measure_blocks(tmdl):
    """Split a TMDL table file into {measure name: block text}."""
    blocks, cur, name = {}, [], None
    for line in tmdl.splitlines():
        mm = re.match(r"^\tmeasure (?:'((?:[^']|'')+)'|(\S+))\s*=", line)
        if mm or (name and re.match(r"^\t\S", line) and not line.startswith("\tmeasure")):
            if name:
                blocks[name] = "\n".join(cur).rstrip()
            name, cur = (((mm.group(1) or "").replace("''", "'") or mm.group(2)), [line]) if mm else (None, [])
        elif name:
            cur.append(line)
    if name:
        blocks[name] = "\n".join(cur).rstrip()
    return blocks


def local_measures():
    with open(os.path.join(HERE, "LeadToSale.SemanticModel/definition/tables/_Measures.tmdl"), encoding="utf-8") as f:
        return measure_blocks(f.read())


def cmd_inspect(ws):
    mid, parts = model_definition(ws)
    os.makedirs(BACKUP, exist_ok=True)
    for p, txt in parts.items():
        out = os.path.join(BACKUP, p)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w", encoding="utf-8").write(txt)
    mpath = next((p for p in parts if p.endswith("tables/_Measures.tmdl")), None)
    remote = measure_blocks(parts[mpath]) if mpath else {}
    missing = [n for n in local_measures() if n not in remote]
    print(f"model {MODEL_NAME} ({mid}): {len(parts)} parts, backup in {BACKUP}")
    print(f"_Measures in Fabric: {len(remote)} · missing (to add): {len(missing)}")
    for n in missing:
        print("  +", n)
    local_tables = {f[:-5] for f in os.listdir(os.path.join(HERE, "LeadToSale.SemanticModel/definition/tables"))}
    remote_tables = {p.split("/")[-1][:-5] for p in parts if "/tables/" in p}
    print("tables only in local model:", sorted(local_tables - remote_tables) or "none")
    return mid, parts, mpath, missing


def cmd_measures(ws):
    mid, parts, mpath, missing = cmd_inspect(ws)
    if not mpath:
        sys.exit("no _Measures table in the Fabric model - create it first")
    if not missing:
        print("nothing to add")
        return
    loc = local_measures()
    # insert before the first column / partition / table annotation so measures stay together
    lines = parts[mpath].splitlines()
    at = next((i for i, l in enumerate(lines) if re.match(r"^\t(column|partition|annotation) ", l)), len(lines))
    new = "\n\n".join(loc[n] for n in missing).splitlines() + [""]
    parts[mpath] = "\n".join(lines[:at] + new + lines[at:]) + "\n"
    body = {"definition": {"parts": [{"path": p, "payload": base64.b64encode(t.encode()).decode(),
                                      "payloadType": "InlineBase64"} for p, t in parts.items()]}}
    call("POST", f"/workspaces/{ws}/semanticModels/{mid}/updateDefinition", body)
    print(f"added {len(missing)} measures to {MODEL_NAME}")


def cmd_formats(ws):
    """Align formatString of measures that exist in both models with the local (v2) model. DAX is not touched."""
    mid, parts, mpath, _ = cmd_inspect(ws)
    loc, text, changed = local_measures(), parts[mpath], []
    for name, block in measure_blocks(text).items():
        want = re.search(r"^\t\tformatString: (.*)$", loc.get(name, ""), re.M)
        if not want:
            continue
        have = re.search(r"^\t\tformatString: (.*)$", block, re.M)
        if have and have.group(1) == want.group(1):
            continue
        if have:
            new = block.replace(have.group(0), want.group(0), 1)
        else:  # insert right after the expression, before the first property line
            new = re.sub(r"^(\t\t(?:lineageTag|displayFolder|description):)", want.group(0) + r"\n\1", block, count=1, flags=re.M)
        text = text.replace(block, new, 1)
        changed.append(f"{name}: {have.group(1) if have else '-'} -> {want.group(1)}")
    if not changed:
        print("formats already aligned")
        return
    parts[mpath] = text
    body = {"definition": {"parts": [{"path": p, "payload": base64.b64encode(t.encode()).decode(),
                                      "payloadType": "InlineBase64"} for p, t in parts.items()]}}
    call("POST", f"/workspaces/{ws}/semanticModels/{mid}/updateDefinition", body)
    print("\n".join(changed))


REPLACE_MEASURES = ["Dealer Conversion Rank", "DQ Last Run"]  # v1 rank counted the UNK dealer; last run shortened to fit its card


def cmd_align(ws):
    """Copy sortByColumn settings from the local model and replace REPLACE_MEASURES with their local DAX."""
    mid, parts, mpath, _ = cmd_inspect(ws)
    tdir = os.path.join(HERE, "LeadToSale.SemanticModel/definition/tables")
    changed = []
    for f in sorted(os.listdir(tdir)):
        local = open(os.path.join(tdir, f), encoding="utf-8").read()
        rpath = next((p for p in parts if p.endswith("/tables/" + f)), None)
        if not rpath:
            continue
        text = parts[rpath]
        for col, sort in re.findall(r"^\tcolumn (\S+)\n(?:\t\t.*\n|\n)*?\t\tsortByColumn: (\S+)", local, re.M):
            m = re.search(rf"^\tcolumn {re.escape(col)}\n((?:\t\t.*\n|\n)*?)(?=^\t\S|\Z)", text, re.M)
            if not m or not re.search(rf"^\tcolumn {re.escape(sort)}$", text, re.M) or "sortByColumn:" in m.group(1):
                continue
            head = f"\tcolumn {col}\n"
            text = text.replace(m.group(0), head + f"\t\tsortByColumn: {sort}\n" + m.group(1), 1)
            changed.append(f"{f[:-5]}[{col}] sorted by {sort}")
        parts[rpath] = text
    loc, remote = local_measures(), measure_blocks(parts[mpath])
    for name in REPLACE_MEASURES:
        if name not in remote or name not in loc:
            continue
        tag = re.search(r"lineageTag: \S+", remote[name])
        new = re.sub(r"lineageTag: \S+", tag.group(0), loc[name]) if tag else loc[name]
        if new != remote[name]:
            parts[mpath] = parts[mpath].replace(remote[name], new, 1)
            changed.append(f"measure '{name}' replaced with v2 DAX")
    if not changed:
        print("already aligned")
        return
    body = {"definition": {"parts": [{"path": p, "payload": base64.b64encode(t.encode()).decode(),
                                      "payloadType": "InlineBase64"} for p, t in parts.items()]}}
    call("POST", f"/workspaces/{ws}/semanticModels/{mid}/updateDefinition", body)
    print("\n".join(changed))


def cmd_report(ws):
    mid = find(call("GET", f"/workspaces/{ws}/semanticModels")["value"], MODEL_NAME, "semantic model")["id"]
    root = os.path.join(HERE, "LeadToSale.Report")
    parts = []
    for dp, _, files in os.walk(root):
        for f in files:
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if f in (".DS_Store", ".platform") or rel == "definition.pbir":
                continue
            parts.append({"path": rel, "payload": base64.b64encode(open(full, "rb").read()).decode(),
                          "payloadType": "InlineBase64"})
    pbir = {"version": "4.0", "datasetReference": {"byConnection": {
        "connectionString": None, "pbiServiceModelId": None, "pbiModelVirtualServerName": "sobe_wowvirtualserver",
        "pbiModelDatabaseName": mid, "name": "EntityDataSource", "connectionType": "pbiServiceXmlaStyleLive"}}}
    parts.append({"path": "definition.pbir", "payload": base64.b64encode(json.dumps(pbir).encode()).decode(),
                  "payloadType": "InlineBase64"})
    existing = [r for r in call("GET", f"/workspaces/{ws}/reports")["value"] if r["displayName"] == REPORT_NAME]
    if existing:
        call("POST", f"/workspaces/{ws}/reports/{existing[0]['id']}/updateDefinition", {"definition": {"parts": parts}})
        rid = existing[0]["id"]
    else:
        rid = call("POST", f"/workspaces/{ws}/reports", {"displayName": REPORT_NAME, "definition": {"parts": parts}}).get("id")
    print(f"report '{REPORT_NAME}': https://app.powerbi.com/groups/{ws}/reports/{rid}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["inspect", "measures", "formats", "align", "report"])
    ap.add_argument("--workspace", required=True)
    a = ap.parse_args()
    ws = workspace(a.workspace)
    {"inspect": cmd_inspect, "measures": cmd_measures, "formats": cmd_formats, "align": cmd_align, "report": cmd_report}[a.step](ws)
