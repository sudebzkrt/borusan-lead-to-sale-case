"""
Lead Intelligence Assistant — Streamlit UI for sales advisors and showroom managers.

Run:  streamlit run ai_product/app.py
Data: reads the Gold export (data/gold/*) written by 03_gold_star_schema + train_lead_scorer.
LLM:  optional — set LLM_API_KEY (see llm.py). Without it the app runs in template mode.

UI language is Turkish because the users are dealer staff; code and comments are English.
"""
import os, sys, glob, json
import pandas as pd
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from llm import next_best_action, llm_enabled, llm_signals  # noqa: E402

REPO = os.environ.get("REPO_ROOT", os.path.dirname(HERE))
GOLD = os.path.join(REPO, "data", "gold")
MODEL_DIR = os.path.join(HERE, "model")

# optional .env next to app.py (LLM_API_KEY=...)
env_path = os.path.join(HERE, ".env")
if os.path.exists(env_path):
    for line in open(env_path, encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

st.set_page_config(page_title="Lead Intelligence Assistant", page_icon="🚗", layout="wide")


@st.cache_data(show_spinner=False)
def gold(name):
    files = glob.glob(os.path.join(GOLD, name, "*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


@st.cache_data(show_spinner=False)
def load():
    scores = gold("lead_scores")
    leads = gold("fact_leads")
    veh = gold("dim_vehicle")[["vehicle_id", "trim_label", "list_price_try"]]
    dea = gold("dim_dealer")[["dealer_id", "dealer_name"]]
    adv = gold("dim_advisor")[["advisor_id", "advisor_name"]]
    cus = gold("dim_customer")[["customer_id", "full_name", "customer_type", "city"]]
    df = (scores.merge(leads.drop(columns=["dealer_id", "advisor_id", "has_test_drive", "has_offer", "lead_age_days",
                                            "days_since_last_interaction"]), on="lead_id")
                .merge(veh, on="vehicle_id", how="left").merge(dea, on="dealer_id", how="left")
                .merge(adv, on="advisor_id", how="left").merge(cus, on="customer_id", how="left"))
    df["reasons_list"] = df["reasons"].apply(json.loads)
    df["created_at"] = pd.to_datetime(df["created_at"])
    metrics = json.load(open(os.path.join(MODEL_DIR, "metrics.json")))
    imp = pd.read_csv(os.path.join(MODEL_DIR, "feature_importance.csv"))
    cal = pd.read_csv(os.path.join(MODEL_DIR, "calibration.csv"))
    dq = gold("dq_results")
    return df, metrics, imp, cal, dq


df, metrics, importance, calibration, dq = load()
BAND_LABEL = {"A": "A · sıcak", "B": "B · ilgili", "C": "C · takip", "D": "D · düşük"}
BAND_COLOR = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "⚪"}

# ------------------------------------------------------------------ sidebar
st.sidebar.title("🚗 Lead Intelligence")
st.sidebar.caption("Borusan Otomotiv · lead-to-sale asistanı")
page = st.sidebar.radio("Sayfa", ["Öncelikli lead'ler", "Lead detayı", "Model kartı", "Veri hattı"], label_visibility="collapsed")
st.sidebar.divider()
dealer_opts = ["Tümü"] + sorted(df["dealer_name"].dropna().unique().tolist())
dealer = st.sidebar.selectbox("Bayi", dealer_opts)
sub = df if dealer == "Tümü" else df[df["dealer_name"] == dealer]
adv_opts = ["Tümü"] + sorted(sub["advisor_name"].dropna().unique().tolist())
advisor = st.sidebar.selectbox("Danışman", adv_opts)
sub = sub if advisor == "Tümü" else sub[sub["advisor_name"] == advisor]
bands = st.sidebar.multiselect("Skor bandı", ["A", "B", "C", "D"], default=["A", "B", "C", "D"], format_func=BAND_LABEL.get)
sub = sub[sub["score_band"].isin(bands)]
st.sidebar.divider()
st.sidebar.caption(("🤖 LLM modu: **açık**" if llm_enabled() else "📄 LLM modu: **şablon** (LLM_API_KEY yok)"))
st.sidebar.caption(f"Skorlama: {pd.to_datetime(df['scored_at'].iloc[0]).strftime('%d.%m.%Y %H:%M')} UTC · {len(df)} açık lead")


def fmt_try(x):
    return "—" if pd.isna(x) else f"{x/1e6:.2f}M ₺"


# ------------------------------------------------------------------ page 1
if page == "Öncelikli lead'ler":
    st.title("Bugün kimi aramalıyım?")
    st.caption("Açık lead'ler, satışa dönüşme olasılığına göre sıralı. Skor, Gold katmanındaki huni verisi ve danışman notlarından hesaplanır.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Açık lead", len(sub))
    c2.metric("A bandı (sıcak)", int((sub["score_band"] == "A").sum()))
    c3.metric("7+ gündür temassız", int((sub["days_since_last_interaction"] >= 7).sum()))
    c4.metric("Fiyat itirazı olan", int(sub["price_objection"].sum()))

    view = sub.sort_values("score", ascending=False).copy()
    view["Skor"] = (view["score"] * 100).round(0).astype(int)
    view["Bant"] = view["score_band"].map(lambda b: f"{BAND_COLOR[b]} {b}")
    view["Müşteri"] = view["full_name"]
    view["Araç"] = view["trim_label"]
    view["Kaynak"] = view["source"]
    view["Yaş (gün)"] = view["lead_age_days"].round(0).astype(int)
    view["Son temas (gün)"] = view["days_since_last_interaction"].round(0)
    view["Aşama"] = view.apply(lambda r: "Teklif" if r["has_offer"] else ("Test sürüşü" if r["has_test_drive"] else "Temas"), axis=1)
    view["Sinyaller"] = view.apply(lambda r: " ".join(s for s, f in [("💰itiraz", r["price_objection"]), ("🔇sessiz", r["went_quiet"]),
                                                                     ("⏳erteleme", r["delay_signal"]), ("✅alım", r["buying_signal"]),
                                                                     ("🏦finans", r["financing_interest"]), ("📦stok", r["stock_issue"])] if f), axis=1)
    view["Neden"] = view["reasons_list"].apply(lambda rs: "; ".join(r[2].split(" (")[0] for r in rs[:2]))
    cols = ["Bant", "Skor", "lead_id", "Müşteri", "Araç", "dealer_name", "advisor_name", "Kaynak", "Aşama", "Yaş (gün)", "Son temas (gün)", "Sinyaller", "Neden"]
    st.dataframe(view[cols].rename(columns={"lead_id": "Lead", "dealer_name": "Bayi", "advisor_name": "Danışman"}),
                 width="stretch", hide_index=True, height=560,
                 column_config={"Skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=100, format="%d%%")})
    st.caption("Skor = modelin satışa dönüşme olasılığı. Bantlar: A ≥ %45, B %25–45, C %10–25, D < %10. "
               "'Neden' sütunu skoru en çok etkileyen iki faktördür (modelden, şablon değil).")

# ------------------------------------------------------------------ page 2
elif page == "Lead detayı":
    st.title("Lead detayı ve sonraki adım")
    ordered = sub.sort_values("score", ascending=False)
    if ordered.empty:
        st.info("Filtreye uyan açık lead yok.")
        st.stop()
    label = lambda r: f"{BAND_COLOR[r.score_band]} {r.score*100:.0f}% · {r.lead_id} · {r.full_name} · {r.trim_label}"
    choice = st.selectbox("Lead seç", ordered.index, format_func=lambda i: label(ordered.loc[i]))
    r = ordered.loc[choice]

    left, right = st.columns([1, 1.4])
    with left:
        st.metric("Dönüşüm olasılığı", f"%{r.score*100:.0f}", BAND_LABEL[r.score_band])
        st.markdown(f"**Müşteri:** {r.full_name} ({r.customer_type}, {r.city})  \n"
                    f"**Araç:** {r.trim_label} · liste {fmt_try(r.list_price_try)}  \n"
                    f"**Bayi / danışman:** {r.dealer_name} / {r.advisor_name}  \n"
                    f"**Kaynak:** {r.source}{(' · ' + str(r.campaign_name)) if isinstance(r.campaign_name, str) else ''}  \n"
                    f"**Oluşturma:** {r.created_at:%d.%m.%Y} · {int(r.lead_age_days)} gün önce  \n"
                    f"**İlk yanıt:** {('%.1f saat' % r.first_response_hours) if pd.notna(r.first_response_hours) else '—'}  \n"
                    f"**Bütçe:** {fmt_try(r.budget_try)} · takas: {'evet' if r.trade_in else 'hayır'}  \n"
                    f"**Test sürüşü:** {'✅' if r.has_test_drive else '—'} · **Teklif:** "
                    f"{('✅ %s, %%%.1f iskonto, %s' % (r.last_offer_status, r.offer_discount_pct, fmt_try(r.offer_final_price_try))) if r.has_offer else '—'}  \n"
                    f"**Etkileşim:** {int(r.n_interactions)} · son temas {int(r.days_since_last_interaction) if pd.notna(r.days_since_last_interaction) else '—'} gün önce")
        st.subheader("Skoru ne belirledi?")
        for feat, eff, text in r.reasons_list:
            st.markdown(f"{'🟢' if eff > 0 else '🔴'} {text}")
        if r.dq_flags:
            st.caption(f"Veri kalitesi notu: bu lead'de Silver katmanı şu düzeltmeleri yaptı → `{r.dq_flags}`")
    with right:
        st.subheader("Danışman notları")
        st.text_area("notlar", r.notes_text or "(not yok)", height=220, label_visibility="collapsed", disabled=True)
        st.subheader("Sonraki en iyi adım")
        if st.button("✨ Öneri üret", type="primary"):
            lead_dict = r.to_dict()
            lead_dict["vehicle"] = r.trim_label
            with st.spinner("Hazırlanıyor…"):
                out = next_best_action(lead_dict, r.notes_text, r.score, r.reasons_list)
            st.info(out["summary"])
            st.success(f"**Aksiyon:** {out['action']}")
            st.markdown("**Müşteriye taslak mesaj:**")
            st.code(out["draft_message"], language=None)
            st.caption(f"Üretim modu: {'LLM' if out['mode'] == 'llm' else 'şablon (LLM anahtarı tanımlı değil)'}")
        if llm_enabled() and st.button("🧠 Notları LLM ile özetle"):
            with st.spinner("Okunuyor…"):
                st.json(llm_signals(r.notes_text))

# ------------------------------------------------------------------ page 3
elif page == "Model kartı":
    st.title("Model kartı")
    o, b, a = metrics["overall"], metrics["before_offer_stage"], metrics["after_offer_stage"]
    st.markdown(f"""
**Görev:** açık bir lead'in satışla kapanma olasılığı. **Model:** gradient boosted trees (scikit-learn HistGradientBoosting), 42 özellik.
**Eğitim verisi:** kapanmış lead'lerin yaşam süresi içinden rastgele anlarda alınmış *snapshot*'ları — her özellik o an bilinebilecek olaylardan hesaplanır
(leakage yok: sonucu yazan son not ve kapanış sonrası alanlar dışarıda). **Doğrulama:** zamansal ayrım, {metrics['split_date']} öncesi eğitim, sonrası test.
""")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AUC (genel)", f"{o['auc']:.3f}")
    c2.metric("AUC (teklif öncesi)", f"{b['auc']:.3f}")
    c3.metric("Lift @ top %10", f"{o['lift_top10pct']:.1f}×")
    c4.metric("Top %10 isabet", f"%{o['precision_top10pct']*100:.0f}", f"taban %{o['base_rate']*100:.0f}")
    st.caption(f"Test seti: {o['n']} snapshot ({b['n']} teklif öncesi, {a['n']} teklif sonrası). "
               "Teklif öncesi AUC'nin yüksek olması önemli: model asıl orada işe yarıyor, teklif geldikten sonra zaten herkes lead'in sıcak olduğunu biliyor.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Özellik önemi (permutation, test seti)")
        st.bar_chart(importance.head(12).set_index("feature")["importance"])
    with col2:
        st.subheader("Kalibrasyon (ondalık dilimler)")
        st.line_chart(calibration.set_index("decile")[["pred", "actual"]])
        st.caption("Tahmin edilen ve gerçekleşen oranlar dilim dilim yakın → skor bir olasılık gibi davranıyor.")
    st.subheader("Bilinen sınırlar")
    st.markdown("""
- Sentetik veri: gerçek CRM'de not kalitesi çok daha değişken olur; kural tabanlı sinyaller yerine LLM çıkarımı gerekebilir.
- Danışman ve bayi etkisi modelde var; bu, düşük performanslı bayilerin lead'lerini "cezalandırır". Üretimde bu özellikler ayrı raporlanmalı, sıralamada nötrlenebilir.
- Açıklamalar SHAP değil, tek-özellik ablasyonu; etkileşimleri kaçırabilir.
- Yeniden eğitim: aylık, Fabric pipeline'ında Gold'dan sonra çalışan bir notebook adımı olarak.
""")

# ------------------------------------------------------------------ page 4
elif page == "Veri hattı":
    st.title("Veri hattı: Bronze → Silver → Gold → model")
    st.markdown("""
| Katman | Ne var | Bu ürün ne okuyor |
|---|---|---|
| **Bronze** | CRM CSV, web JSON, bayi DMS (`;`, ondalık virgül, dd.MM.yyyy) olduğu gibi Delta'ya | — |
| **Silver** | Tipler, format birleştirme, müşteri tekilleştirme (golden record), FK kontrolleri, `dq_results` | — |
| **Gold** | Yıldız şema: `fact_leads` (huni pre-joined), `fact_interactions`, `dim_*`, `lead_notes` | **hepsi** |
| **Model** | `gold.lead_scores` — açık lead skorları, bant, gerekçe | app bunu gösterir |

Semantic model / Power BI raporu da aynı Gold tablolarını Direct Lake ile okur. Yani rapor ve asistan aynı sayılara bakar.
""")
    st.subheader("Silver'ın düzelttikleri (dq_results)")
    show = dq[["table_name", "check_name", "severity", "action", "failed_rows", "total_rows", "failed_pct"]].sort_values(["severity", "failed_rows"], ascending=[True, False])
    st.dataframe(show, width="stretch", hide_index=True)
