// Builds docs/presentation_v3.pptx (round 2) — run from the repo root: node docs/build_deck_v3.js
// Rules: the title IS the message; one visual per slide; at most three short lines of support text;
// report pages shown large with their design reasons; the AI workflow is part of the story, not a backup slide.
// Numbers come from docs/presentation_facts.md (python docs/build_fact_sheet.py). No speaker notes: the talk track is kept outside the repo.
const pptxgen = require("pptxgenjs");
const path = require("path");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.author = "Sude Bozkurt";
pres.title = "Lead-to-Sale Data Platform on Microsoft Fabric";

const IMG = (f) => path.join(__dirname, "img", f);
// Palette taken from the report so slides and report read as one product.
const C = { ink: "14213D", body: "2B3445", slate: "5B6472", muted: "8A93A1", tint: "F3F4F6", line: "DDE1E7", white: "FFFFFF",
            blue: "1C5CAB", orange: "EB6834", green: "0C8A4E", red: "D03B3B", grey: "B9C2CE", sky: "86B6EF", night: "0F1A2E" };
const F = "Arial";
const W = 13.33, H = 7.5, M = 0.6;
let n = 0;

function title(s, text, sub) {
  s.addText(text, { x: M, y: 0.4, w: W - 2 * M, h: 0.95, fontFace: F, fontSize: 26, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "top" });
  if (sub) s.addText(sub, { x: M, y: 1.33, w: W - 2 * M, h: 0.4, fontFace: F, fontSize: 15, color: C.slate, isTextBox: true, margin: 0 });
}
function footer(s, dark = false) {
  s.addText(`Borusan Otomotiv · Lead-to-Sale case · ${n}`, { x: M, y: H - 0.42, w: W - 2 * M, h: 0.28, fontFace: F, fontSize: 9, color: dark ? "6C7A92" : C.muted, isTextBox: true, margin: 0, align: "right" });
}
function slide(dark = false) {
  const s = pres.addSlide(); n++; s.background = { color: dark ? C.night : C.white }; return s;
}
function dot(s, x, y, label, color = C.orange, d = 0.42) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color }, line: { color } });
  s.addText(String(label), { x, y, w: d, h: d, fontFace: F, fontSize: 14, bold: true, color: C.white, align: "center", valign: "middle", isTextBox: true, margin: 0 });
}
function card(s, x, y, w, h, head, body, o = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: o.fill || C.tint }, line: { color: o.fill || C.tint } });
  s.addText(head, { x: x + 0.25, y: y + 0.2, w: w - 0.5, h: 0.4, fontFace: F, fontSize: o.hs || 16, bold: true, color: o.hc || C.ink, isTextBox: true, margin: 0 });
  s.addText(body, { x: x + 0.25, y: y + 0.65, w: w - 0.5, h: h - 0.8, fontFace: F, fontSize: o.bs || 13, color: o.bc || C.body, isTextBox: true, margin: 0, valign: "top" });
}
function box(s, x, y, w, h, text, fill, color = C.white, fs = 12, bold = true) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: fill }, line: { color: fill } });
  s.addText(text, { x, y, w, h, fontFace: F, fontSize: fs, bold, color, align: "center", valign: "middle", isTextBox: true, margin: 0.05 });
}
function arrow(s, x, y, w = 0.4, h = 0.28, color = C.grey) {
  s.addShape(pres.shapes.RIGHT_ARROW, { x, y, w, h, fill: { color }, line: { color } });
}
function stat(s, x, y, w, big, label, color = C.ink, size = 44) {
  s.addText(big, { x, y, w, h: 0.85, fontFace: F, fontSize: size, bold: true, color, isTextBox: true, margin: 0 });
  s.addText(label, { x, y: y + 0.85, w, h: 0.6, fontFace: F, fontSize: 13, color: C.slate, isTextBox: true, margin: 0, valign: "top" });
}
function framed(s, file, x, y, w, h) {
  s.addShape(pres.shapes.RECTANGLE, { x: x - 0.04, y: y - 0.04, w: w + 0.08, h: h + 0.08, fill: { color: C.white }, line: { color: C.line, width: 0.75 },
    shadow: { type: "outer", color: "000000", opacity: 0.12, blur: 8, offset: 2, angle: 90 } });
  s.addImage({ path: IMG(file), x, y, w, h });
}
function reasons(s, x, y, w, items) {
  let cy = y;
  items.forEach(([h, t], i) => {
    dot(s, x, cy, i + 1, C.orange, 0.36);
    s.addText(h, { x: x + 0.5, y: cy - 0.02, w: w - 0.5, h: 0.4, fontFace: F, fontSize: 14, bold: true, color: C.ink, isTextBox: true, margin: 0 });
    s.addText(t, { x: x + 0.5, y: cy + 0.36, w: w - 0.5, h: 0.85, fontFace: F, fontSize: 12, color: C.body, isTextBox: true, margin: 0, valign: "top" });
    cy += 1.3;
  });
}
function bullets(s, x, y, w, h, items, fs = 13, color = C.body) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 8 } })),
    { x, y, w, h, fontFace: F, fontSize: fs, color, isTextBox: true, margin: 0, valign: "top" });
}
const REPORT_W = 8.7, REPORT_H = REPORT_W * 1368 / 2400; // report screenshots are 2400 x 1368

// ---------------------------------------------------------------- 1 title
{
  const s = slide(true);
  s.addText("Lead-to-Sale Data Platform\non Microsoft Fabric", { x: M, y: 1.5, w: 8.6, h: 1.9, fontFace: F, fontSize: 44, bold: true, color: C.white, isTextBox: true, margin: 0 });
  s.addText("Three dirty source systems → one star schema → one report and one AI assistant that read the same numbers",
    { x: M, y: 3.6, w: 8.4, h: 0.9, fontFace: F, fontSize: 18, color: C.sky, isTextBox: true, margin: 0 });
  s.addText("Round 2 · built with AI, decided and verified by me", { x: M, y: 4.6, w: 8.4, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: C.orange, isTextBox: true, margin: 0 });
  s.addText("Sude Bozkurt · Veri Yönetimi ve Uygulamaları Uzman Yardımcısı · Borusan Otomotiv İthalat · September 2026",
    { x: M, y: 6.3, w: 11, h: 0.4, fontFace: F, fontSize: 12, color: "9AA6BA", isTextBox: true, margin: 0 });
  [["Gold", "E8A33D"], ["Silver", "B8C0CC"], ["Bronze", "9C6B3C"]].forEach(([t, c], i) =>
    box(s, 10.2, 1.8 + i * 0.95, 2.5, 0.7, t, c, C.night, 18));
}

// ---------------------------------------------------------------- 2 what changed since round 1
{
  const s = slide();
  title(s, "Round 1 feedback: the model worked, the report and the story did not", "What changed in round 2");
  const cols = [
    ["Report", "Default Power BI visuals, raw column names, unformatted numbers, no finding on any page.",
     "Every title states a finding, one accent colour, a real funnel, formatted numbers. Generated as a Power BI project and published to Fabric."],
    ["Story", "Architecture first, no process view, report pages as thumbnails, small text.",
     "Starts from the business problem and the lead lifecycle; each report page full size with its design reasons."],
    ["AI", "AI use hidden in a backup slide, the prompt nowhere.",
     "AI built the notebooks, the report and this deck from my specs. Prompts are versioned files, shown live in the app."]];
  cols.forEach(([h, before, now], i) => {
    const x = M + i * 4.1, y = 1.95, w = 3.9;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 4.1, rectRadius: 0.08, fill: { color: C.tint }, line: { color: C.tint } });
    dot(s, x + 0.25, y + 0.25, i + 1);
    s.addText(h, { x: x + 0.8, y: y + 0.22, w: w - 1, h: 0.48, fontFace: F, fontSize: 20, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "middle" });
    s.addText("ROUND 1", { x: x + 0.25, y: y + 0.95, w: w - 0.5, h: 0.3, fontFace: F, fontSize: 11, bold: true, color: C.muted, isTextBox: true, margin: 0, charSpacing: 1 });
    s.addText(before, { x: x + 0.25, y: y + 1.25, w: w - 0.5, h: 1.2, fontFace: F, fontSize: 13, color: C.slate, isTextBox: true, margin: 0, valign: "top" });
    s.addText("ROUND 2", { x: x + 0.25, y: y + 2.55, w: w - 0.5, h: 0.3, fontFace: F, fontSize: 11, bold: true, color: C.orange, isTextBox: true, margin: 0, charSpacing: 1 });
    s.addText(now, { x: x + 0.25, y: y + 2.85, w: w - 0.5, h: 1.75, fontFace: F, fontSize: 14, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "top" });
  });
  footer(s);
}

// ---------------------------------------------------------------- 3 the problem
{
  const s = slide();
  title(s, "Digital channels bring 55% of leads but convert at 7%; referrals convert at 44%", "The high-volume channels are the ones that need triage — that is where a data product pays off");
  stat(s, M, 2.0, 3.0, "15,000", "leads in 24 months (Sep 2024 – Aug 2026)");
  stat(s, M, 3.65, 3.0, "18.2%", "lead-to-sale conversion overall", C.blue);
  stat(s, M, 5.3, 3.0, "40–70", "open leads per advisor in the Istanbul branches, worked in CRM order", C.orange);
  s.addChart(pres.charts.BAR, [{ name: "Conversion", labels: ["Referral", "Existing customer", "Showroom walk-in", "Call center", "Web form", "Campaign", "Social media"], values: [43.9, 42.9, 38.4, 15.7, 7.9, 5.2, 4.6] }],
    { x: 4.0, y: 1.9, w: 8.7, h: 5.0, barDir: "bar", showTitle: true, title: "Lead-to-sale conversion by source (%) · orange = digital", titleFontFace: F, titleFontSize: 14, titleColor: C.ink,
      chartColors: [C.blue, C.blue, C.blue, C.blue, C.orange, C.orange, C.orange], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: C.body,
      catAxisLabelColor: C.body, catAxisLabelFontSize: 13, catAxisLabelFontFace: F, valAxisHidden: true, valAxisMaxVal: 50, valAxisMinVal: 0,
      valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, catAxisOrientation: "maxMin", barGapWidthPct: 45 });
  footer(s);
}

// ---------------------------------------------------------------- 4 lead lifecycle
{
  const s = slide();
  title(s, "One lead, four lanes: where the data is born and where the platform gives it back", "The lifecycle I modelled before any code — the assistant steps in at the two orange points");
  const lanes = [["Customer", "F7F8FA"], ["Advisor", "FFFFFF"], ["Source systems", "F7F8FA"], ["Fabric platform", "FFFFFF"]];
  const ly = 2.25, lh = 1.08, lx = M, lw = W - 2 * M, labw = 1.7;
  lanes.forEach(([name, fill], i) => {
    const y = ly + i * lh;
    s.addShape(pres.shapes.RECTANGLE, { x: lx, y, w: lw, h: lh, fill: { color: fill }, line: { color: C.line, width: 0.5 } });
    s.addText(name, { x: lx + 0.15, y, w: labw - 0.2, h: lh, fontFace: F, fontSize: 13, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "middle" });
  });
  const cx = lx + labw, cw = lw - labw, step = cw / 6;
  ["Enquiry", "First contact", "Test drive", "Offer", "Decision", "Delivery"].forEach((t, i) =>
    s.addText(t, { x: cx + i * step, y: ly - 0.38, w: step, h: 0.32, fontFace: F, fontSize: 13, bold: true, color: C.slate, align: "center", isTextBox: true, margin: 0 }));
  const bw = step - 0.2, bh = 0.62;
  const at = (lane, stage, text, fill = C.tint, color = C.ink, bold = false) => box(s, cx + stage * step + 0.1, ly + lane * lh + (lh - bh) / 2, bw, bh, text, fill, color, 11, bold);
  at(0, 0, "web form / call / walk-in"); at(0, 2, "drives the car"); at(0, 3, "compares with a rival dealer"); at(0, 4, "buys · postpones · leaves");
  at(1, 1, "who do I call first?", C.orange, C.white, true); at(1, 2, "books test drive"); at(1, 3, "sends offer, discount"); at(1, 4, "follow-up calls"); at(1, 5, "hands over");
  at(2, 0, "Web JSON · CRM lead"); at(2, 1, "CRM interactions + notes"); at(2, 2, "DMS test drives"); at(2, 3, "DMS offers"); at(2, 4, "CRM status, lost reason"); at(2, 5, "DMS sales");
  at(3, 0, "Bronze: land as-is"); at(3, 1, "Silver: 25 checks"); at(3, 2, "Gold: one row per lead");
  at(3, 3, "Power BI report"); at(3, 4, "Assistant: rank + next action", C.orange, C.white, true); at(3, 5, "scores back to Gold");
  s.addText("Data flows down every night (systems → platform); rankings and drafted messages flow back up to the advisor every morning.",
    { x: M, y: ly + 4 * lh + 0.15, w: W - 2 * M, h: 0.4, fontFace: F, fontSize: 13, italic: true, color: C.slate, isTextBox: true, margin: 0 });
  footer(s);
}

// ---------------------------------------------------------------- 5 how I worked with AI
{
  const s = slide();
  title(s, "How I worked: I specify and verify, AI builds", "The same loop for notebooks, DAX, the Power BI report, the prompts and this deck");
  const steps = [["Specify", "what each table and page must answer, the rules, the numbers it must match", C.ink],
                 ["Generate", "AI writes notebooks, DAX, the report definition (PBIP), prompts, slides", C.orange],
                 ["Verify", "Gold totals = report cards, DQ counts vs ground truth, every run end to end", C.blue],
                 ["Fix & ship", "AI applies the fix everywhere and publishes through the Fabric REST API", C.green]];
  const sw = 2.75, gap = 0.37;
  steps.forEach(([h, t, c], i) => {
    const x = M + i * (sw + gap), y = 1.95;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: sw, h: 1.65, rectRadius: 0.08, fill: { color: C.tint }, line: { color: C.tint } });
    dot(s, x + 0.2, y + 0.22, i + 1, c);
    s.addText(h, { x: x + 0.72, y: y + 0.2, w: sw - 0.85, h: 0.46, fontFace: F, fontSize: 17, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(t, { x: x + 0.2, y: y + 0.8, w: sw - 0.4, h: 1.0, fontFace: F, fontSize: 12.5, color: C.body, isTextBox: true, margin: 0, valign: "top" });
    if (i < 3) arrow(s, x + sw + 0.03, y + 0.8, gap - 0.06, 0.3);
  });
  // real example from this week
  const ey = 3.95;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: ey, w: 7.7, h: 2.55, rectRadius: 0.08, fill: { color: "FDF0EA" }, line: { color: "FDF0EA" } });
  s.addText("A real loop from this week", { x: M + 0.25, y: ey + 0.2, w: 7.2, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: C.orange, isTextBox: true, margin: 0 });
  bullets(s, M + 0.25, ey + 0.7, 7.2, 1.8, [
    "Report opened on my Mac: every title rendered in a serif fallback font",
    "Cause: 159 visuals pinned to 'Segoe UI' with no fallback — a theme change could not override it",
    "AI patched the report definition and re-published it through the Fabric API; I checked it in the browser"], 13);
  card(s, 8.55, ey, 4.18, 2.55, "Decisions that stay mine", "The scenario and the data grain · Silver rules (flag, never drop) · no leakage in the model · what each report page answers · what to leave out", { hs: 16, bs: 13 });
  footer(s);
}

// ---------------------------------------------------------------- 7 architecture
{
  const s = slide();
  title(s, "One lakehouse, three schemas, one pipeline, two consumers", "The same notebooks run on Fabric (Delta) and on a laptop (parquet) — the environment is detected, not configured");
  const y = 2.25, h = 1.05;
  box(s, 0.6, y, 1.95, h, "Sources\nCRM · Web · DMS", C.ink, C.white, 13);
  arrow(s, 2.62, y + 0.38, 0.45);
  box(s, 3.15, y, 1.95, h, "Bronze\nraw as-is + lineage", "9C6B3C", C.white, 13);
  arrow(s, 5.17, y + 0.38, 0.45);
  box(s, 5.7, y, 1.95, h, "Silver\nclean · conform · validate", "B8C0CC", C.ink, 13);
  arrow(s, 7.72, y + 0.38, 0.45);
  box(s, 8.25, y, 1.95, h, "Gold\nstar schema", "E8A33D", C.ink, 13);
  arrow(s, 10.27, y + 0.05, 0.45); arrow(s, 10.27, y + 0.72, 0.45);
  box(s, 10.8, y - 0.4, 1.93, 0.85, "Power BI\nDirect Lake, 4 pages", C.blue, C.white, 12);
  box(s, 10.8, y + 0.6, 1.93, 0.85, "Lead assistant\nmodel + Streamlit", C.orange, C.white, 12);
  s.addText("Data Factory pipeline: notebook 01 → 02 → 03, alert on failure, daily 06:00", { x: 3.15, y: y + 1.2, w: 7.1, h: 0.35, fontFace: F, fontSize: 13, italic: true, color: C.slate, isTextBox: true, margin: 0 });
  const cy = 4.5;
  card(s, 0.6, cy, 3.9, 2.2, "One lakehouse with schemas", "The simplest thing that keeps the boundaries explicit. A Warehouse is the next step for T-SQL users, not a day-one need.");
  card(s, 4.72, cy, 3.9, 2.2, "Direct Lake", "No import, no refresh schedule — the report reads the files Gold wrote. Same numbers in the report and in the assistant.");
  card(s, 8.84, cy, 3.89, 2.2, "Free text stays out of BI", "Advisor notes live in Gold for the assistant, not in the semantic model. 67k notes do not belong in a star schema.");
  footer(s);
}

// ---------------------------------------------------------------- 7a one lead through the layers
{
  const s = slide();
  title(s, "Follow one lead through the layers: L0000283, a showroom visit that became a sale", "Real values from the pipeline — the same record in every layer, from source file to report number");
  const cols = [
    ["Source files", C.ink, "CRM · DMS", [
      ["crm_customers.csv", "\"Ali Doğan\" 5324778874\n\"ALI DOĞAN\" 0532 477 88 74"],
      ["dms_offers.csv", "ISKONTO_ORANI \"8,1\"\nTEKLIF_TARIHI \"29.10.2024\""],
      ["dms_sales.csv", "SATIS_TARIHI \"07.11.2024\""]]],
    ["Bronze", "9C6B3C", "as received", [
      ["Values", "unchanged — every column stored as text"],
      ["+ lineage", "_source_system = dms\n_source_file = dms_offers.csv\n_ingest_ts"]]],
    ["Silver", "7D8796", "cleaned + checked", [
      ["Customer", "2 records → 1 golden C005693\nphone +905324778874"],
      ["Lead", "repointed to C005693\ndq_flags: customer_repointed"],
      ["Offer", "discount 8.1 (number)\ndates parsed as Istanbul time"]]],
    ["Gold", "C98A1E", "fact_leads · 1 row", [
      ["Funnel", "test drive ✓ (4/5) · offer ✓ 8.1%\nwon ✓ in 14.1 days"],
      ["Speed", "first response 0.38 h → band ≤ 1h"],
      ["Keys", "dealer D004 · date 20241024"]]],
    ["Semantic model", C.blue, "Direct Lake", [
      ["Counts in", "[Leads], [Won Leads], [Revenue]"],
      ["Shows up as", "Showroom walk-in 38.4%\nBorusan Oto Kartal\n≤ 1h band 35.2%"]]]];
  const cw = 2.22, gap = 0.255, y0 = 1.95, ch = 4.95;
  cols.forEach(([h, c, sub, rows], i) => {
    const x = M + i * (cw + gap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: y0, w: cw, h: ch, rectRadius: 0.08, fill: { color: C.tint }, line: { color: C.tint } });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: y0, w: cw, h: 0.72, rectRadius: 0.08, fill: { color: c }, line: { color: c } });
    s.addText([{ text: h, options: { bold: true, fontSize: 15, breakLine: true } }, { text: sub, options: { fontSize: 11 } }],
      { x: x + 0.12, y: y0, w: cw - 0.24, h: 0.72, fontFace: F, color: C.white, valign: "middle", isTextBox: true, margin: 0 });
    let y = y0 + 0.92;
    rows.forEach(([k, v]) => {
      s.addText(k, { x: x + 0.14, y, w: cw - 0.28, h: 0.28, fontFace: F, fontSize: 11.5, bold: true, color: C.slate, isTextBox: true, margin: 0 });
      const lines = v.split("\n").reduce((a, l) => a + Math.max(1, Math.ceil(l.length / 21)), 0);
      s.addText(v, { x: x + 0.14, y: y + 0.3, w: cw - 0.28, h: 0.27 * lines + 0.06, fontFace: F, fontSize: 13, color: C.ink, isTextBox: true, margin: 0, valign: "top" });
      y += 0.3 + 0.27 * lines + 0.3;
    });
    if (i < 4) arrow(s, x + cw + 0.02, y0 + 2.2, gap - 0.04, 0.26, C.orange);
  });
  footer(s);
}

// ---------------------------------------------------------------- 8 bronze + silver
{
  const s = slide();
  title(s, "Bronze keeps the evidence, Silver turns every source quirk into an explicit, logged rule", "5,031 rows repaired or flagged in 25 checks — only exact duplicates were dropped");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 1.9, w: W - 2 * M, h: 0.72, rectRadius: 0.06, fill: { color: "F4ECE4" }, line: { color: "F4ECE4" } });
  s.addText([{ text: "Bronze  ", options: { bold: true, color: "9C6B3C" } },
             { text: "lands every file exactly as received: all columns as text, nested JSON kept, three lineage columns. A value that fails to parse becomes a counted issue in Silver, never a silent null.", options: { color: C.ink } }],
    { x: M + 0.25, y: 1.9, w: W - 2 * M - 0.5, h: 0.72, fontFace: F, fontSize: 13, isTextBox: true, margin: 0, valign: "middle" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.ink }, fontSize: 12.5 } });
  const c = (t, o = {}) => ({ text: t, options: { color: C.body, fontSize: 12, ...o } });
  const rows = [[hdr("In the source"), hdr("Silver rule"), hdr("Rows")],
    [c("Same person twice: \"Ali Doğan\" / \"ALI DOĞAN\""), c("golden record by name + phone + e-mail; leads repointed to it"), c("180 merged · 223 leads", { bold: true })],
    [c("Phone in five formats"), c("normalised to +90XXXXXXXXXX (E.164)"), c("908", { bold: true })],
    [c("\"İstanbul\", \"ISTANBUL\", \"istanbul\""), c("Turkish-aware city canon"), c("352", { bold: true })],
    [c("DMS: \"8,1\", \"29.10.2024\", E/H, Turkish headers"), c("decimal comma, dd.MM.yyyy and booleans parsed; English column names"), c("all DMS rows", { bold: true })],
    [c("Web leads only in nested JSON"), c("CRM leads ∪ web leads → one silver.leads table"), c("15,000 leads", { bold: true })],
    [c("Dealer id not in master data"), c("nulled, flagged → 'Unknown dealer' in Gold"), c("120", { bold: true })],
    [c("150% discount, negative response time"), c("nulled and flagged, the row is kept"), c("43 + 45", { bold: true })]];
  s.addTable(rows, { x: M, y: 2.85, w: W - 2 * M, colW: [4.3, 5.53, 2.3], fontFace: F, border: { type: "solid", color: C.line, pt: 0.75 },
    fill: { color: C.white }, valign: "middle", rowH: 0.47, margin: 0.07 });
  s.addText("Every check writes to dq_results (check, rows, severity, action) · verified against the defects I injected: 12 of 18 exact, the rest within ±8 rows",
    { x: M, y: 6.72, w: W - 2 * M, h: 0.35, fontFace: F, fontSize: 12.5, italic: true, color: C.slate, isTextBox: true, margin: 0 });
  footer(s);
}

// ---------------------------------------------------------------- 9 gold star schema
{
  const s = slide();
  title(s, "Gold is a star schema Power BI reads as-is: one row per lead, the whole funnel pre-joined", "Natural keys · an 'Unknown' member in every dimension · 78 measures in one table");
  const cxs = 4.3, cys = 4.4;
  const dims = [["dim_date", 1.3, 2.3], ["dim_dealer", 4.3, 2.1], ["dim_vehicle", 7.3, 2.3], ["dim_lead_source", 1.3, 6.4], ["dim_customer", 4.3, 6.6], ["dim_advisor", 7.3, 6.4]];
  dims.forEach(([, x, y]) => s.addShape(pres.shapes.LINE, { x: Math.min(x, cxs), y: Math.min(y, cys), w: Math.abs(x - cxs), h: Math.abs(y - cys), line: { color: C.grey, width: 1.5 }, flipH: (x < cxs) !== (y < cys) }));
  dims.forEach(([t, x, y]) => box(s, x - 0.95, y - 0.28, 1.9, 0.56, t, C.ink, C.white, 12));
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cxs - 1.45, y: cys - 0.85, w: 2.9, h: 1.7, rectRadius: 0.08, fill: { color: "E8A33D" }, line: { color: "E8A33D" } });
  s.addText([{ text: "fact_leads", options: { bold: true, fontSize: 17, breakLine: true } },
             { text: "1 row per lead · test drive · offer · won · response band · DQ flags", options: { fontSize: 11 } }],
    { x: cxs - 1.35, y: cys - 0.8, w: 2.7, h: 1.6, fontFace: F, color: C.night, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  card(s, 8.9, 1.95, 3.83, 1.5, "Single-direction star", "Every relationship many-to-one, dimension → fact. No two-way filters, no ambiguous paths.", { bs: 12.5 });
  card(s, 8.9, 3.6, 3.83, 1.5, "Unknown rows, not lost rows", "A lead with a broken dealer id shows as 'Unknown dealer' instead of vanishing in a join.", { bs: 12.5 });
  card(s, 8.9, 5.25, 3.83, 1.5, "Two conversion measures", "Won / all leads, and won / closed leads — the honest trend, not dragged down by open leads.", { bs: 12.5 });
  footer(s);
}

// ---------------------------------------------------------------- 9b semantic model
{
  const s = slide();
  title(s, "From Gold to the semantic model: Direct Lake, a clean star, and measures instead of raw columns", "sm_lead_to_sale on Fabric — what went in, how it is wired, and how I checked it");
  card(s, M, 1.95, 5.9, 1.45, "What goes in — and what stays out", "11 Gold tables in. Advisor notes and interactions stay out: free text has no place in a star schema, and personal data stays in Silver.", { bs: 12.5 });
  card(s, M, 3.55, 5.9, 1.55, "How it is wired", "18 relationships, all many-to-one, one direction. A lead is counted by its creation date; the closing date is an inactive relationship used with USERELATIONSHIP. dim_date is marked as the date table.", { bs: 12.5 });
  card(s, M, 5.25, 5.9, 1.5, "What the user sees", "78 measures in one _Measures table, each with a format. Raw numeric columns are hidden. Months and bands sorted by an order column, not alphabetically.", { bs: 12.5 });
  const cx = 6.75, cw = W - M - cx;
  s.addText("Two conversion measures, on purpose", { x: cx, y: 1.95, w: cw, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: C.ink, isTextBox: true, margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: cx, y: 2.45, w: cw, h: 2.0, fill: { color: C.night }, line: { color: C.night } });
  s.addText([
    { text: "Lead-to-Sale Conversion =", options: { color: "E8A33D", breakLine: true } },
    { text: "  DIVIDE ( [Won Leads], [Leads] )", options: { color: "E6EAF0", breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: "Conversion Rate (Closed) =", options: { color: "E8A33D", breakLine: true } },
    { text: "  DIVIDE ( [Won Leads],", options: { color: "E6EAF0", breakLine: true } },
    { text: "          [Won Leads] + [Lost Leads] )", options: { color: "E6EAF0" } }],
    { x: cx + 0.25, y: 2.6, w: cw - 0.5, h: 1.75, fontFace: "Courier New", fontSize: 14, isTextBox: true, margin: 0, valign: "top" });
  s.addText("The first is today's number; the second is the honest trend, because open leads would drag recent months down.",
    { x: cx, y: 4.65, w: cw, h: 0.7, fontFace: F, fontSize: 13.5, color: C.body, isTextBox: true, margin: 0 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: 5.6, w: cw, h: 1.15, rectRadius: 0.06, fill: { color: "E7F4EC" }, line: { color: "E7F4EC" } });
  s.addText([{ text: "Checked: ", options: { bold: true, color: C.green } }, { text: "the Gold notebook's totals equal the report cards — 15,000 leads, 2,736 won, 18.2%.", options: { color: C.ink } }],
    { x: cx + 0.2, y: 5.6, w: cw - 0.4, h: 1.15, fontFace: F, fontSize: 14, isTextBox: true, margin: 0, valign: "middle" });
  footer(s);
}

// ---------------------------------------------------------------- 10 report page 1
{
  const s = slide();
  title(s, "Every report page answers one question, and every title states the finding", "Funnel Overview — the page a sales director reads first");
  framed(s, "page1.png", M, 1.95, REPORT_W, REPORT_H);
  reasons(s, 9.65, 2.0, 3.08, [
    ["Titles are findings", "a sentence with a number, not a field name"],
    ["One accent colour", "orange always means digital leads"],
    ["Honest trend line", "closed-lead conversion, so recent months are not understated"],
    ["Hand-over to part 2", "752 stale open leads — the assistant's queue"]]);
  footer(s);
}

// ---------------------------------------------------------------- 11 report page 2
{
  const s = slide();
  title(s, "Two authorized dealers convert below 75% of the network — and speed matters in every channel", "Dealer & Advisor Performance — colour only where it means something");
  framed(s, "page2.png", M, 1.95, REPORT_W, REPORT_H);
  reasons(s, 9.65, 2.0, 3.08, [
    ["Red and green = a flag", "below 75% or above 125% of the network; everything else grey"],
    ["Channel split", "response time shown for digital and non-digital separately, so source mix does not fake the effect"],
    ["Click to filter", "click a dealer bar and the whole page follows"]]);
  footer(s);
}

// ---------------------------------------------------------------- 13 live demo
{
  const s = slide(true);
  s.addText("Live demo", { x: M, y: 0.8, w: 8, h: 0.9, fontFace: F, fontSize: 40, bold: true, color: C.white, isTextBox: true, margin: 0 });
  s.addText("Four minutes, four stops", { x: M, y: 1.65, w: 8, h: 0.45, fontFace: F, fontSize: 18, color: C.sky, isTextBox: true, margin: 0 });
  [["Lakehouse", "bronze / silver / gold schemas — one raw table next to its cleaned twin"],
   ["Pipeline", "the last run in Monitor — three notebook steps chained"],
   ["Report", "Funnel → click 'Web form' → Dealer page follows → Data Quality"],
   ["Assistant", "ranked open leads → one lead → reasons → next action → the prompt behind it"]].forEach(([h, b], i) => {
    dot(s, M, 2.65 + i * 0.95, i + 1);
    s.addText(h, { x: M + 0.6, y: 2.6 + i * 0.95, w: 2.3, h: 0.5, fontFace: F, fontSize: 20, bold: true, color: C.orange, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(b, { x: M + 3.0, y: 2.6 + i * 0.95, w: 9.3, h: 0.5, fontFace: F, fontSize: 16, color: "E6EAF0", isTextBox: true, margin: 0, valign: "middle" });
  });
  s.addText("If something breaks: the report pages in this deck, then the local run (run_local.sh + Streamlit)", { x: M, y: 6.55, w: 12, h: 0.4, fontFace: F, fontSize: 12, italic: true, color: "9AA6BA", isTextBox: true, margin: 0 });
  footer(s, true);
}

// ---------------------------------------------------------------- 14 the assistant
{
  const s = slide();
  title(s, "Lead Intelligence Assistant: which open lead do I call first, why, and what do I say?", "A data product for advisors, built on Gold only — scores written back to the lakehouse");
  const w = 7.7, h = w * 1438 / 2940;
  framed(s, "app_ranked.png", M, 2.2, w, h);
  card(s, 8.6, 1.95, 4.13, 1.55, "Scores every open lead", "Conversion probability from 42 point-in-time features, with three plain-language reasons.", { bs: 12.5 });
  card(s, 8.6, 3.65, 4.13, 1.55, "Rules at scale, LLM at the last mile", "Keyword rules read 15k note threads; the LLM reads one lead to draft the next action.", { bs: 12.5 });
  card(s, 8.6, 5.35, 4.13, 1.4, "Never depends on the network", "No API key → a template writes the action. The demo cannot break.", { bs: 12.5 });
  footer(s);
}

// ---------------------------------------------------------------- 15 prompts
{
  const s = slide();
  title(s, "The prompts are files, not strings: versioned, schema-checked and measured", "How the LLM layer is designed — ai_product/prompts/ and ai_product/eval/");
  const ax = M, ay = 1.95;
  s.addText("Anatomy of the next-best-action prompt", { x: ax, y: ay, w: 6.4, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: C.ink, isTextBox: true, margin: 0 });
  [["Role", "assistant for one advisor and one lead"],
   ["Inputs, whitelisted", "lead fields, score, three reasons, the notes — no IDs"],
   ["Hard rules", "never invent price, stock or delivery · never promise a discount"],
   ["Examples", "two worked cases where the rules are ambiguous"],
   ["JSON schema", "output checked; one retry, then the template"]].forEach(([h, b], i) => {
    const y = ay + 0.5 + i * 0.88;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ax, y, w: 6.4, h: 0.78, rectRadius: 0.06, fill: { color: C.tint }, line: { color: C.tint } });
    s.addText(h, { x: ax + 0.2, y, w: 2.0, h: 0.78, fontFace: F, fontSize: 13, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(b, { x: ax + 2.25, y, w: 4.0, h: 0.78, fontFace: F, fontSize: 12.5, color: C.body, isTextBox: true, margin: 0, valign: "middle" });
  });
  const rx = 7.45;
  s.addText("Measured, not assumed", { x: rx, y: ay, w: 5.28, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: C.ink, isTextBox: true, margin: 0 });
  s.addText("40 note threads labelled by AI in two passes (90%+ agreement); keyword rules scored against them", { x: rx, y: ay + 0.45, w: 5.28, h: 0.6, fontFace: F, fontSize: 12.5, color: C.slate, isTextBox: true, margin: 0 });
  s.addChart(pres.charts.BAR, [{ name: "Accuracy", labels: ["went quiet", "buying signal", "intent", "main objection"], values: [100.0, 92.5, 87.5, 72.5] }],
    { x: rx, y: ay + 1.1, w: 5.28, h: 3.2, barDir: "bar", chartColors: [C.blue, C.blue, C.blue, C.orange], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: C.body,
      dataLabelFormatCode: '0.0"%"', catAxisLabelColor: C.body, catAxisLabelFontSize: 13, catAxisLabelFontFace: F, valAxisHidden: true, valAxisMaxVal: 115, valAxisMinVal: 0,
      valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, catAxisOrientation: "maxMin", barGapWidthPct: 45 });
  s.addText("Orange = the weak spot, where the LLM should earn its place", { x: rx, y: ay + 4.4, w: 5.28, h: 0.4, fontFace: F, fontSize: 12.5, italic: true, color: C.orange, isTextBox: true, margin: 0 });
  footer(s);
}

// ---------------------------------------------------------------- 15b what changed between prompt versions
{
  const s = slide();
  title(s, "What changed between prompt versions — and why", "From ai_product/prompts/CHANGELOG.md · every change is re-scored before it ships");
  const vy = 1.95, vw = 5.6, vh = 2.45;
  const ver = [
    ["v1 · string in code", C.muted, [
      "Role and a JSON answer: summary, action, drafted message",
      "Two rules from day one: no discount promises, every action says WHEN",
      "Extractor: a JSON example, no written labelling rules"]],
    ["v2 · a file with a changelog", C.orange, [
      "Rules for quiet, closed and empty-notes leads; never mention 'AI' to the customer",
      "Two worked examples; output checked against a JSON schema, one retry, then the template",
      "Extractor: written labelling rules with a tie-break order, so it can be measured"]]];
  ver.forEach(([h, c, items], i) => {
    const x = M + i * (vw + 0.93);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: vy, w: vw, h: vh, rectRadius: 0.08, fill: { color: i ? "FDF0EA" : C.tint }, line: { color: i ? "FDF0EA" : C.tint } });
    s.addText(h, { x: x + 0.25, y: vy + 0.2, w: vw - 0.5, h: 0.45, fontFace: F, fontSize: 18, bold: true, color: i ? C.orange : C.ink, isTextBox: true, margin: 0 });
    bullets(s, x + 0.25, vy + 0.8, vw - 0.5, vh - 0.95, items, 13.5);
  });
  arrow(s, M + vw + 0.2, vy + vh / 2 - 0.18, 0.53, 0.36, C.orange);
  s.addText("Why v2: I reviewed v1 against a failure list — nothing stopped a pushy message to a lead that went quiet, or \"according to our model\" leaking into a customer message.",
    { x: M, y: vy + vh + 0.2, w: W - 2 * M, h: 0.6, fontFace: F, fontSize: 13.5, italic: true, color: C.body, isTextBox: true, margin: 0 });
  const cy = 5.55;
  s.addText("How a change is checked", { x: M, y: cy - 0.05, w: 3.0, h: 0.4, fontFace: F, fontSize: 15, bold: true, color: C.ink, isTextBox: true, margin: 0 });
  [["Re-score", "run_eval.py before and after; a drop on any field is reverted"], ["Read aloud", "three leads in the app: offer, quiet, closed"], ["Test every rule", "each new rule gets a note thread in the eval set"]]
    .forEach(([h, t], i) => {
      const x = 3.6 + i * 3.1;
      dot(s, x, cy, i + 1, C.blue, 0.36);
      s.addText([{ text: h + "  ", options: { bold: true, color: C.ink } }, { text: t, options: { color: C.body } }],
        { x: x + 0.48, y: cy - 0.08, w: 2.55, h: 0.75, fontFace: F, fontSize: 12, isTextBox: true, margin: 0, valign: "top" });
    });
  footer(s);
}

// ---------------------------------------------------------------- 16 the model
{
  const s = slide();
  title(s, "The model: AUC 0.84 before the offer stage, and no peeking at the answer", "Point-in-time snapshots, outcome notes removed, split by time");
  stat(s, M, 2.0, 2.7, "0.84", "AUC before the offer stage — the slice that matters", C.blue, 44);
  stat(s, M, 3.65, 2.7, "3.7×", "more wins in the top 10% of pre-offer leads than average", C.orange, 44);
  stat(s, M, 5.3, 2.7, "0.82", "AUC on all test snapshots (8,886)", C.ink, 44);
  s.addChart(pres.charts.LINE, [
      { name: "Predicted", labels: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"], values: [0.2, 1.0, 2.2, 4.0, 6.8, 11.3, 19.7, 33.1, 51.1, 73.4] },
      { name: "Actual", labels: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"], values: [0.3, 1.7, 5.1, 8.0, 10.6, 16.4, 21.3, 35.9, 45.9, 60.1] }],
    { x: 3.6, y: 1.9, w: 5.0, h: 3.4, showTitle: true, title: "Calibration by score decile (% won)", titleFontFace: F, titleFontSize: 13, titleColor: C.ink,
      chartColors: [C.blue, C.orange], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 6, showLegend: true, legendPos: "b", legendFontSize: 11,
      catAxisLabelColor: C.slate, catAxisLabelFontSize: 10, valAxisLabelColor: C.slate, valAxisLabelFontSize: 10, valGridLine: { color: "E3E7EC", size: 0.5 }, catGridLine: { style: "none" } });
  card(s, 8.9, 1.95, 3.83, 3.35, "How I avoided fooling myself", "A closed lead's final state is not a training example — 'has an offer' is the answer written on the exam. Each lead gives snapshots from moments in its life; the note that records the outcome is removed; train before March 2026, test after.", { bs: 12.5 });
  bullets(s, 3.6, 5.55, 9.1, 1.3, [
    "Limits I state myself: synthetic notes are cleaner than real ones; the top decile is optimistic (73% predicted vs 60% actual)",
    "Dealer effects make it a ranking within a dealer, not across dealers"], 12.5);
  footer(s);
}

// ---------------------------------------------------------------- 17 next
{
  const s = slide();
  title(s, "Next for the platform: four steps, each a named Fabric feature with a reason and a size", "In the order I would do them — each one removes a limit of the case version");
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.ink }, fontSize: 12.5 } });
  const cell = (t, o = {}) => ({ text: t, options: { color: C.body, fontSize: 12, ...o } });
  const rows = [
    [hdr("Step"), hdr("How, in Fabric"), hdr("Why it matters — the limit it removes"), hdr("Size")],
    [cell("1  Incremental loads", { bold: true, color: C.ink }), cell("Bronze appends by ingest_date; Silver uses MERGE INTO on the natural keys; a run_date pipeline parameter"),
     cell("Today every run reloads everything. At real CRM volume (millions of interactions) a full reload will not fit the 06:00 window."), cell("~2 days")],
    [cell("2  History (SCD2)", { bold: true, color: C.ink }), cell("Surrogate keys + valid_from / valid_to on dim_dealer and dim_advisor"),
     cell("When an advisor moves to another dealer, their old leads move with them today — past dealer rankings get silently rewritten."), cell("~2 days")],
    [cell("3  Access (RLS + KVKK)", { bold: true, color: C.ink }), cell("A dealer role in the semantic model filtering dim_dealer by the user's e-mail; OneLake workspace roles"),
     cell("Each dealer sees only its own leads. Phone and e-mail already stay in Silver; RLS closes the report side."), cell("~1 day")],
    [cell("4  Quality gates", { bold: true, color: C.ink }), cell("dq_results appended per run → DQ trend page; pipeline fails above an error threshold; Activator alert to the data team"),
     cell("Today a bad source file only raises warnings and still reaches the report. A gate stops it at Silver."), cell("~1–2 days")]];
  s.addTable(rows, { x: M, y: 1.95, w: W - 2 * M, colW: [2.3, 3.85, 4.85, 1.13], fontFace: F, border: { type: "solid", color: C.line, pt: 0.75 },
    fill: { color: C.white }, valign: "middle", rowH: [0.45, 1.05, 1.05, 1.05, 1.05], margin: 0.08 });
  s.addText("About one working week in total; none of it changes the Gold tables the report and the assistant already read.",
    { x: M, y: 6.75, w: W - 2 * M, h: 0.35, fontFace: F, fontSize: 13, italic: true, color: C.slate, isTextBox: true, margin: 0 });
  footer(s);
}

// ---------------------------------------------------------------- 17b product roadmap
{
  const s = slide();
  title(s, "Next for the product: a 90-day pilot where every phase has a number to hit", "The assistant is only worth scaling if advisors convert more digital leads with it than without it");
  const phases = [
    ["Days 1–30", "Pilot", C.ink, [
      "Two Istanbul branches, 8 advisors with 40–70 open leads each",
      "Scores in a Power BI page next to the report; a morning summary in Teams",
      "Advisor feedback buttons: called / not relevant / wrong reason — written back to Gold"],
      "Baseline: digital conversion 6.7%"],
    ["Days 31–60", "Measure", C.orange, [
      "Half the advisors work the ranked queue, half keep CRM order (A/B, 8 weeks)",
      "Retrain on real outcomes and the feedback; monthly AUC written to a metrics table",
      "Run the LLM note extractor if it beats the rules on 'main objection' (72.5%)"],
      "Target: +1 pt digital conversion"],
    ["Days 61–90", "Scale", C.blue, [
      "All 14 dealers, with dealer-level RLS",
      "SHAP explanations instead of single-feature reasons",
      "Drift alert when AUC drops below 0.78 or the source mix shifts"],
      "Go / no-go on the A/B result"]];
  phases.forEach(([when, h, c, items, kpi], i) => {
    const x = M + i * 4.1, y = 1.95, w = 3.9, hh = 4.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: hh, rectRadius: 0.08, fill: { color: C.tint }, line: { color: C.tint } });
    s.addText(when, { x: x + 0.25, y: y + 0.18, w: w - 0.5, h: 0.3, fontFace: F, fontSize: 12, bold: true, color: c, isTextBox: true, margin: 0, charSpacing: 1 });
    s.addText(h, { x: x + 0.25, y: y + 0.48, w: w - 0.5, h: 0.45, fontFace: F, fontSize: 20, bold: true, color: C.ink, isTextBox: true, margin: 0 });
    bullets(s, x + 0.25, y + 1.05, w - 0.5, 2.3, items, 12.5);
    box(s, x + 0.25, y + hh - 0.7, w - 0.5, 0.5, kpi, c, C.white, 13);
    if (i < 2) arrow(s, x + w + 0.02, y + hh / 2 - 0.14, 0.16, 0.28);
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 6.2, w: W - 2 * M, h: 0.6, rectRadius: 0.06, fill: { color: "FDF0EA" }, line: { color: "FDF0EA" } });
  s.addText([{ text: "Why +1 point is worth it:  ", options: { bold: true, color: C.orange } },
             { text: "~4,160 digital leads a year × 1 pt ≈ 42 extra sales ≈ 200M TRY a year (illustrative prices)", options: { color: C.ink } }],
    { x: M + 0.25, y: 6.2, w: W - 2 * M - 0.5, h: 0.6, fontFace: F, fontSize: 13.5, isTextBox: true, margin: 0, valign: "middle" });
  footer(s);
}

// ---------------------------------------------------------------- 18 thank you
{
  const s = slide(true);
  s.addText("Thank you", { x: M, y: 2.3, w: 9, h: 1.1, fontFace: F, fontSize: 44, bold: true, color: C.white, isTextBox: true, margin: 0 });
  s.addText("Repo: notebooks, DAX, Power BI project, prompts + eval, data generator, AI product, docs", { x: M, y: 3.6, w: 11, h: 0.5, fontFace: F, fontSize: 16, color: "C9D1DB", isTextBox: true, margin: 0 });
  s.addText("sude.bozkurt@ozu.edu.tr", { x: M, y: 4.2, w: 11, h: 0.5, fontFace: F, fontSize: 16, color: C.sky, isTextBox: true, margin: 0 });
  footer(s, true);
}

// ---------------------------------------------------------------- 19 backup: AI split
{
  const s = slide();
  title(s, "Backup — who did what: decisions, AI work, verification", "The split behind slide 5");
  [["I decided", ["The business scenario and the data grain", "One lakehouse with schemas, no Warehouse", "Silver rules: flag, never drop", "Star schema with Unknown members", "Snapshot training to avoid leakage", "What each report page answers"]],
   ["AI built", ["Notebook cells and refactors", "DAX measures and the Streamlit app", "Turkish keyword rules for the notes", "The Power BI project (PBIP) from my page spec", "Publishing and fixes via the Fabric REST API", "This deck, from my outline"]],
   ["I verified", ["Every notebook run end to end, locally and in Fabric", "DQ counts against the injected ground truth", "Gold totals = report cards", "Model metrics on a time split, calibration by decile", "40 AI-labelled note threads, 6 disagreements reviewed", "The report on my own Mac, in the browser"]]]
    .forEach(([h, items], i) => {
      const x = M + i * 4.1;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.95, w: 3.9, h: 4.8, rectRadius: 0.08, fill: { color: C.tint }, line: { color: C.tint } });
      s.addText(h, { x: x + 0.25, y: 2.15, w: 3.4, h: 0.45, fontFace: F, fontSize: 17, bold: true, color: [C.ink, C.orange, C.blue][i], isTextBox: true, margin: 0 });
      bullets(s, x + 0.25, 2.75, 3.45, 3.9, items, 13);
    });
  footer(s);
}

// ---------------------------------------------------------------- 20 backup: Fabric screenshots
{
  const s = slide();
  title(s, "Backup — pipeline run and lakehouse schemas in Fabric", "Screenshots from the Fabric trial workspace");
  const w = 8.6, h = w * 1264 / 2792;
  framed(s, "pipeline.png", M, 2.0, w, h);
  const lw = 2.9, lh = lw * 612 / 526;
  framed(s, "lakehouse.png", 9.83, 2.0, lw, lh);
  s.addText("Left: pl_lead_to_sale_daily — three notebook activities chained. Right: lh_borusan with bronze / silver / gold schemas.",
    { x: M, y: 6.3, w: 12, h: 0.4, fontFace: F, fontSize: 13, color: C.body, isTextBox: true, margin: 0 });
  footer(s);
}

// ---------------------------------------------------------------- backup: one dataset
{
  const s = slide();
  title(s, "Backup — one synthetic dataset feeds both deliverables — built dirty on purpose", "15,000 leads · 6,000 customers · 14 dealers · 56 advisors · 38 trims · 22 defect types with known counts");
  const ex = 0.8, ey = 2.1;
  box(s, ex + 2.3, ey, 2.0, 0.6, "CUSTOMERS", C.ink);
  box(s, ex, ey + 1.35, 2.0, 0.6, "DEALERS", C.ink);
  box(s, ex, ey + 2.35, 2.0, 0.6, "ADVISORS", C.ink);
  box(s, ex + 2.3, ey + 1.3, 2.0, 0.75, "LEADS\n15,000", "E8A33D", C.night, 13);
  box(s, ex + 4.6, ey + 1.35, 2.0, 0.6, "VEHICLES", C.ink);
  [["TEST DRIVES  5,686", C.blue], ["OFFERS  7,114", C.blue], ["SALES  2,736", C.green], ["INTERACTIONS  67k + notes", C.orange]]
    .forEach(([t, c], i) => box(s, ex + 2.3, ey + 2.55 + i * 0.66, 3.5, 0.5, t, c, C.white, 12));
  const ln = { color: C.slate, width: 1.5 };
  s.addShape(pres.shapes.LINE, { x: ex + 3.3, y: ey + 0.6, w: 0, h: 0.7, line: ln });
  s.addShape(pres.shapes.LINE, { x: ex + 2.0, y: ey + 1.65, w: 0.3, h: 0, line: ln });
  s.addShape(pres.shapes.LINE, { x: ex + 2.0, y: ey + 2.65, w: 0.3, h: 0, line: ln });
  s.addShape(pres.shapes.LINE, { x: ex + 4.3, y: ey + 1.65, w: 0.3, h: 0, line: ln });
  s.addShape(pres.shapes.LINE, { x: ex + 3.3, y: ey + 2.05, w: 0, h: 0.5, line: ln });
  card(s, 7.7, 1.95, 5.03, 1.45, "Why synthetic", "No customer data leaves a company for an interview case. Seed 42, Turkish names and cities, realistic volumes.");
  card(s, 7.7, 3.6, 5.03, 1.45, "Why deliberately dirty", "Duplicate customers, five phone formats, orphan keys, 150% discounts — every count written down as ground truth.");
  card(s, 7.7, 5.25, 5.03, 1.45, "Why causal structure", "Source, dealer, response time, test drive and price all move conversion, so the model has something real to learn.");
  footer(s);
}

// ---------------------------------------------------------------- backup: report page 3
{
  const s = slide();
  title(s, "Backup — what sells: conversion halves above 10M TRY, electrified models hold half of sales", "Model & Segment Mix — volume, price and powertrain on one page");
  framed(s, "page3.png", M, 1.95, REPORT_W, REPORT_H);
  reasons(s, 9.65, 2.0, 3.08, [
    ["Three colours, one legend", "top 15 models coloured by brand — no 30-colour treemap"],
    ["Price bands, not a scatter", "23% under 4M TRY → 9% above 10M TRY"],
    ["Units, not percentages alone", "every card has a unit and a subtitle"]]);
  footer(s);
}

// ---------------------------------------------------------------- backup: report page 4
{
  const s = slide();
  title(s, "Backup — Data Quality Monitor: what Silver repaired, and what it did with each problem", "Report page 4 — reads dq_results, the log every Silver check writes");
  framed(s, "page4.png", M, 1.95, REPORT_W, REPORT_H);
  footer(s);
}

pres.writeFile({ fileName: path.join(__dirname, "presentation_v3.pptx") }).then(() => console.log("written presentation_v3.pptx"));
