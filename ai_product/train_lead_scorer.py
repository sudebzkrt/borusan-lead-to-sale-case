# %% [markdown]
# # Lead scorer — train, evaluate, score open leads
#
# **Problem.** An advisor at a busy Istanbul branch has 40–80 open leads. Today they work them in the order the CRM
# shows them. This model ranks open leads by the probability of ending in a sale and explains each score, so the
# advisor's first three calls of the day are the right three.
#
# **Data.** Gold only: `fact_leads`, `fact_interactions`, `fact_test_drives`, `fact_offers`, `dim_vehicle`, `dim_dealer`.
# The AI product is a *consumer* of the Medallion architecture — nothing here touches Bronze or Silver.
#
# **Point-in-time correctness (the part interviewers care about).** A closed lead's final state is not a valid
# training example: "has_offer = 1" for every won lead is not insight, it is the answer written on the exam.
# Instead, each closed lead contributes **snapshots** — the lead as it looked at random moments between creation
# and closing — with every feature computed from events *before* that moment (test drive done yet? offer sent yet?
# how many interactions so far? what did the notes say so far?). Open leads are scored as a snapshot at the
# dataset's end date, with exactly the same feature code. The interaction that records the outcome
# ("Sözleşme imzalandı", "Rakip markadan aldı") is removed from closed leads altogether.
#
# **Validation.** Temporal split: train on leads created before `SPLIT_DATE`, test on later closed leads.
# Metrics are reported overall and for the hard case — snapshots with no offer yet — because that is where a
# ranking actually changes what the advisor does.
#
# Runs in Fabric (writes `gold.lead_scores`) or locally (`data/gold/lead_scores/`). ~1 minute on a laptop.

# %%
import os, sys, json, glob, pickle
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.inspection import permutation_importance

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, HERE)
from signals import rule_signals, SIGNAL_NAMES  # noqa: E402

try:
    import notebookutils  # noqa: F401
    IS_FABRIC = True
except ImportError:
    IS_FABRIC = False

REPO = os.environ.get("REPO_ROOT", os.path.dirname(HERE))
GOLD_DIR = os.path.join(REPO, "data", "gold")
MODEL_DIR = os.path.join(HERE, "model")
os.makedirs(MODEL_DIR, exist_ok=True)
SPLIT_DATE = pd.Timestamp("2026-03-01")
SNAPSHOTS_PER_CLOSED_LEAD = 2
RANDOM_STATE = 42
rng = np.random.default_rng(RANDOM_STATE)


def read_gold(name):
    if IS_FABRIC:
        return spark.table(f"gold.{name}").toPandas()  # noqa: F821 (spark exists in Fabric)
    files = glob.glob(os.path.join(GOLD_DIR, name, "*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def write_gold(df, name):
    if IS_FABRIC:
        (spark.createDataFrame(df).write.format("delta").mode("overwrite")  # noqa: F821
              .option("overwriteSchema", "true").saveAsTable(f"gold.{name}"))
    out = os.path.join(GOLD_DIR, name)
    os.makedirs(out, exist_ok=True)
    df.to_parquet(os.path.join(out, "part-0.parquet"), index=False)


# %% [markdown]
# ## 1. Load Gold and build the snapshot frame

# %%
leads = read_gold("fact_leads")
inter = read_gold("fact_interactions")
tds = read_gold("fact_test_drives")
offers = read_gold("fact_offers")
vehicles = read_gold("dim_vehicle")
dealers = read_gold("dim_dealer")
for c in ["created_at", "first_contact_at", "closed_at"]:
    leads[c] = pd.to_datetime(leads[c])
inter["interaction_at"] = pd.to_datetime(inter["interaction_at"])
tds["scheduled_at"] = pd.to_datetime(tds["scheduled_at"])
offers["offer_date"] = pd.to_datetime(offers["offer_date"])
DATA_END = leads["created_at"].max().normalize() + pd.Timedelta(days=1)
leads["is_closed"] = ~leads["is_open"]
print(f"leads {len(leads)}  interactions {len(inter)}  DATA_END {DATA_END.date()}")

# Remove the outcome-recording interaction (the last one) from closed leads — it literally states the result.
inter = inter.sort_values(["lead_id", "interaction_at"])
last_idx = inter.groupby("lead_id")["interaction_at"].idxmax()
closed_ids = set(leads.loc[leads["is_closed"], "lead_id"])
drop_idx = last_idx[last_idx.index.isin(closed_ids)]
inter = inter.drop(drop_idx.values)
print(f"dropped {len(drop_idx)} outcome notes from closed leads")

# Snapshots: closed leads -> random moments inside their lifetime; open leads -> DATA_END
closed = leads[leads["is_closed"]].copy()
life = (closed["closed_at"] - closed["created_at"]).dt.total_seconds().clip(lower=3600)
snap_rows = []
for k in range(SNAPSHOTS_PER_CLOSED_LEAD):
    u = rng.uniform(0.02, 0.98, size=len(closed))
    snap_rows.append(pd.DataFrame({"lead_id": closed["lead_id"].values,
                                   "snapshot_at": closed["created_at"].values + pd.to_timedelta(u * life.values, unit="s"),
                                   "is_open_snapshot": False}))
open_leads = leads[leads["is_open"]]
snap_rows.append(pd.DataFrame({"lead_id": open_leads["lead_id"].values, "snapshot_at": DATA_END, "is_open_snapshot": True}))
snaps = pd.concat(snap_rows, ignore_index=True)
snaps["snapshot_at"] = pd.to_datetime(snaps["snapshot_at"])
print(f"snapshots: {len(snaps)}  (closed {(~snaps['is_open_snapshot']).sum()}, open {snaps['is_open_snapshot'].sum()})")

# %% [markdown]
# ## 2. Features as of the snapshot time
#
# Every event-derived feature is computed with a `<= snapshot_at` filter. Static attributes (source, dealer,
# vehicle, budget) are known at creation and are safe as they are.

# %%
static_cols = ["lead_id", "customer_id", "dealer_id", "advisor_id", "vehicle_id", "source", "utm_source", "created_at",
               "first_contact_at", "first_response_hours", "budget_try", "trade_in", "is_won", "is_closed"]
X = snaps.merge(leads[static_cols], on="lead_id", how="left")
X = (X.merge(vehicles[["vehicle_id", "brand", "segment", "fuel_type", "list_price_try"]], on="vehicle_id", how="left")
      .merge(dealers[["dealer_id", "dealer_type", "region"]], on="dealer_id", how="left"))
X["lead_age_days"] = (X["snapshot_at"] - X["created_at"]).dt.total_seconds() / 86400
X["contacted"] = (X["first_contact_at"] <= X["snapshot_at"]).astype(float)
X["response_hours_capped"] = np.where(X["contacted"] == 1, X["first_response_hours"].clip(upper=120), np.nan)
X["created_month"] = X["created_at"].dt.month
X["created_dow"] = X["created_at"].dt.dayofweek
X["log_list_price"] = np.log(X["list_price_try"].fillna(X["list_price_try"].median()))
X["budget_gap_pct"] = (X["budget_try"] - X["list_price_try"]) / X["list_price_try"] * 100
X["trade_in"] = X["trade_in"].astype(float)

# test drives before snapshot
td_join = snaps[["lead_id", "snapshot_at"]].merge(tds[["lead_id", "scheduled_at", "satisfaction_score", "completed"]], on="lead_id")
td_join = td_join[td_join["scheduled_at"] <= td_join["snapshot_at"]]
td_feat = td_join.groupby(["lead_id", "snapshot_at"]).agg(has_test_drive=("scheduled_at", "size"),
                                                          test_drive_satisfaction=("satisfaction_score", "max"),
                                                          first_td_at=("scheduled_at", "min")).reset_index()
X = X.merge(td_feat, on=["lead_id", "snapshot_at"], how="left")
X["has_test_drive"] = (X["has_test_drive"].fillna(0) > 0).astype(float)
X["days_to_test_drive"] = (X["first_td_at"] - X["created_at"]).dt.total_seconds() / 86400

# offers before snapshot (offer_date is a date -> compare with snapshot date)
of_join = snaps[["lead_id", "snapshot_at"]].merge(offers[["lead_id", "offer_date", "discount_pct", "financing", "final_price_try"]], on="lead_id")
of_join = of_join[of_join["offer_date"] <= of_join["snapshot_at"].dt.normalize()]
of_feat = (of_join.sort_values("offer_date").groupby(["lead_id", "snapshot_at"])
                  .agg(has_offer=("offer_date", "size"), offer_discount_pct=("discount_pct", "last"),
                       offer_financing=("financing", "last"), offer_final_price_try=("final_price_try", "last"),
                       first_offer_date=("offer_date", "min")).reset_index())
X = X.merge(of_feat, on=["lead_id", "snapshot_at"], how="left")
X["has_offer"] = (X["has_offer"].fillna(0) > 0).astype(float)
X["offer_financing"] = X["offer_financing"].map({True: 1.0, False: 0.0})
X["days_to_offer"] = (X["first_offer_date"] - X["created_at"].dt.normalize()).dt.days

# interactions before snapshot (+ notes so far)
in_join = snaps[["lead_id", "snapshot_at"]].merge(inter[["lead_id", "interaction_at", "direction", "channel", "notes"]], on="lead_id")
in_join = in_join[in_join["interaction_at"] <= in_join["snapshot_at"]].sort_values("interaction_at")
in_join["is_in"] = (in_join["direction"] == "inbound").astype(int)
in_join["is_show"] = (in_join["channel"] == "showroom_visit").astype(int)
in_join["is_wa"] = (in_join["channel"] == "whatsapp").astype(int)
in_join["line"] = in_join["interaction_at"].dt.strftime("%Y-%m-%d") + " [" + in_join["channel"] + "] " + in_join["notes"].fillna("")
in_feat = (in_join.groupby(["lead_id", "snapshot_at"])
                  .agg(n_interactions=("interaction_at", "size"), inbound_count=("is_in", "sum"),
                       showroom_visits=("is_show", "sum"), whatsapp_count=("is_wa", "sum"),
                       last_interaction_at=("interaction_at", "max"), notes_text=("line", "\n".join)).reset_index())
X = X.merge(in_feat, on=["lead_id", "snapshot_at"], how="left")
for c in ["n_interactions", "inbound_count", "showroom_visits", "whatsapp_count"]:
    X[c] = X[c].fillna(0).astype(float)
X["days_since_last_interaction"] = (X["snapshot_at"] - X["last_interaction_at"]).dt.total_seconds() / 86400
X["notes_text"] = X["notes_text"].fillna("")
sig = pd.DataFrame([rule_signals(t) for t in X["notes_text"]], index=X.index)
X = pd.concat([X, sig], axis=1)

CAT = ["source", "dealer_id", "advisor_id", "brand", "segment", "fuel_type", "dealer_type", "region", "utm_source"]
NUM = ["lead_age_days", "contacted", "response_hours_capped", "log_list_price", "budget_gap_pct", "trade_in",
       "created_month", "created_dow", "has_test_drive", "test_drive_satisfaction", "days_to_test_drive",
       "has_offer", "offer_discount_pct", "offer_financing", "days_to_offer",
       "n_interactions", "inbound_count", "showroom_visits", "whatsapp_count", "days_since_last_interaction"] + SIGNAL_NAMES + ["signal_count"]
FEATURES = CAT + NUM
for c in CAT:
    X[c] = X[c].astype("category")
for c in NUM:
    X[c] = pd.to_numeric(X[c], errors="coerce").astype(float)
y = X["is_won"].astype(int)
print(f"feature matrix {X.shape[0]} x {len(FEATURES)}")

# %% [markdown]
# ## 3. Temporal validation

# %%
train_mask = (~X["is_open_snapshot"]) & (X["created_at"] < SPLIT_DATE)
test_mask = (~X["is_open_snapshot"]) & (X["created_at"] >= SPLIT_DATE)
print(f"train {train_mask.sum()}  test {test_mask.sum()}  won rate train {y[train_mask].mean():.3f} / test {y[test_mask].mean():.3f}")

def make_model():
    return HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=500, max_leaf_nodes=15, min_samples_leaf=50, l2_regularization=1.0,
        early_stopping=True, validation_fraction=0.15, categorical_features="from_dtype", random_state=RANDOM_STATE)

m = make_model().fit(X.loc[train_mask, FEATURES], y[train_mask])
p_test = m.predict_proba(X.loc[test_mask, FEATURES])[:, 1]
y_test = y[test_mask].values

def lift_at(p, y, frac):
    k = max(1, int(len(p) * frac))
    return y[np.argsort(-p)[:k]].mean() / y.mean()

def block(p, y):
    return {"n": int(len(y)), "base_rate": float(y.mean()), "auc": float(roc_auc_score(y, p)),
            "pr_auc": float(average_precision_score(y, p)), "brier": float(brier_score_loss(y, p)),
            "lift_top10pct": float(lift_at(p, y, 0.10)), "lift_top20pct": float(lift_at(p, y, 0.20)),
            "precision_top10pct": float(y[np.argsort(-p)[:max(1, len(p)//10)]].mean())}

no_offer = (X.loc[test_mask, "has_offer"] == 0).values
metrics = {"split_date": str(SPLIT_DATE.date()), "n_train": int(train_mask.sum()),
           "overall": block(p_test, y_test),
           "before_offer_stage": block(p_test[no_offer], y_test[no_offer]),
           "after_offer_stage": block(p_test[~no_offer], y_test[~no_offer])}
print(json.dumps(metrics, indent=2))

# %% [markdown]
# ### Which features matter (permutation importance on the test set)

# %%
pi = permutation_importance(m, X.loc[test_mask, FEATURES], y_test, scoring="roc_auc", n_repeats=5, random_state=RANDOM_STATE, n_jobs=-1)
importance = (pd.DataFrame({"feature": FEATURES, "importance": pi.importances_mean, "std": pi.importances_std})
                .sort_values("importance", ascending=False).reset_index(drop=True))
print(importance.head(15).to_string(index=False))

# %% [markdown]
# ### Calibration by decile — a 0.30 score should convert about 30% of the time

# %%
cal = pd.DataFrame({"p": p_test, "y": y_test})
cal["decile"] = pd.qcut(cal["p"].rank(method="first"), 10, labels=False) + 1
calibration = cal.groupby("decile").agg(pred=("p", "mean"), actual=("y", "mean"), n=("y", "size")).reset_index()
print(calibration.round(3).to_string(index=False))

# %% [markdown]
# ## 4. Refit on all closed snapshots, score the open pipeline

# %%
fit_mask = ~X["is_open_snapshot"]
final = make_model().fit(X.loc[fit_mask, FEATURES], y[fit_mask])
open_df = X[X["is_open_snapshot"]].copy()
open_df["score"] = final.predict_proba(open_df[FEATURES])[:, 1]

# %% [markdown]
# ### Per-lead explanations (feature ablation)
#
# For each open lead and each feature: replace the value with the population baseline (median / mode of closed
# snapshots), re-score, record the change. The biggest absolute changes are the lead's "reasons". Simple, faithful
# to this exact model, readable by a sales manager. SHAP is the upgrade; this is the two-day version.

# %%
baseline = {c: (X.loc[fit_mask, c].mode().iloc[0] if c in CAT else float(X.loc[fit_mask, c].median())) for c in FEATURES}

LABELS = {  # feature: (detail template, text when it lowers the score, text when it raises it) — Turkish, shown to advisors
    "response_hours_capped": ("ilk yanıt {v:.0f} sa", "ilk yanıt geç verildi", "ilk yanıt hızlı verildi"),
    "contacted": ("temas", "henüz temas kurulmadı", "temas kuruldu"),
    "lead_age_days": ("{v:.0f} günlük", "lead eskiyor", "taze lead"),
    "has_test_drive": ("test sürüşü", "test sürüşü yapılmadı", "test sürüşü yapıldı"),
    "test_drive_satisfaction": ("memnuniyet {v:.0f}/5", "test sürüşü memnuniyeti düşük", "test sürüşü memnuniyeti yüksek"),
    "days_to_test_drive": ("{v:.0f}. günde test sürüşü", "test sürüşü geç yapıldı", "test sürüşü hızlı yapıldı"),
    "has_offer": ("teklif", "henüz teklif verilmedi", "teklif masada"),
    "offer_discount_pct": ("iskonto %{v:.1f}", "iskonto olağandan düşük", "iskonto olağandan yüksek"),
    "offer_financing": ("finansman", "teklifte finansman yok", "teklifte finansman var"),
    "log_list_price": ("araç fiyatı", "yüksek fiyatlı model", "erişilebilir fiyat"),
    "budget_gap_pct": ("bütçe farkı %{v:.0f}", "bütçe liste fiyatının altında", "bütçe liste fiyatını karşılıyor"),
    "source": ("kaynak {v}", "düşük dönüşümlü kaynak", "yüksek dönüşümlü kaynak"),
    "dealer_id": ("bayi {v}", "bayi ağ ortalamasının altında", "bayi ağ ortalamasının üstünde"),
    "advisor_id": ("danışman {v}", "danışman ortalamanın altında", "danışman ortalamanın üstünde"),
    "n_interactions": ("{v:.0f} etkileşim", "etkileşim az", "etkileşim yoğun"),
    "inbound_count": ("{v:.0f} gelen temas", "müşteri kendisi aramıyor", "müşteri kendisi temas kuruyor"),
    "showroom_visits": ("{v:.0f} showroom ziyareti", "showroom'a gelmedi", "showroom'a geldi"),
    "days_since_last_interaction": ("son temas {v:.0f} gün önce", "temas soğudu", "temas yakın zamanda"),
    "went_quiet": ("sessizlik", "müşteri sessizleşti", "müşteri yanıt veriyor"),
    "price_objection": ("fiyat itirazı", "notlarda fiyat itirazı var", "fiyat itirazı yok"),
    "buying_signal": ("alım sinyali", "alım sinyali yok", "notlarda alım sinyali var"),
    "delay_signal": ("erteleme", "müşteri erteliyor", "erteleme yok"),
    "financing_interest": ("finansman ilgisi", "finansman ilgisi yok", "finansman ilgisi var"),
    "corporate_fleet": ("filo", "filo alımı değil", "kurumsal/filo alımı"),
    "stock_issue": ("stok", "stok/renk sorunu var", "stok sorunu yok"),
    "competitor": ("rakip", "rakiple kıyaslıyor", "rakip devrede değil"),
    "trade_in": ("takas", "takas yok", "takas var"),
    "spouse_decision": ("ortak karar", "kararı eşiyle/ailesiyle verecek", "tek karar verici"),
}
X_open = open_df[FEATURES].copy()
base_score = open_df["score"].values
contrib = pd.DataFrame(index=open_df.index)
for c in FEATURES:
    X_alt = X_open.copy()
    X_alt[c] = baseline[c]
    if c in CAT:
        X_alt[c] = X_alt[c].astype(X_open[c].dtype)
    contrib[c] = base_score - final.predict_proba(X_alt)[:, 1]   # + : the lead's actual value raises the score

def reasons_for(idx, k=3):
    row = contrib.loc[idx].dropna()
    row = row[row.abs() > 0.005].sort_values(key=np.abs, ascending=False).head(k)
    out = []
    for feat, eff in row.items():
        tpl, bad, good = LABELS.get(feat, (feat, feat, feat))
        v = open_df.at[idx, feat]
        try:
            detail = tpl.format(v=v)
        except Exception:
            detail = str(v)
        out.append((feat, round(float(eff), 3), f"{good if eff > 0 else bad} ({detail}, {eff*100:+.0f} pts)"))
    return out

open_df["reasons"] = [json.dumps(reasons_for(i), ensure_ascii=False) for i in open_df.index]
open_df["score_band"] = pd.cut(open_df["score"], [-0.001, 0.10, 0.25, 0.45, 1.0], labels=["D", "C", "B", "A"]).astype(str)
open_df["rank_in_dealer"] = open_df.groupby("dealer_id", observed=True)["score"].rank(ascending=False, method="first").astype(int)
open_df["scored_at"] = datetime.now(timezone.utc)

lead_scores = open_df[["lead_id", "dealer_id", "advisor_id", "score", "score_band", "rank_in_dealer", "reasons",
                       "lead_age_days", "days_since_last_interaction", "n_interactions", "has_test_drive", "has_offer",
                       "buying_signal", "price_objection", "went_quiet", "delay_signal", "financing_interest",
                       "stock_issue", "competitor", "notes_text", "scored_at"]].copy()
for c in ["dealer_id", "advisor_id"]:
    lead_scores[c] = lead_scores[c].astype(str)
write_gold(lead_scores, "lead_scores")
print(f"scored {len(lead_scores)} open leads; bands: {lead_scores['score_band'].value_counts().to_dict()}")

# %% [markdown]
# ## 5. Persist artefacts for the app

# %%
with open(os.path.join(MODEL_DIR, "lead_scorer.pkl"), "wb") as f:
    pickle.dump({"model": final, "features": FEATURES, "cat": CAT, "baseline": baseline}, f)
json.dump(metrics, open(os.path.join(MODEL_DIR, "metrics.json"), "w"), indent=2)
importance.to_csv(os.path.join(MODEL_DIR, "feature_importance.csv"), index=False)
calibration.to_csv(os.path.join(MODEL_DIR, "calibration.csv"), index=False)
print("artefacts written to", MODEL_DIR)
