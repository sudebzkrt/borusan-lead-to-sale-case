"""
Thin LLM layer for the Lead Intelligence Assistant.

Provider-agnostic: any OpenAI-compatible endpoint works (OpenAI, Azure OpenAI, Groq, OpenRouter, a local Ollama).
Configure with environment variables (or a .env file next to app.py):

    LLM_API_KEY   = sk-...                       (required to enable the LLM)
    LLM_BASE_URL  = https://api.openai.com/v1    (optional; default OpenAI)
    LLM_MODEL     = gpt-4o-mini                  (optional)

Without a key everything still works: `next_best_action` falls back to a rule-based template and the app shows a
"template mode" badge. That fallback is not a hack — it is the offline path a dealer laptop without internet would use.
"""
import json
import os

_client = None


def llm_enabled() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL") or None)
    return _client


def _chat(system: str, user: str, json_mode: bool = False, max_tokens: int = 500) -> str:
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = _get_client().chat.completions.create(
        model=os.environ.get("LLM_MODEL", "gpt-4o-mini"), temperature=0.2, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kwargs)
    return resp.choices[0].message.content


SIGNAL_SCHEMA = {
    "summary": "one sentence in Turkish summarising where this lead stands",
    "intent": "low | medium | high",
    "main_objection": "price | financing | stock | timing | competitor | none",
    "went_quiet": True,
    "next_action": "one concrete action for the advisor, in Turkish, max 20 words",
    "risk": "low | medium | high",
}


def llm_signals(notes_text: str) -> dict:
    """LLM version of signals.rule_signals: reads the whole thread and returns a structured judgement."""
    system = ("You are a sales-operations analyst for a premium car importer in Turkey. You read a sales advisor's "
              "notes about one lead and return ONLY a JSON object with exactly these keys: "
              + json.dumps(SIGNAL_SCHEMA, ensure_ascii=False))
    return json.loads(_chat(system, notes_text, json_mode=True))


def next_best_action(lead: dict, notes_text: str, score: float, reasons: list) -> dict:
    """
    Returns {"mode": "llm"|"template", "action": str, "summary": str, "draft_message": str}.
    `lead` is a row of fact_leads as a dict; `reasons` is the list of (feature, effect, text) from the scorer.
    """
    if llm_enabled():
        system = (
            "You are an assistant for BMW/MINI/Land Rover sales advisors in Turkey. Write in Turkish, concise, "
            "no fluff. Given the lead facts, a conversion probability from a model, the model's top reasons and the "
            "advisor's own notes, return ONLY JSON with keys: summary (1 sentence), action (1 concrete next step, "
            "max 25 words, say WHEN), draft_message (a WhatsApp message to the customer, max 60 words, polite 'siz' form, "
            "no discount promises unless an offer already exists).")
        user = json.dumps({
            "lead": {k: (str(v) if v is not None else None) for k, v in lead.items()
                     if k in ("source", "status", "created_at", "first_response_hours", "has_test_drive", "has_offer",
                              "offer_discount_pct", "offer_final_price_try", "lead_age_days", "days_since_last_interaction",
                              "interaction_count", "budget_try", "trade_in", "vehicle", "dealer_name")},
            "conversion_probability": round(float(score), 3),
            "model_reasons": [r[2] for r in reasons],
            "advisor_notes": notes_text,
        }, ensure_ascii=False)
        try:
            out = json.loads(_chat(system, user, json_mode=True))
            out["mode"] = "llm"
            return out
        except Exception as e:  # network / key problems must never break the demo
            fallback = _template_action(lead, score, reasons)
            fallback["summary"] += f" (LLM hatası, şablon kullanıldı: {type(e).__name__})"
            return fallback
    return _template_action(lead, score, reasons)


def _template_action(lead: dict, score: float, reasons: list) -> dict:
    vehicle = lead.get("vehicle") or "araç"
    quiet = (lead.get("days_since_last_interaction") or 0) >= 7
    if lead.get("has_offer") and score >= 0.4:
        durum = {"open": "açık", "expired": "süresi dolmuş", "rejected": "reddedilmiş"}.get(str(lead.get("last_offer_status")), "açık")
        action = f"Bugün ara: teklif {durum} durumda, karar için son soruyu sor ve teslimat tarihi öner."
    elif lead.get("has_test_drive") and not lead.get("has_offer"):
        action = "48 saat içinde yazılı teklif gönder; test sürüşü yapıldı ama teklif aşamasına geçilmedi."
    elif not lead.get("has_test_drive") and score >= 0.25:
        action = f"Bu hafta için {vehicle} test sürüşü randevusu teklif et (WhatsApp + arama)."
    elif quiet:
        action = f"{int(lead.get('days_since_last_interaction') or 0)} gündür temas yok: kısa bir WhatsApp mesajı + 2 gün sonra arama."
    else:
        action = "Standart takip: 3 iş günü içinde arama, ihtiyaç ve zamanlama netleştir."
    summary = f"Dönüşüm olasılığı %{score*100:.0f}. " + "; ".join(r[2] for r in reasons[:2]) + "."
    draft = (f"Merhaba, Borusan Oto'dan yazıyorum. {vehicle} ile ilgili görüşmemize istinaden size yardımcı olmak isterim. "
             "Uygun olduğunuz bir gün için kısa bir görüşme veya test sürüşü planlayabiliriz. İyi günler dilerim.")
    return {"mode": "template", "summary": summary, "action": action, "draft_message": draft}
