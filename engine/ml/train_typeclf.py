"""Train the column-type classifier on SYNTHETIC data (never real data).

We generate many small, deliberately-varied columns for each type — including
messy ones with a share of junk/blank values — extract shape features, and train
a small classifier. Crucially, numeric/date columns are generated *with* a chunk
of worded junk ("Do not know", "N/A", "ditto") so the model learns to still call
them numeric/date instead of giving up — the exact failure seen on real files.

Run:  python -m engine.ml.train_typeclf   ->  writes engine/ml/typeclf.joblib
"""
from __future__ import annotations

import random
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier

from .features import column_features

random.seed(1864)

JUNK = ["", "N/A", "na", "unknown", "Do not know", "ditto", "-", "?", "nil", "none", "tbd"]
FIRST = ["Ada", "Musa", "Ngozi", "Ibrahim", "Chidi", "Aisha", "Tunde", "Amina", "Emeka", "Fatima"]
LAST = ["Okafor", "Bello", "Sani", "Adeyemi", "Mohammed", "Nwosu", "Idris", "Obi", "Eze", "Okon"]
CITY = ["Lagos", "Kano", "Ibadan", "Abuja", "Enugu", "Kaduna", "Jos", "Warri", "Owerri", "Benue"]
CATS = ["Maize", "Rice", "Sorghum", "Cassava", "Yam", "Basic", "Premium", "Savings", "Current",
        "Retail", "Wholesale", "Trading", "Farming", "Services", "Manufacturing"]


def _maybe_junk(gen, junk_rate):
    return random.choice(JUNK) if random.random() < junk_rate else gen()


def _col(kind: str, n: int, junk_rate: float) -> list[str]:
    def num(): return str(random.choice([random.randint(1, 99), round(random.uniform(1, 5000), 2)]))
    def date(): return random.choice([f"{random.randint(1,28)}/{random.randint(1,12)}/{random.randint(1970,2020)}",
                                       f"{random.randint(1970,2020)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"])
    def phone(): return random.choice(["080", "070", "090"]) + "".join(random.choice("0123456789") for _ in range(8))
    def email(): return random.choice(FIRST).lower() + "@" + random.choice(["mail.com", "x.io", "gov.ng"])
    def ident(): return random.choice(["ENR", "STU", "CR", "HH"]) + str(random.randint(10000, 999999))
    def name(): return random.choice(FIRST) + " " + random.choice(LAST)
    def geo(): return random.choice(CITY)
    def cat(): return random.choice(CATS)
    def boolean(): return random.choice(["Yes", "No", "yes", "no", "Y", "N"])
    def gender(): return random.choice(["M", "F", "Male", "Female", "male", "female"])
    def text(): return " ".join(random.choice(FIRST + LAST + CITY + ["road", "market", "opposite", "near"]) for _ in range(random.randint(3, 7)))
    def indicator(): return random.choice(["0", "1"])
    def datetime(): return random.choice([
        f"{random.randint(2015,2022)}-{random.randint(1,12):02d}-{random.randint(1,28):02d} {random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}",
        f"{random.randint(1,28)}/{random.randint(1,12)}/{random.randint(2015,2022)} {random.randint(1,12)}:{random.randint(0,59):02d}"])
    gens = {"numeric": num, "date": date, "phone": phone, "email": email, "identifier": ident,
            "name": name, "geo": geo, "categorical": cat, "boolean": boolean, "gender": gender,
            "free_text": text, "indicator": indicator, "datetime": datetime}
    g = gens[kind]
    return [_maybe_junk(g, junk_rate) for _ in range(n)]


def build_dataset():
    X, y = [], []
    kinds = ["numeric", "date", "datetime", "phone", "email", "identifier", "name", "geo",
             "categorical", "boolean", "gender", "free_text", "indicator"]
    for kind in kinds:
        for _ in range(120):                       # many columns per type
            n = random.randint(15, 60)
            jr = 0.0 if kind == "indicator" else random.choice([0.0, 0.05, 0.15, 0.3, 0.45])
            X.append(column_features(_col(kind, n, jr)))
            y.append(kind)
    return X, y


def main():
    X, y = build_dataset()
    clf = RandomForestClassifier(n_estimators=200, max_depth=None, random_state=1864, n_jobs=-1)
    clf.fit(X, y)
    out = Path(__file__).resolve().parent / "typeclf.joblib"
    joblib.dump(clf, out)
    print(f"trained on {len(X)} synthetic columns across {len(set(y))} types -> {out}")
    # quick self-check on the exact failure case: numbers polluted with 'Do not know'
    from .predict import predict_type
    age = ["34", "41", "29", "Do not know", "52", "N/A", "38", "45", "unknown", "27", "33", "61"]
    print("age-with-junk ->", predict_type(age, clf))


if __name__ == "__main__":
    main()
