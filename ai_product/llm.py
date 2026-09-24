"""
Thin LLM layer for the Lead Intelligence Assistant (v2 — prompts as files, schema-validated output).

Provider-agnostic: any OpenAI-compatible endpoint works (OpenAI, Azure OpenAI, Groq, OpenRouter, a local Ollama).
Configure with environment variables (or a .env file next to app.py):

    LLM_API_KEY   = sk-...                       (required to enable the LLM)
    LLM_BASE_URL  = https://api.openai.com/v1    (optional; default OpenAI)
    LLM_MODEL     = gpt-4o-mini                  (optional)

Without a key everything still works: `next_best_action` falls back to a rule-based template and the app shows a
"template mode" badge. That fallback is not a hack — it is the offline path a dealer laptop without internet would use.

What changed in v2
    * The two system prompts live in prompts/*.system.md (reviewable, versioned, with a changelog).
    * Every LLM answer is validated against prompts/schemas.json. On failure the model gets one retry with the
      validation error; if that fails too, the template path is used. A malformed answer never reaches the UI.
    * `build_payload()` is public so the app can show the advisor exactly what the model saw.
"""
import json
import os

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
LEAD_FIELDS = ("source", "status", "created_at", "first_response_hours", "has_test_drive", "has_offer",
               "last_offer_status", "offer_discount_pct", "offer_final_price_try", "lead_age_days",
               "days_since_last_interaction", "interaction_count", "budget_try", "trade_in", "vehicle", "dealer_name")

_client = None
_prompts = {}
_schemas = None


def llm_enabled() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def load_prompt(name: str) -> str:
    """Read prompts/<name>.system.md (cached)."""
    if name not in _prompts:
        with open(os.path.join(PROMPT_DIR, f"{name}.system.md"), encoding="utf-8") as f:
            _prompts[name] = f.read()
    return _prompts[name]


def load_schema(name: str) -> dict:
    global _schemas
    if _schemas is None:
        with open(os.path.join(PROMPT_DIR, "schemas.json"), encoding="utf-8") as f:
            _schemas = json.load(f)
    return _schemas[name]


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL") or None)
    return _client


def _chat(system: str, user: str, json_mode: bool = True, max_tokens: int = 600) -> str:
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = _get_client().chat.completions.create(
        model=os.environ.get("LLM_MODEL", "gpt-4o-mini"), temperature=0.2, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kwargs)
    return resp.choices[0].message.content


def _validate(obj: dict, schema: dict):
    """Return None if `obj` matches `schema`, else a short error string. Uses jsonschema when installed."""
    try:
        import jsonschema
        jsonschema.validate(obj, schema)
        return None
    except ImportError:
        missing = [k for k in schema.get("required", []) if k not in obj]
        extra = [k for k in obj if k not in schema.get("properties", {})]
        for k, spec in schema.get("properties", {}).items():
            if k in obj and "enum" in spec and obj[k] not in spec["enum"]:
                return f"{k} must be one of {spec['enum']}"
        if missing or extra:
            return f"missing keys {missing}, unexpected keys {extra}"
        return None
    except Exception as e:  # jsonschema.ValidationError
        return str(e).splitlines()[0]


def _chat_json(prompt_name: str, user: str) -> dict:
    """Call the model with a file-based system prompt; validate; retry once with the error; raise if still invalid."""
    system, schema = load_prompt(prompt_name), load_schema(prompt_name)
    raw = _chat(system, user)
    obj = json.loads(raw)
    err = _validate(obj, schema)
    if err is None:
        return obj
    retry_user = user + "\n\nYour previous answer was rejected by the JSON schema: " + err + \
        "\nReturn ONLY a corrected JSON object with exactly the required keys."
    obj = json.loads(_chat(system, retry_user))
    err = _validate(obj, schema)
    if err is not None:
        raise ValueError("LLM output failed schema validation twice: " + err)
    return obj


def llm_signals(notes_text: str) -> dict:
    """LLM version of signals.rule_signals: reads the whole thread and returns a structured judgement."""
    return _chat_json("signal_extraction", notes_text or "(not yok)")


def build_payload(lead: dict, notes_text: str, score: float, reasons: list) -> dict:
    """The exact object the model sees for next_best_action — whitelisted lead fields only."""
    return {
        "lead": {k: (str(v) if v is not None else None) for k, v in lead.items() if k in LEAD_FIELDS},
        "conversion_probability": round(float(score), 3),
        "model_reasons": [r[2] for r in reasons],
        "advisor_notes": notes_text or "",
    }


def next_best_action(lead: dict, notes_text: str, score: float, reasons: list) -> dict:
    """
    Returns {"mode": "llm"|"template", "action": str, "summary": str, "draft_message": str, "confidence": str}.
    `lead` is a row of fact_leads as a dict; `reasons` is the list of (feature, effect, text) from the scorer.
    """
    if llm_enabled():
        user = json.dumps(build_payload(lead, notes_text, score, reasons), ensure_ascii=False)
        try:
            out = _chat_json("next_best_action", user)
            out["mode"] = "llm"
            return out
        except Exception as e:  # network / key / validation problems must never break the demo
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
    return {"mode": "template", "summary": summary, "action": action, "draft_message": draft, "confidence": "n/a"}
