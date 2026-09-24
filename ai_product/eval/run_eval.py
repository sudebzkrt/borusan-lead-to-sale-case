"""
Measure the note-signal extractors against 40 labelled lead threads.

    python ai_product/eval/run_eval.py          # keyword rules (signals.rule_signals) vs reference labels
    python ai_product/eval/run_eval.py --llm    # also run llm.llm_signals (needs LLM_API_KEY) and compare

Writes eval/RESULTS.md and eval/predictions.csv.

Reference labels (eval_notes.csv, columns ref_*) were produced in two AI labelling passes that both follow the rules in
prompts/signal_extraction.system.md; the first pass is kept in labels_first_pass.csv, disagreements were reviewed and the
second pass is the reference. Because labellers and the LLM share one written definition, disagreement is measurable
rather than a matter of taste.
"""
import argparse, json, os, sys, time
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # ai_product/
from signals import rule_signals  # noqa: E402

FIELDS = ["intent", "main_objection", "went_quiet", "buying_signal"]


def rules_to_labels(text: str) -> dict:
    """Map the 0/1 keyword signals onto the evaluation schema (same definitions as the LLM prompt)."""
    s = rule_signals(text)
    last = (text or "").strip().split("\n")[-1].lower()
    quiet_last = any(k in last for k in ["ulaşılamadı", "cevap yok", "sesli mesaj", "dönüş yapmıyor", "cevap bekleniyor"])
    if s["financing_interest"] and "kredi onayı çıkmadı" in (text or "").lower():
        obj = "financing"
    elif s["stock_issue"] and "teslim süresi uzun" in (text or "").lower():
        obj = "stock"
    elif s["delay_signal"]:
        obj = "timing"
    elif s["price_objection"]:
        obj = "price"
    elif s["competitor"]:
        obj = "competitor"
    else:
        obj = "none"
    if s["buying_signal"]:
        intent = "high"
    elif quiet_last or s["delay_signal"] or "kredi onayı çıkmadı" in (text or "").lower():
        intent = "low"
    elif s["financing_interest"] or s["upsell_signal"] or s["corporate_fleet"] or s["price_objection"]:
        intent = "medium"
    else:
        intent = "low"
    if s["buying_signal"]:
        obj = "none"
    return {"intent": intent, "main_objection": obj, "went_quiet": int(quiet_last), "buying_signal": int(s["buying_signal"])}


def llm_labels(text: str) -> dict:
    from llm import llm_signals
    out = llm_signals(text)
    return {"intent": out["intent"], "main_objection": out["main_objection"],
            "went_quiet": int(bool(out["went_quiet"])), "buying_signal": int(bool(out["buying_signal"]))}


def score(df, prefix):
    rows = []
    for f in FIELDS:
        ref = df[f"ref_{f}"].astype(str)
        pred = df[f"{prefix}_{f}"].astype(str)
        acc = (ref == pred).mean()
        row = {"field": f, "accuracy": round(acc, 3)}
        if f in ("went_quiet", "buying_signal"):
            tp = ((ref == "1") & (pred == "1")).sum(); fp = ((ref == "0") & (pred == "1")).sum(); fn = ((ref == "1") & (pred == "0")).sum()
            row["precision"] = round(tp / (tp + fp), 3) if tp + fp else None
            row["recall"] = round(tp / (tp + fn), 3) if tp + fn else None
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--llm", action="store_true"); args = ap.parse_args()
    df = pd.read_csv(os.path.join(HERE, "eval_notes.csv"))
    for f in ("ref_went_quiet", "ref_buying_signal"):
        df[f] = df[f].astype(int)
    preds = df.notes_text.apply(rules_to_labels).apply(pd.Series).add_prefix("rules_")
    df = pd.concat([df, preds], axis=1)
    tables = {"Keyword rules (signals.py)": score(df, "rules")}
    if args.llm:
        outs = []
        for t in df.notes_text:
            outs.append(llm_labels(t)); time.sleep(0.2)
        lp = pd.DataFrame(outs).add_prefix("llm_")
        df = pd.concat([df, lp], axis=1)
        tables["LLM extractor (prompts/signal_extraction.system.md)"] = score(df, "llm")
    df.to_csv(os.path.join(HERE, "predictions.csv"), index=False)
    md = [f"# Extractor evaluation — {len(df)} labelled threads", "",
          f"Sample: {len(df)} leads ({df.status.value_counts().to_dict()}), labelled with the rules in "
          "`prompts/signal_extraction.system.md` in two AI passes; disagreements reviewed, second pass is the reference. "
          "Accuracy = share of threads where the extractor's label equals the reference.", ""]
    first = os.path.join(HERE, "labels_first_pass.csv")
    if os.path.exists(first):
        fp = df[["lead_id"] + [f"ref_{f}" for f in FIELDS]].merge(pd.read_csv(first), on="lead_id")
        agree = pd.DataFrame([{"field": f, "agreement": round((fp[f"ref_{f}"].astype(str) == fp[f"first_{f}"].astype(str)).mean(), 3)}
                              for f in FIELDS])
        n_diff = int((fp[[f"ref_{f}" for f in FIELDS]].astype(str).values != fp[[f"first_{f}" for f in FIELDS]].astype(str).values).any(axis=1).sum())
        md += ["## Labeller agreement (first pass vs reference)", "", agree.to_markdown(index=False), "",
               f"{n_diff} of {len(fp)} threads differed in at least one field and were reviewed.", ""]
    for name, t in tables.items():
        md += [f"## {name}", "", t.to_markdown(index=False), ""]
    md += ["## Reading the numbers", "",
           "* `went_quiet` and `buying_signal` are the two fields the scorer uses as features; precision matters more than recall there "
           "(a false 'buying signal' inflates a score).",
           "* `main_objection` is the hardest field: threads often carry two obstacles and the label follows the most recent one. "
           "Disagreements are listed in `predictions.csv` (compare `ref_*` with `rules_*` / `llm_*`).",
           "* The keyword rules see substrings only; the LLM reads the whole thread. The LLM column is empty until `run_eval.py --llm` "
           "is run with an API key.", ""]
    open(os.path.join(HERE, "RESULTS.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
