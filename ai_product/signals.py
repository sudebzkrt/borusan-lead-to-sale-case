"""
Turn advisors' free-text notes into structured signals.

Two extractors with the same output schema:

* `rule_signals(text)`   — deterministic keyword rules. Free, instant, runs over all 15k leads. Used for model features.
* `llm_signals(text)`    — an LLM reads the notes and fills the same fields, plus a one-line summary. Used on demand
                           in the app for the lead the advisor is looking at (see llm.py).

Why both: an LLM call per lead per day for 15k leads is money and latency for very little gain on the *model*;
the model only needs coarse signals (is there a price objection? did they go quiet?). The LLM earns its keep at
the "last mile" — summarising the thread and drafting the next action for one lead at a time.

The schema is deliberately small. Every field is a 0/1 flag except `signal_count`.
"""
import re

SIGNAL_RULES = {
    # signal            : list of Turkish lowercase substrings / regexes found in advisor notes
    "buying_signal":    [r"sözleşme", r"kapora", r"teklifi kabul", r"ödeme planı", r"netleşti", r"memnun kaldı",
                         r"plaka", r"sigorta işlem"],
    "price_objection":  [r"fiyat.{0,20}yüksek", r"bütçe", r"daha iyi fiyat", r"iskonto verilemedi", r"tereddüt",
                         r"rakip bayi", r"karşılaştırıyor"],
    "financing_interest": [r"finansman", r"kredi", r"vade", r"evrak"],
    "stock_issue":      [r"stokta", r"teslim süresi", r"renk yok", r"alternatif renk"],
    "went_quiet":       [r"ulaşılamadı", r"cevap yok", r"sesli mesaj", r"dönüş yapmıyor", r"cevap bekleniyor",
                         r"okundu"],
    "delay_signal":     [r"erteledi", r"yıl sonu", r"acele etmiyor", r"iş seyahati", r"haftaya", r"sonra tekrar",
                         r"zamanı yok", r"iptal edildi"],
    "competitor":       [r"rakip"],
    "corporate_fleet":  [r"filo", r"şirket aracı", r"kurumsal"],
    "trade_in_mention": [r"takas"],
    "upsell_signal":    [r"üst donanım", r"yeni fiyat çalışılacak"],
    "positive_test_drive": [r"test sürüşü sonrası", r"araçtan memnun"],
    "spouse_decision":  [r"eşiyle", r"ailesiyle"],
}
_COMPILED = {k: re.compile("|".join(v)) for k, v in SIGNAL_RULES.items()}
SIGNAL_NAMES = list(SIGNAL_RULES.keys())


def _norm(text: str) -> str:
    # Turkish lowercase: İ -> i, I -> ı is what Python does; we want a forgiving match, so fold both to i.
    return (text or "").replace("İ", "i").replace("I", "ı").lower()


def rule_signals(text: str) -> dict:
    t = _norm(text)
    out = {name: int(bool(rx.search(t))) for name, rx in _COMPILED.items()}
    out["signal_count"] = sum(out.values())
    return out


def drop_outcome_note(notes_text: str, is_closed: bool) -> str:
    """
    For closed leads the *last* note records the outcome ("Sözleşme imzalandı", "Rakip markadan araç almış").
    Training on it would be target leakage — the model would learn to read the answer. We drop that last line
    for closed leads so features reflect what an advisor could have known *before* the lead closed.
    """
    if not notes_text or not is_closed:
        return notes_text or ""
    lines = notes_text.split("\n")
    return "\n".join(lines[:-1]) if len(lines) > 1 else ""


if __name__ == "__main__":
    demo = ("2026-04-14 [phone] Müşteri BMW X1 ile ilgileniyor, fiyat bilgisi verildi.\n"
            "2026-04-18 [whatsapp] Fiyat konusunda tereddütlü. Finansman seçenekleri anlatıldı.\n"
            "2026-04-25 [phone] 3 kez arandı, ulaşılamadı.")
    print(rule_signals(demo))
