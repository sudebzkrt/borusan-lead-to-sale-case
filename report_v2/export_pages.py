"""
Export the four pages of the published v2 report with the Power BI ExportTo API (needs Fabric/trial capacity).
PNG export is disabled on some tenants, so each page is exported as PDF and rendered to PNG locally (PyMuPDF).

    python report_v2/export_pages.py --workspace-id <guid> --report-id <guid>

Writes report/screenshots/10a-10d_*.png and copies them to docs/img/page1-4.png for the deck
(then: node docs/build_deck_v2.js).
"""
import argparse, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PAGES = [("funnel_overview", "10a_report_v2_funnel.png", "page1.png"),
         ("dealer_performance", "10b_report_v2_dealers.png", "page2.png"),
         ("model_mix", "10c_report_v2_model_mix.png", "page3.png"),
         ("data_quality", "10d_report_v2_dq.png", "page4.png")]


def token():
    return subprocess.check_output(["az", "account", "get-access-token", "--resource",
                                    "https://analysis.windows.net/powerbi/api", "--query", "accessToken", "-o", "tsv"],
                                   text=True).strip()


def call(method, url, body=None, raw=False):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url} -> {e.code}: {e.read().decode()[:1000]}")
    return data if raw else json.loads(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", required=True)
    ap.add_argument("--report-id", required=True)
    a = ap.parse_args()
    base = f"https://api.powerbi.com/v1.0/myorg/groups/{a.workspace_id}/reports/{a.report_id}"
    for page, shot, deck in PAGES:
        job = call("POST", base + "/ExportTo", {"format": "PDF",
                                                 "powerBIReportConfiguration": {"pages": [{"pageName": page}]}})
        while job["status"] not in ("Succeeded", "Failed"):
            time.sleep(3)
            job = call("GET", f"{base}/exports/{job['id']}")
        if job["status"] != "Succeeded":
            sys.exit(f"{page}: export failed {job}")
        out = os.path.join(REPO, "report", "screenshots", shot)
        pdf = pymupdf.open(stream=call("GET", f"{base}/exports/{job['id']}/file", raw=True), filetype="pdf")
        pdf[0].get_pixmap(dpi=200).save(out)
        shutil.copy(out, os.path.join(REPO, "docs", "img", deck))
        print(page, "->", os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
