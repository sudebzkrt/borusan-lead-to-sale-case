"""
Synthetic source-system extracts for the Borusan Otomotiv case study.

Produces raw files that mimic three source systems plus master data:

  data/raw/master/dealers.csv, vehicles.csv          -- reference / master data (clean)
  data/raw/crm/crm_customers.csv                      -- CRM export, comma CSV, ISO dates
  data/raw/crm/crm_leads.csv                          -- CRM leads (all sources except web)
  data/raw/crm/crm_interactions.csv                   -- CRM activity log with free-text notes
  data/raw/web/web_leads.json                         -- website lead form, nested JSON
  data/raw/dms/dms_test_drives.csv                    -- dealer DMS export: ';' separator, decimal comma, dd.MM.yyyy
  data/raw/dms/dms_offers.csv
  data/raw/dms/dms_sales.csv
  docs/dq_injections.md                               -- what was deliberately broken, with counts

The funnel has real causal structure (source quality, test drive, response time,
discount, price, dealer) so a lead-scoring model has signal to learn.
Data-quality defects are injected on purpose and logged so the Silver layer has
concrete work to do and the DQ checks can be verified against ground truth.

Usage: python data_gen/generate.py [--out data/raw] [--seed 42] [--scale 1.0]
"""
import argparse
import json
import os
import random
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
START = datetime(2024, 9, 1)
END = datetime(2026, 8, 31)
DAYS = (END - START).days

FIRST_NAMES_M = ["Ahmet", "Mehmet", "Mustafa", "Ali", "Hüseyin", "Hasan", "İbrahim", "Emre", "Burak", "Murat",
                 "Kerem", "Can", "Cem", "Onur", "Serkan", "Tolga", "Umut", "Barış", "Efe", "Arda", "Yusuf",
                 "Eren", "Kaan", "Berk", "Deniz", "Selim", "Oğuz", "Furkan", "Halil", "Ömer"]
FIRST_NAMES_F = ["Ayşe", "Fatma", "Zeynep", "Elif", "Merve", "Selin", "Ece", "Büşra", "Esra", "Gizem",
                 "Sude", "Nur", "Hande", "Melis", "Pınar", "Derya", "Ceren", "İrem", "Yasemin", "Aslı",
                 "Gamze", "Dilara", "Beyza", "Naz", "Ebru", "Tuğba", "Seda", "Nazlı", "Cansu", "Damla"]
LAST_NAMES = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın", "Özdemir",
              "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan", "Şimşek",
              "Polat", "Korkmaz", "Çakır", "Erdoğan", "Bozkurt", "Taş", "Aksoy", "Güneş", "Acar", "Turan",
              "Ünal", "Bulut", "Keskin", "Yalçın", "Sarı", "Ateş", "Tekin", "Karaca", "Uzun", "Avcı"]
COMPANIES = ["Lojistik", "İnşaat", "Teknoloji", "Gıda", "Tekstil", "Enerji", "Turizm", "Otomotiv Yan Sanayi",
             "Danışmanlık", "Sağlık", "Medya", "Yazılım"]
COMPANY_PREFIX = ["Anadolu", "Marmara", "Ege", "Boğaziçi", "Akdeniz", "Kuzey", "Yıldız", "Global", "Delta", "Nova",
                  "Atlas", "Meridyen", "Zirve", "Ufuk"]

CITIES = {  # city -> weight
    "İstanbul": 45, "Ankara": 14, "İzmir": 9, "Bursa": 6, "Antalya": 5, "Kocaeli": 4, "Adana": 3,
    "Gaziantep": 2, "Samsun": 2, "Eskişehir": 2, "Denizli": 2, "Konya": 2, "Mersin": 2, "Muğla": 2,
}

DEALERS = [
    # dealer_id, name, city, region, type
    ("D001", "Borusan Oto İstinye", "İstanbul", "Marmara", "own_retail"),
    ("D002", "Borusan Oto Avcılar", "İstanbul", "Marmara", "own_retail"),
    ("D003", "Borusan Oto Çekmeköy", "İstanbul", "Marmara", "own_retail"),
    ("D004", "Borusan Oto Kartal", "İstanbul", "Marmara", "own_retail"),
    ("D005", "Borusan Oto Ankara Çankaya", "Ankara", "İç Anadolu", "own_retail"),
    ("D006", "Borusan Oto Ankara Esenboğa", "Ankara", "İç Anadolu", "own_retail"),
    ("D007", "Borusan Oto İzmir", "İzmir", "Ege", "own_retail"),
    ("D008", "Borusan Oto Bursa", "Bursa", "Marmara", "own_retail"),
    ("D009", "Borusan Oto Antalya", "Antalya", "Akdeniz", "own_retail"),
    ("D010", "Borusan Oto Kocaeli", "Kocaeli", "Marmara", "own_retail"),
    ("D011", "Adana Yetkili Bayi", "Adana", "Akdeniz", "authorized_dealer"),
    ("D012", "Gaziantep Yetkili Bayi", "Gaziantep", "Güneydoğu", "authorized_dealer"),
    ("D013", "Samsun Yetkili Bayi", "Samsun", "Karadeniz", "authorized_dealer"),
    ("D014", "Eskişehir Yetkili Bayi", "Eskişehir", "İç Anadolu", "authorized_dealer"),
]
# hidden dealer quality effect on conversion (logit)
DEALER_EFFECT = {"D001": 0.35, "D002": 0.10, "D003": 0.20, "D004": -0.10, "D005": 0.25, "D006": -0.20,
                 "D007": 0.15, "D008": 0.05, "D009": 0.00, "D010": -0.05, "D011": -0.30, "D012": -0.40,
                 "D013": -0.25, "D014": -0.15}

# brand, model, trim, body, fuel, segment, list_price_try (illustrative 2026 prices)
VEHICLES = [
    ("BMW", "1 Serisi", "118i M Sport", "Hatchback", "Petrol", "Compact", 3_450_000),
    ("BMW", "2 Serisi Gran Coupe", "218i M Sport", "Sedan", "Petrol", "Compact", 3_900_000),
    ("BMW", "3 Serisi", "320i M Sport", "Sedan", "Petrol", "Premium Mid", 4_650_000),
    ("BMW", "3 Serisi", "320d xDrive M Sport", "Sedan", "Diesel", "Premium Mid", 5_100_000),
    ("BMW", "5 Serisi", "520i M Sport", "Sedan", "Petrol", "Executive", 6_900_000),
    ("BMW", "5 Serisi", "530e xDrive", "Sedan", "PHEV", "Executive", 7_800_000),
    ("BMW", "7 Serisi", "740d xDrive", "Sedan", "Diesel", "Luxury", 14_500_000),
    ("BMW", "X1", "sDrive18i M Sport", "SUV", "Petrol", "Compact SUV", 4_200_000),
    ("BMW", "X1", "xDrive25e M Sport", "SUV", "PHEV", "Compact SUV", 4_900_000),
    ("BMW", "X2", "sDrive20i M Sport", "SUV", "Petrol", "Compact SUV", 4_600_000),
    ("BMW", "X3", "xDrive20d M Sport", "SUV", "Diesel", "Mid SUV", 6_400_000),
    ("BMW", "X3", "xDrive30e M Sport", "SUV", "PHEV", "Mid SUV", 7_100_000),
    ("BMW", "X5", "xDrive30d M Sport", "SUV", "Diesel", "Large SUV", 11_200_000),
    ("BMW", "X5", "xDrive50e M Sport", "SUV", "PHEV", "Large SUV", 12_300_000),
    ("BMW", "X7", "xDrive40d M Sport", "SUV", "Diesel", "Luxury SUV", 16_800_000),
    ("BMW", "i4", "eDrive40 M Sport", "Gran Coupe", "Electric", "Premium Mid", 5_300_000),
    ("BMW", "iX1", "eDrive20 M Sport", "SUV", "Electric", "Compact SUV", 4_100_000),
    ("BMW", "iX1", "xDrive30 M Sport", "SUV", "Electric", "Compact SUV", 4_700_000),
    ("BMW", "iX2", "eDrive20 M Sport", "SUV", "Electric", "Compact SUV", 4_500_000),
    ("BMW", "iX3", "50 xDrive", "SUV", "Electric", "Mid SUV", 6_600_000),
    ("BMW", "i5", "eDrive40 M Sport", "Sedan", "Electric", "Executive", 7_400_000),
    ("BMW", "iX", "xDrive45", "SUV", "Electric", "Large SUV", 9_800_000),
    ("BMW", "i7", "xDrive60", "Sedan", "Electric", "Luxury", 15_900_000),
    ("MINI", "Cooper", "C Classic", "Hatchback", "Petrol", "Premium Small", 2_650_000),
    ("MINI", "Cooper", "S Favoured", "Hatchback", "Petrol", "Premium Small", 3_050_000),
    ("MINI", "Cooper", "E Classic", "Hatchback", "Electric", "Premium Small", 2_900_000),
    ("MINI", "Countryman", "C Favoured", "SUV", "Petrol", "Compact SUV", 3_700_000),
    ("MINI", "Countryman", "E Favoured", "SUV", "Electric", "Compact SUV", 4_000_000),
    ("MINI", "Aceman", "E Favoured", "Crossover", "Electric", "Premium Small", 3_300_000),
    ("Land Rover", "Defender", "110 D250 SE", "SUV", "Diesel", "Large SUV", 11_900_000),
    ("Land Rover", "Defender", "90 P300 X-Dynamic", "SUV", "Petrol", "Large SUV", 10_800_000),
    ("Land Rover", "Discovery Sport", "D200 Dynamic SE", "SUV", "Diesel", "Mid SUV", 6_200_000),
    ("Land Rover", "Range Rover Evoque", "P160 Dynamic SE", "SUV", "Petrol", "Compact SUV", 5_400_000),
    ("Land Rover", "Range Rover Evoque", "P300e Dynamic HSE", "SUV", "PHEV", "Compact SUV", 6_100_000),
    ("Land Rover", "Range Rover Velar", "D200 Dynamic SE", "SUV", "Diesel", "Mid SUV", 7_900_000),
    ("Land Rover", "Range Rover Sport", "D300 Dynamic SE", "SUV", "Diesel", "Large SUV", 14_200_000),
    ("Land Rover", "Range Rover Sport", "P460e Autobiography", "SUV", "PHEV", "Large SUV", 17_500_000),
    ("Land Rover", "Range Rover", "D350 Autobiography", "SUV", "Diesel", "Luxury SUV", 22_000_000),
]

LEAD_SOURCES = {  # source -> (share, base logit)
    "web_form": (0.34, -1.9),
    "showroom_walkin": (0.20, -0.6),
    "call_center": (0.14, -1.4),
    "campaign": (0.12, -2.1),
    "social_media": (0.10, -2.3),
    "referral": (0.06, -0.3),
    "existing_customer": (0.04, -0.2),
}
CAMPAIGNS = ["Bahar Fırsatları 2025", "Yaz Kampanyası 2025", "Elektrikli Geleceğe Geçiş", "Yıl Sonu Fırsatları 2025",
             "Bahar Fırsatları 2026", "Yaz Kampanyası 2026", "MINI Şehir Günleri", "Defender Deneyim Günleri"]

ADVISORS_PER_DEALER = 4

STATUS_FLOW = ["new", "contacted", "qualified", "test_drive", "offer", "won", "lost"]

LOST_REASONS = ["price", "bought_competitor", "no_response", "financing_rejected", "timing", "stock_unavailable",
                "chose_other_model"]

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def rand_date(rng, start=START, end=END):
    return start + timedelta(seconds=int(rng.integers(0, int((end - start).total_seconds()))))


def phone_clean(rng):
    return f"+905{rng.integers(30, 60):02d}{rng.integers(1000000, 9999999):07d}"


def phone_variant(p, rng):
    d = "".join(ch for ch in p if ch.isdigit())[-10:]  # 5xxxxxxxxx, robust to already-formatted input
    forms = [
        f"0{d}",
        f"0{d[:3]} {d[3:6]} {d[6:8]} {d[8:]}",
        f"+90 {d[:3]} {d[3:6]} {d[6:]}",
        f"{d}",
        f"0 ({d[:3]}) {d[3:6]}-{d[6:]}",
    ]
    return forms[rng.integers(0, len(forms))]


def slug(s):
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return s.translate(tr).lower().replace(" ", "")


def business_time(rng, dt, allow_any=False):
    """Snap a timestamp into 09:00-19:00 on a working day (Mon-Sat). allow_any keeps ~30% as-is (web/social)."""
    if dt is None:
        return None
    if allow_any and rng.random() < 0.3:
        return dt
    if dt.weekday() == 6:
        dt = dt + timedelta(days=1)
    hour = int(np.clip(rng.normal(14, 2.5), 9, 18))
    return dt.replace(hour=hour, minute=int(rng.integers(0, 60)), second=int(rng.integers(0, 60)))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def month_seasonality(dt):
    # Turkish market: strong Q4 (year-end pricing), weak Jan/Feb, small summer dip
    m = dt.month
    return {1: -0.25, 2: -0.2, 3: 0.05, 4: 0.1, 5: 0.1, 6: 0.0, 7: -0.1, 8: -0.15, 9: 0.05, 10: 0.15, 11: 0.25,
            12: 0.35}[m]


# ----------------------------------------------------------------------------
# generation
# ----------------------------------------------------------------------------
def generate(out, seed=42, scale=1.0):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    dq = Counter()

    os.makedirs(out, exist_ok=True)
    for sub in ["master", "crm", "web", "dms"]:
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    # ---------------- master data ----------------
    dealers = pd.DataFrame(DEALERS, columns=["dealer_id", "dealer_name", "city", "region", "dealer_type"])
    dealers["opened_year"] = rng.integers(2005, 2022, size=len(dealers))
    dealers["is_active"] = True

    vehicles = pd.DataFrame(VEHICLES, columns=["brand", "model", "trim", "body_type", "fuel_type", "segment",
                                               "list_price_try"])
    vehicles.insert(0, "vehicle_id", [f"V{i+1:03d}" for i in range(len(vehicles))])
    vehicles["model_year"] = 2026
    # popularity weight for lead interest: cheaper + SUV + electric slightly more
    pop = np.log(30_000_000 / vehicles["list_price_try"]) + np.where(vehicles["body_type"] == "SUV", 0.4, 0) \
        + np.where(vehicles["fuel_type"] == "Electric", 0.15, 0)
    veh_w = np.exp(pop) / np.exp(pop).sum()

    advisors = []
    for d in dealers["dealer_id"]:
        for k in range(ADVISORS_PER_DEALER):
            fn = random.choice(FIRST_NAMES_M + FIRST_NAMES_F)
            ln = random.choice(LAST_NAMES)
            advisors.append({"advisor_id": f"A{d[1:]}{k+1}", "advisor_name": f"{fn} {ln}", "dealer_id": d,
                             "hidden_skill": float(rng.normal(0, 0.25))})
    advisors = pd.DataFrame(advisors)
    adv_by_dealer = {d: g for d, g in advisors.groupby("dealer_id")}

    # ---------------- customers ----------------
    n_cust = int(6000 * scale)
    cities = list(CITIES.keys())
    city_w = np.array(list(CITIES.values()), dtype=float)
    city_w /= city_w.sum()
    cust_rows = []
    for i in range(n_cust):
        cid = f"C{i+1:06d}"
        is_corp = rng.random() < 0.15
        if is_corp:
            name = f"{random.choice(COMPANY_PREFIX)} {random.choice(COMPANIES)} A.Ş." if rng.random() < 0.6 \
                else f"{random.choice(COMPANY_PREFIX)} {random.choice(COMPANIES)} Ltd. Şti."
            gender, birth = None, None
            email_local = slug(name.split(" A.Ş.")[0].split(" Ltd.")[0]) + "@" + slug(name.split()[0]) + ".com.tr"
        else:
            gender = "F" if rng.random() < 0.38 else "M"
            fn = random.choice(FIRST_NAMES_F if gender == "F" else FIRST_NAMES_M)
            ln = random.choice(LAST_NAMES)
            name = f"{fn} {ln}"
            age = int(np.clip(rng.normal(42, 11), 23, 75))
            birth = (datetime(2026, 1, 1) - timedelta(days=age * 365 + int(rng.integers(0, 364)))).date()
            dom = random.choice(["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com"])
            email_local = f"{slug(fn)}.{slug(ln)}{rng.integers(1, 99) if rng.random() < 0.5 else ''}@{dom}"
        city = cities[rng.choice(len(cities), p=city_w)]
        created = rand_date(rng, START - timedelta(days=365), END)
        cust_rows.append({
            "customer_id": cid,
            "full_name": name,
            "customer_type": "corporate" if is_corp else "individual",
            "gender": gender,
            "birth_date": birth.isoformat() if birth else None,
            "email": email_local,
            "phone": phone_clean(rng),
            "city": city,
            "kvkk_consent": bool(rng.random() < 0.93),
            "marketing_consent": bool(rng.random() < 0.55),
            "created_at": created.strftime("%Y-%m-%dT%H:%M:%S"),
            "updated_at": (created + timedelta(days=int(rng.integers(0, 200)))).strftime("%Y-%m-%dT%H:%M:%S"),
            "_hidden_affluence": float(rng.normal(0, 1)),
        })
    customers = pd.DataFrame(cust_rows)

    # ---------------- leads ----------------
    n_leads = int(15000 * scale)
    src_names = list(LEAD_SOURCES.keys())
    src_w = np.array([LEAD_SOURCES[s][0] for s in src_names])
    # customers with multiple leads (repeat shoppers)
    cust_lead_w = np.exp(rng.normal(0, 0.6, size=n_cust))
    cust_lead_w /= cust_lead_w.sum()

    lead_rows, td_rows, offer_rows, sale_rows, inter_rows = [], [], [], [], []
    lead_counter = td_counter = offer_counter = sale_counter = inter_counter = 0

    for i in range(n_leads):
        lead_counter += 1
        lead_id = f"L{lead_counter:07d}"
        ci = int(rng.choice(n_cust, p=cust_lead_w))
        cust = customers.iloc[ci]
        created = rand_date(rng)
        # don't create a lead before the customer exists (mostly)
        c_created = datetime.strptime(cust["created_at"], "%Y-%m-%dT%H:%M:%S")
        if created < c_created:
            created = c_created + timedelta(days=int(rng.integers(0, 30)))
            if created > END:
                created = END - timedelta(days=int(rng.integers(1, 20)))
        source = src_names[rng.choice(len(src_names), p=src_w)]
        # dealer: mostly same city, else nearest big city
        same_city = dealers[dealers["city"] == cust["city"]]
        if len(same_city) and rng.random() < 0.85:
            dealer_id = same_city.sample(1, random_state=int(rng.integers(0, 1e9))).iloc[0]["dealer_id"]
        else:
            dealer_id = dealers.sample(1, random_state=int(rng.integers(0, 1e9))).iloc[0]["dealer_id"]
        adv = adv_by_dealer[dealer_id].sample(1, random_state=int(rng.integers(0, 1e9))).iloc[0]
        vi = int(rng.choice(len(vehicles), p=veh_w))
        veh = vehicles.iloc[vi]
        campaign = random.choice(CAMPAIGNS) if source == "campaign" else None
        first_resp_h = float(np.clip(rng.lognormal(1.6, 0.9), 0.1, 240))  # median ~5h, tail to 10 days
        if source == "showroom_walkin":
            first_resp_h = float(np.clip(rng.lognormal(-1.0, 0.5), 0.05, 4))
        price_z = (np.log(veh["list_price_try"]) - np.log(6_000_000)) / 0.6

        # --- latent conversion propensity ---
        logit = LEAD_SOURCES[source][1]
        logit += DEALER_EFFECT[dealer_id] + adv["hidden_skill"]
        logit += -0.35 * price_z + 0.45 * cust["_hidden_affluence"] * 0.5
        logit += 0.3 if cust["customer_type"] == "corporate" else 0
        logit += -0.012 * min(first_resp_h, 72)  # slow response hurts
        logit += month_seasonality(created)
        # test drive decision (itself driven by intent)
        p_td = sigmoid(logit + 0.8)
        did_td = rng.random() < p_td
        logit += 0.9 if did_td else 0
        # offer stage
        p_offer = sigmoid(logit + 0.9)
        did_offer = rng.random() < p_offer
        discount_pct = None
        financing = None
        if did_offer:
            discount_pct = float(np.clip(rng.normal(4.5, 2.5), 0, 12))
            financing = bool(rng.random() < 0.45)
            logit += 0.08 * discount_pct + (0.25 if financing else 0)
        p_won = sigmoid(logit - 0.6) if did_offer else 0.0
        won = rng.random() < p_won

        # timeline
        created = business_time(rng, created, allow_any=source in ("web_form", "social_media", "campaign"))
        t_contact = created + timedelta(hours=first_resp_h)
        if source != "showroom_walkin":
            t_contact = max(business_time(rng, t_contact), created + timedelta(minutes=5))
        first_resp_h = (t_contact - created).total_seconds() / 3600
        t_td = business_time(rng, t_contact + timedelta(days=float(rng.gamma(2, 2.5)))) if did_td else None
        t_offer = business_time(rng, (t_td or t_contact) + timedelta(days=float(rng.gamma(2, 2.0)))) if did_offer else None
        t_close = None
        if won:
            t_close = t_offer + timedelta(days=float(rng.gamma(2, 4.0)))
        elif did_offer:
            t_close = t_offer + timedelta(days=float(rng.gamma(2, 7.0)))
        elif rng.random() < 0.85:
            t_close = (t_td or t_contact) + timedelta(days=float(rng.gamma(2, 10.0)))
        t_close = business_time(rng, t_close)
        # cap at END: anything closing after END is still open
        still_open = t_close is not None and t_close > END
        if t_close is None or still_open:
            status = "offer" if did_offer and (t_offer or END) <= END else ("test_drive" if did_td and (t_td or END) <= END
                                                                          else ("contacted" if t_contact <= END else "new"))
            won = False
            lost_reason = None
            t_close = None
        else:
            status = "won" if won else "lost"
            lost_reason = None if won else random.choice(LOST_REASONS)

        lead_rows.append({
            "lead_id": lead_id, "customer_id": cust["customer_id"], "dealer_id": dealer_id,
            "advisor_id": adv["advisor_id"], "vehicle_id": veh["vehicle_id"], "source": source,
            "campaign_name": campaign, "created_at": created, "first_contact_at": t_contact if t_contact <= END else None,
            "first_response_hours": round(first_resp_h, 2), "status": status, "lost_reason": lost_reason,
            "closed_at": t_close, "budget_try": int(veh["list_price_try"] * float(rng.uniform(0.75, 1.15)) // 10000 * 10000)
            if rng.random() < 0.6 else None,
            "trade_in": bool(rng.random() < 0.3),
        })

        # test drive
        if did_td and t_td <= END:
            td_counter += 1
            td_rows.append({
                "test_drive_id": f"TD{td_counter:06d}", "lead_id": lead_id, "dealer_id": dealer_id,
                "vehicle_id": veh["vehicle_id"], "scheduled_at": t_td,
                "completed": bool(rng.random() < 0.9),
                "duration_min": int(np.clip(rng.normal(35, 10), 10, 90)),
                "satisfaction_score": int(np.clip(round(rng.normal(4.1 + (0.4 if won else 0), 0.8)), 1, 5)),
                "advisor_id": adv["advisor_id"],
            })
        # offer
        if did_offer and t_offer <= END:
            offer_counter += 1
            lp = int(veh["list_price_try"])
            final = int(lp * (1 - discount_pct / 100) // 1000 * 1000)
            offer_status = "accepted" if won else ("rejected" if status == "lost" else ("expired" if rng.random() < 0.3 else "open"))
            offer_rows.append({
                "offer_id": f"O{offer_counter:06d}", "lead_id": lead_id, "vehicle_id": veh["vehicle_id"],
                "dealer_id": dealer_id, "offer_date": t_offer, "list_price_try": lp,
                "discount_pct": round(discount_pct, 2), "final_price_try": final,
                "financing": financing, "valid_until": t_offer + timedelta(days=14),
                "offer_status": offer_status,
            })
        # sale
        if won:
            sale_counter += 1
            sale_rows.append({
                "sale_id": f"S{sale_counter:06d}", "lead_id": lead_id, "customer_id": cust["customer_id"],
                "dealer_id": dealer_id, "vehicle_id": veh["vehicle_id"], "advisor_id": adv["advisor_id"],
                "sale_date": t_close, "delivery_date": t_close + timedelta(days=int(rng.integers(3, 45))),
                "final_price_try": int(veh["list_price_try"] * (1 - discount_pct / 100) // 1000 * 1000),
                "payment_type": "financing" if financing else random.choice(["cash", "cash", "bank_transfer"]),
                "trade_in_value_try": int(rng.uniform(0.15, 0.5) * veh["list_price_try"] // 10000 * 10000)
                if lead_rows[-1]["trade_in"] and rng.random() < 0.8 else None,
                "vin": "WBA" + "".join(random.choices("ABCDEFGHJKLMNPRSTUVWXYZ0123456789", k=14)),
            })

        # interactions (2-7 per lead, with free-text notes)
        n_int = int(rng.integers(2, 8)) if status not in ("new",) else 1
        times = sorted([created + (min(t_close or END, END) - created) * float(rng.random()) for _ in range(n_int)])
        times = [business_time(rng, t) for t in times]
        times[0] = t_contact if t_contact <= END else created
        times = sorted(times)
        for k, ts in enumerate(times):
            inter_counter += 1
            channel = random.choices(["phone", "whatsapp", "email", "showroom_visit", "sms"],
                                     weights=[35, 30, 15, 15, 5])[0]
            direction = "outbound" if k == 0 or rng.random() < 0.6 else "inbound"
            inter_rows.append({
                "interaction_id": f"I{inter_counter:07d}", "lead_id": lead_id, "customer_id": cust["customer_id"],
                "advisor_id": adv["advisor_id"], "channel": channel, "direction": direction,
                "interaction_at": ts, "duration_sec": int(rng.integers(30, 900)) if channel in ("phone", "showroom_visit") else None,
                "notes": make_note(rng, k, n_int, status, veh, did_td, did_offer, discount_pct, lost_reason, channel),
            })

    leads = pd.DataFrame(lead_rows).astype({"budget_try": "Int64"})
    test_drives = pd.DataFrame(td_rows).astype({"duration_min": "Int64"})
    offers = pd.DataFrame(offer_rows).astype({"final_price_try": "Int64"})
    sales = pd.DataFrame(sale_rows).astype({"trade_in_value_try": "Int64"})
    interactions = pd.DataFrame(inter_rows).astype({"duration_sec": "Int64"})

    # ---------------- DQ injections (documented) ----------------
    # customers: duplicates with format variations
    n_dup = int(len(customers) * 0.03)
    dup_src = customers.sample(n_dup, random_state=seed)
    dups = dup_src.copy()
    dups["customer_id"] = [f"C{n_cust + j + 1:06d}" for j in range(n_dup)]
    dups["phone"] = [phone_variant(p, rng) for p in dups["phone"]]
    dups["full_name"] = [n.upper() if rng.random() < 0.4 else (n.lower() if rng.random() < 0.3 else n) for n in dups["full_name"]]
    dups["email"] = [e.upper() if rng.random() < 0.5 else e for e in dups["email"]]
    dups["created_at"] = [(datetime.strptime(c, "%Y-%m-%dT%H:%M:%S") + timedelta(days=int(rng.integers(1, 400)))).strftime("%Y-%m-%dT%H:%M:%S") for c in dups["created_at"]]
    customers = pd.concat([customers, dups], ignore_index=True)
    dq["customers.duplicate_records"] = n_dup
    # some leads/sales were logged against the duplicate record instead of the original (that is how duplicates
    # happen in real CRMs: a second advisor re-creates the customer and works the new lead under the new id)
    dup_map = dict(zip(dup_src["customer_id"], dups["customer_id"]))
    repoint = leads["customer_id"].isin(dup_map) & (rng.random(len(leads)) < 0.5)
    leads.loc[repoint, "customer_id"] = leads.loc[repoint, "customer_id"].map(dup_map)
    sales.loc[sales["lead_id"].isin(leads.loc[repoint, "lead_id"]), "customer_id"] = \
        sales.loc[sales["lead_id"].isin(leads.loc[repoint, "lead_id"]), "lead_id"].map(leads.set_index("lead_id")["customer_id"])
    dq["leads.customer_id_points_to_duplicate"] = int(repoint.sum())
    # phone format variants on originals too
    idx = customers.sample(frac=0.12, random_state=seed + 1).index
    customers.loc[idx, "phone"] = [phone_variant(p, rng) for p in customers.loc[idx, "phone"]]
    dq["customers.phone_format_variants"] = len(idx)
    # city spelling variants
    city_var = {"İstanbul": ["Istanbul", "ISTANBUL", "istanbul", "İstanbul "], "İzmir": ["Izmir", "IZMIR"],
                "Ankara": ["ANKARA", "ankara"], "Eskişehir": ["Eskisehir"]}
    idx = customers.sample(frac=0.08, random_state=seed + 2).index
    cnt = 0
    for i in idx:
        c = customers.at[i, "city"]
        if c in city_var:
            customers.at[i, "city"] = random.choice(city_var[c])
            cnt += 1
    dq["customers.city_spelling_variants"] = cnt
    # missing email
    idx = customers.sample(frac=0.02, random_state=seed + 3).index
    customers.loc[idx, "email"] = None
    dq["customers.missing_email"] = len(idx)
    # invalid email
    idx = customers.sample(frac=0.01, random_state=seed + 4).index
    customers.loc[idx, "email"] = [e.replace("@", " at ") if e else "n/a" for e in customers.loc[idx, "email"]]
    dq["customers.invalid_email"] = len(idx)
    customers = customers.drop(columns=["_hidden_affluence"])

    # leads: orphan dealer, missing vehicle, status casing, orphan customer, negative response hours
    idx = leads.sample(frac=0.008, random_state=seed + 5).index
    leads.loc[idx, "dealer_id"] = [random.choice(["D099", "D0O1", "", "D15"]) for _ in idx]
    dq["leads.orphan_or_malformed_dealer_id"] = len(idx)
    idx = leads.sample(frac=0.015, random_state=seed + 6).index
    leads.loc[idx, "vehicle_id"] = None
    dq["leads.missing_vehicle_id"] = len(idx)
    idx = leads.sample(frac=0.05, random_state=seed + 7).index
    leads.loc[idx, "status"] = [s.upper() if rng.random() < 0.5 else s.title() for s in leads.loc[idx, "status"]]
    dq["leads.status_casing_variants"] = len(idx)
    idx = leads.sample(frac=0.004, random_state=seed + 8).index
    leads.loc[idx, "customer_id"] = [f"C9{rng.integers(0, 99999):05d}" for _ in idx]
    dq["leads.orphan_customer_id"] = len(idx)
    idx = leads.sample(frac=0.003, random_state=seed + 9).index
    leads.loc[idx, "first_response_hours"] = -1.0
    dq["leads.negative_response_hours"] = len(idx)
    # exact duplicate lead rows (CRM re-export)
    dup_leads = leads.sample(frac=0.005, random_state=seed + 10)
    dq["leads.exact_duplicate_rows"] = len(dup_leads)

    # offers: impossible discounts, missing final price, decimal comma will come from DMS format
    idx = offers.sample(frac=0.006, random_state=seed + 11).index
    offers.loc[idx, "discount_pct"] = [random.choice([150.0, -5.0, 99.0]) for _ in idx]
    dq["offers.impossible_discount_pct"] = len(idx)
    idx = offers.sample(frac=0.01, random_state=seed + 12).index
    offers.loc[idx, "final_price_try"] = None
    dq["offers.missing_final_price"] = len(idx)

    # sales: duplicates, sale before lead created, orphan lead
    dup_sales = sales.sample(frac=0.01, random_state=seed + 13)
    dq["sales.exact_duplicate_rows"] = len(dup_sales)
    idx = sales.sample(frac=0.005, random_state=seed + 14).index
    sales.loc[idx, "sale_date"] = sales.loc[idx, "sale_date"] - timedelta(days=400)
    dq["sales.sale_date_before_lead_created"] = len(idx)
    idx = sales.sample(frac=0.004, random_state=seed + 15).index
    sales.loc[idx, "lead_id"] = [f"L9{rng.integers(0, 999999):06d}" for _ in idx]
    dq["sales.orphan_lead_id"] = len(idx)

    # test drives: missing duration, satisfaction out of range
    idx = test_drives.sample(frac=0.03, random_state=seed + 16).index
    test_drives.loc[idx, "duration_min"] = None
    dq["test_drives.missing_duration"] = len(idx)
    idx = test_drives.sample(frac=0.004, random_state=seed + 17).index
    test_drives.loc[idx, "satisfaction_score"] = [random.choice([0, 6, 10]) for _ in idx]
    dq["test_drives.satisfaction_out_of_range"] = len(idx)

    # interactions: orphan leads, mixed timestamp formats, empty notes
    idx = interactions.sample(frac=0.003, random_state=seed + 18).index
    interactions.loc[idx, "lead_id"] = [f"L8{rng.integers(0, 999999):06d}" for _ in idx]
    dq["interactions.orphan_lead_id"] = len(idx)
    idx = interactions.sample(frac=0.02, random_state=seed + 19).index
    interactions.loc[idx, "notes"] = None
    dq["interactions.empty_notes"] = len(idx)

    # late-arriving: a slice of sales rows are duplicated with a later updated timestamp (simulate CDC)
    # (kept simple: handled via duplicates above)

    # ---------------- write: CRM (comma CSV, ISO timestamps) ----------------
    crm_dir = os.path.join(out, "crm")
    customers.to_csv(os.path.join(crm_dir, "crm_customers.csv"), index=False)

    web_mask = leads["source"] == "web_form"
    crm_leads = pd.concat([leads[~web_mask], dup_leads[dup_leads["source"] != "web_form"]], ignore_index=True)
    crm_leads = crm_leads.sample(frac=1, random_state=seed).reset_index(drop=True)
    for c in ["created_at", "first_contact_at", "closed_at"]:
        crm_leads[c] = pd.to_datetime(crm_leads[c]).dt.strftime("%Y-%m-%dT%H:%M:%S")
    # mixed timestamp format injection in CRM leads (a few rows exported by an older CRM version)
    idx = crm_leads.sample(frac=0.01, random_state=seed + 20).index
    crm_leads.loc[idx, "created_at"] = pd.to_datetime(crm_leads.loc[idx, "created_at"]).dt.strftime("%d/%m/%Y %H:%M")
    dq["crm_leads.mixed_timestamp_format"] = len(idx)
    crm_leads.to_csv(os.path.join(crm_dir, "crm_leads.csv"), index=False)

    inter_out = interactions.copy()
    inter_out["interaction_at"] = pd.to_datetime(inter_out["interaction_at"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
    idx = inter_out.sample(frac=0.01, random_state=seed + 21).index
    inter_out.loc[idx, "interaction_at"] = pd.to_datetime(inter_out.loc[idx, "interaction_at"]).dt.strftime("%d.%m.%Y %H:%M:%S")
    dq["crm_interactions.mixed_timestamp_format"] = len(idx)
    inter_out.to_csv(os.path.join(crm_dir, "crm_interactions.csv"), index=False)

    # ---------------- write: web leads (nested JSON) ----------------
    web = pd.concat([leads[web_mask], dup_leads[dup_leads["source"] == "web_form"]], ignore_index=True)
    web_records = []
    for _, r in web.iterrows():
        rec = {
            "leadId": r["lead_id"],
            "submittedAt": pd.Timestamp(r["created_at"]).strftime("%Y-%m-%dT%H:%M:%S+03:00"),
            "form": {"type": "contact_request", "campaign": r["campaign_name"] if pd.notna(r["campaign_name"]) else None,
                     "utm": {"source": random.choice(["google", "meta", "direct", "newsletter"]),
                             "medium": random.choice(["cpc", "organic", "email", "social"])}},
            "customer": {"customerId": r["customer_id"]},
            "interest": {"vehicleId": r["vehicle_id"] if pd.notna(r["vehicle_id"]) else None,
                         "preferredDealerId": r["dealer_id"], "budget": int(r["budget_try"]) if pd.notna(r["budget_try"]) else None,
                         "tradeIn": bool(r["trade_in"])},
            "crm": {"assignedAdvisorId": r["advisor_id"], "status": r["status"], "lostReason": r["lost_reason"] if pd.notna(r["lost_reason"]) else None,
                    "firstContactAt": pd.Timestamp(r["first_contact_at"]).strftime("%Y-%m-%dT%H:%M:%S+03:00") if pd.notna(r["first_contact_at"]) else None,
                    "firstResponseHours": r["first_response_hours"],
                    "closedAt": pd.Timestamp(r["closed_at"]).strftime("%Y-%m-%dT%H:%M:%S+03:00") if pd.notna(r["closed_at"]) else None},
        }
        web_records.append(rec)
    with open(os.path.join(out, "web", "web_leads.json"), "w", encoding="utf-8") as f:
        json.dump({"export": {"system": "borusan-web-forms", "exportedAt": END.strftime("%Y-%m-%dT%H:%M:%S+03:00"),
                              "recordCount": len(web_records)}, "leads": web_records}, f, ensure_ascii=False, indent=1)

    # ---------------- write: DMS (Turkish locale: ';' sep, decimal comma, dd.MM.yyyy) ----------------
    dms_dir = os.path.join(out, "dms")

    def to_dms(df, datecols, dtcols=()):
        d = df.copy()
        for c in datecols:
            d[c] = pd.to_datetime(d[c]).dt.strftime("%d.%m.%Y")
        for c in dtcols:
            d[c] = pd.to_datetime(d[c]).dt.strftime("%d.%m.%Y %H:%M")
        return d

    td_out = to_dms(test_drives, [], ["scheduled_at"])
    td_out.columns = ["TESTSURUS_ID", "LEAD_ID", "BAYI_KODU", "ARAC_KODU", "PLANLANAN_TARIH", "TAMAMLANDI",
                      "SURE_DK", "MEMNUNIYET_PUANI", "DANISMAN_ID"]
    td_out["TAMAMLANDI"] = td_out["TAMAMLANDI"].map({True: "E", False: "H"})
    td_out.to_csv(os.path.join(dms_dir, "dms_test_drives.csv"), index=False, sep=";", encoding="utf-8-sig")

    of_out = to_dms(offers, ["offer_date", "valid_until"])
    of_out.columns = ["TEKLIF_NO", "LEAD_ID", "ARAC_KODU", "BAYI_KODU", "TEKLIF_TARIHI", "LISTE_FIYATI",
                      "ISKONTO_ORANI", "NET_FIYAT", "FINANSMAN", "GECERLILIK_TARIHI", "TEKLIF_DURUMU"]
    of_out["FINANSMAN"] = of_out["FINANSMAN"].map({True: "E", False: "H"})
    of_out.to_csv(os.path.join(dms_dir, "dms_offers.csv"), index=False, sep=";", decimal=",", encoding="utf-8-sig")

    sa_out = pd.concat([sales, dup_sales], ignore_index=True).sample(frac=1, random_state=seed).reset_index(drop=True)
    sa_out = to_dms(sa_out, ["sale_date", "delivery_date"])
    sa_out.columns = ["SATIS_NO", "LEAD_ID", "MUSTERI_ID", "BAYI_KODU", "ARAC_KODU", "DANISMAN_ID", "SATIS_TARIHI",
                      "TESLIMAT_TARIHI", "NET_FIYAT", "ODEME_TIPI", "TAKAS_DEGERI", "SASE_NO"]
    sa_out.to_csv(os.path.join(dms_dir, "dms_sales.csv"), index=False, sep=";", decimal=",", encoding="utf-8-sig")

    # ---------------- write: master ----------------
    dealers.to_csv(os.path.join(out, "master", "dealers.csv"), index=False)
    vehicles.to_csv(os.path.join(out, "master", "vehicles.csv"), index=False)
    advisors.drop(columns=["hidden_skill"]).to_csv(os.path.join(out, "master", "advisors.csv"), index=False)

    # ---------------- DQ log ----------------
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "dq_injections.md"), "w", encoding="utf-8") as f:
        f.write("# Deliberate data-quality defects in the raw extracts\n\n")
        f.write(f"Generated with seed={seed}, scale={scale}. Counts are ground truth for validating Silver-layer DQ checks.\n\n")
        f.write("| Defect | Rows |\n|---|---|\n")
        for k, v in sorted(dq.items()):
            f.write(f"| `{k}` | {v} |\n")
        f.write("\n## Format-level defects (whole file)\n\n")
        f.write("- DMS extracts use `;` separator, decimal comma, `dd.MM.yyyy` dates, Turkish column names, `E/H` booleans, UTF-8 BOM.\n")
        f.write("- Web leads are nested JSON with camelCase keys and `+03:00` timestamps; CRM uses ISO without offset.\n")
        f.write("- Web-sourced leads exist only in `web_leads.json`; all other sources only in `crm_leads.csv` (Bronze must union).\n")
        f.write("- `advisors.csv` is master data but leads reference advisors that always exist; dealers referenced by leads may not.\n")

    # summary
    won = (leads["status"].str.lower() == "won").sum()
    print(f"customers {len(customers)} | leads {len(leads)} (+{len(dup_leads)} dup) | test_drives {len(test_drives)} | "
          f"offers {len(offers)} | sales {len(sales)} (+{len(dup_sales)} dup) | interactions {len(interactions)}")
    print(f"won rate: {won / len(leads):.1%}   lost: {(leads['status'].str.lower() == 'lost').mean():.1%}   "
          f"open: {(~leads['status'].str.lower().isin(['won', 'lost'])).mean():.1%}")
    print("conversion by source:")
    print(leads.assign(w=leads["status"].str.lower() == "won").groupby("source")["w"].mean().round(3).to_string())
    return dq


# ----------------------------------------------------------------------------
# free-text notes (Turkish, advisor style) -- raw material for the AI product
# ----------------------------------------------------------------------------
def make_note(rng, k, n, status, veh, did_td, did_offer, discount, lost_reason, channel):
    model = f"{veh['brand']} {veh['model']}"
    trim = veh["trim"]
    first = [
        f"Müşteri {model} ile ilgileniyor, {trim} donanımı soruldu. Fiyat bilgisi verildi, düşünecek.",
        f"{model} için bilgi talebi. Stok durumu ve teslim süresi soruldu. Katalog paylaşıldı.",
        f"İlk temas. Müşteri {model} ve rakip modelleri karşılaştırıyor, en geç ay sonuna karar verecek.",
        f"Ulaşıldı. {model} için showroom randevusu teklif edildi, uygun günü bildirecek.",
        f"Cevap yok, sesli mesaj bırakıldı. {model} ilgisi web formundan.",
        f"Müşteri aradı, {model} {trim} için kampanya var mı diye sordu. Güncel liste paylaşıldı.",
        f"Mevcut aracını takasa vermek istiyor, {model} için değerleme talep etti.",
    ]
    mid = [
        f"Test sürüşü sonrası görüşüldü, araçtan memnun kaldı. Renk ve donanım netleşti." if did_td else
        f"Test sürüşü için tekrar arandı, bu hafta zamanı yok. Haftaya tekrar aranacak.",
        f"Teklif iletildi, %{discount:.0f} iskonto ile. Müşteri eşiyle değerlendirecek." if did_offer and discount else
        f"Fiyat konusunda tereddütlü. Finansman seçenekleri anlatıldı, hesaplama gönderilecek.",
        f"Finansman için evrak listesi gönderildi. 48 ay vade seçeneğini soruyor.",
        f"Müşteri geri dönüş yaptı, {trim} yerine daha üst donanımı düşünüyor. Yeni fiyat çalışılacak.",
        f"Whatsapp üzerinden görsel ve fiyat listesi paylaşıldı. Okundu, cevap bekleniyor.",
        f"Müşteri acele etmiyor, yıl sonu kampanyalarını beklemek istiyor.",
        f"Şirket aracı olarak alınacak, kurumsal filo fiyatı talep edildi. Filo ekibiyle görüşülecek.",
        f"Stokta istediği renk yok, 6-8 hafta teslim süresi söylendi. Alternatif renk önerildi.",
        f"Müşteri teklifi rakip bayi ile karşılaştırıyor, daha iyi fiyat bekliyor.",
        f"Randevu iptal edildi, iş seyahati. Ayın 15'inden sonra tekrar aranacak.",
    ]
    last_won = [
        f"Sözleşme imzalandı, kapora alındı. Teslimat planlandı. {model} {trim}.",
        f"Müşteri teklifi kabul etti, ödeme planı onaylandı. Plaka ve sigorta işlemleri başlatıldı.",
        f"Satış tamamlandı. Müşteri memnun, referans olabileceğini söyledi.",
    ]
    last_lost = {
        "price": [f"Fiyatı yüksek buldu, bütçesini aşıyor. Şimdilik vazgeçti.",
                  f"İstenen iskonto verilemedi, müşteri kapattı."],
        "bought_competitor": [f"Rakip markadan araç almış, konuyu kapattık.",
                              f"Başka bayiden daha iyi teklif almış, oradan aldı."],
        "no_response": [f"3 kez arandı, ulaşılamadı. Kayıt kapatıldı.", f"Mesajlara dönüş yapmıyor, kapatıldı."],
        "financing_rejected": [f"Kredi onayı çıkmadı, alım ertelendi."],
        "timing": [f"Alımı ileri bir tarihe erteledi, 6 ay sonra tekrar aranacak."],
        "stock_unavailable": [f"İstediği donanım/renk için teslim süresi uzun, beklemek istemedi."],
        "chose_other_model": [f"Farklı bir segmente yöneldi, ihtiyaç değişti."],
    }
    if k == 0:
        return random.choice(first)
    if k == n - 1 and status == "won":
        return random.choice(last_won)
    if k == n - 1 and status == "lost" and lost_reason:
        return random.choice(last_lost[lost_reason])
    note = random.choice(mid)
    if channel == "showroom_visit" and rng.random() < 0.5:
        note = "Showroom ziyareti. " + note
    return note


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    generate(a.out, a.seed, a.scale)
