"""Generate small, SYNTHETIC, deliberately messy sample files — one per sector.

Nothing here is real data. Each file is built to contain the kinds of mess the
engine exists to fix (mixed phone/date formats, inconsistent spellings, ALL-CAPS
names, currency symbols) so you can see example inputs for each sector.

Run:  python samples/make_sector_samples.py   -> writes samples/data/*.csv
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

random.seed(1864)
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)

FIRST = ["ADA", "fatima", "Musa", "ngozi", "IBRAHIM", "chidi", "Aisha", "tunde", "amina", "Emeka"]
LAST = ["okafor", "BELLO", "Sani", "OYEBANJO", "mohammed", "adeyemi", "USMAN", "nwosu", "idris", "obi"]
STATES = ["Lagos", "lagos", "Kastina", "Kaduna", "ABUJA", "Port Harcourt", "Ibadan", "Rivers", "kano", "Benue"]
YESNO = ["Yes", "no", "YES", "No", "y", "n"]


def nin():
    return "".join(random.choice("0123456789") for _ in range(random.choice([11, 11, 11, 10])))


def phone():
    body = random.choice(["803", "806", "701", "905"]) + "".join(random.choice("0123456789") for _ in range(7))
    return random.choice([lambda b: "0" + b, lambda b: b, lambda b: "+234" + b,
                          lambda b: "0" + b[:3] + " " + b[3:6] + " " + b[6:]])(body)


def dob():
    y, m, d = random.randint(1960, 2005), random.randint(1, 12), random.randint(1, 28)
    return random.choice([f"{d}/{m}/{y}", f"{d}/{m}/{str(y)[2:]}", f"{y}-{m:02d}-{d:02d}", f"{d:02d}-{m:02d}-{y}"])


def money():
    return random.choice(["$1,200.50", "N45,000", "30000", "12,500.75", "N/A"])


def messy_cat(options):
    v = random.choice(options)
    return random.choice([v, v.upper(), v.lower(), v + " "])


SECTORS = {
    "health": lambda: {
        "Enrollee No": "ENR" + str(random.randint(100000, 999999)),
        "NIN": nin(), "First Name": random.choice(FIRST), "Surname": random.choice(LAST),
        "Sex": random.choice(["M", "F", "male", "FEMALE"]), "DOB": dob(), "Ph No": phone(),
        "State of Residence": random.choice(STATES),
        "Blood Group": messy_cat(["A+", "O+", "B+", "AB+", "O-"]),
        "Plan": messy_cat(["basic", "premium", "premuim", "family"]),
        "Premium": money(), "Payment Made": random.choice(YESNO),
    },
    "agriculture": lambda: {
        "FarmerID": "FRM" + str(random.randint(100000, 999999)),
        "BVN": nin(), "Full Name": random.choice(FIRST) + " " + random.choice(LAST),
        "GSM": phone(), "State": random.choice(STATES),
        "Crop": messy_cat(["Maize", "maize", "Maiz", "Rice", "sorghum", "Sorgum", "Cassava"]),
        "Farm Size (Ha)": str(round(random.uniform(0.5, 12), 2)),
        "Inputs Redeemed": random.choice(YESNO),
        "Registration Date": dob(), "Bank": messy_cat(["GTB", "gtbank", "Access", "First Bank", "UBA"]),
    },
    "education": lambda: {
        "Student ID": "STU" + str(random.randint(100000, 999999)),
        "NIN": nin(), "First Name": random.choice(FIRST), "Surname": random.choice(LAST),
        "Sex": random.choice(["M", "F", "male", "FEMALE"]), "DOB": dob(),
        "State of Origin": random.choice(STATES),
        "Class": messy_cat(["JSS1", "jss1", "SSS2", "sss 2", "Primary 5"]),
        "Exam Score": str(random.randint(0, 100)),
        "On Scholarship": random.choice(YESNO), "Guardian Phone": phone(),
    },
    "social_protection": lambda: {
        "Household ID": "HH" + str(random.randint(10000, 99999)),
        "Head NIN": nin(), "Head Name": random.choice(FIRST) + " " + random.choice(LAST),
        "Sex of Head": random.choice(["M", "F", "male", "FEMALE"]), "Phone": phone(),
        "State": random.choice(STATES), "Household Size": str(random.randint(1, 12)),
        "Poverty Score": str(round(random.uniform(0, 1), 3)),
        "Programme": messy_cat(["NCTP", "cash transfer", "Cash Transfer", "grant"]),
        "Transfer Amount": money(), "Payment Status": random.choice(YESNO),
    },
    "finance": lambda: {
        "Account Number": str(random.randint(1000000000, 9999999999)),
        "BVN": nin(), "NIN": nin(), "Account Name": random.choice(FIRST) + " " + random.choice(LAST),
        "Phone": phone(), "Email": random.choice(["ADA@X.IO", "musa@mail.com", "bad-email", "n@bank.ng"]),
        "Account Type": messy_cat(["savings", "Current", "SAVINGS", "current"]),
        "KYC Tier": messy_cat(["tier 1", "Tier1", "TIER 2", "tier3"]),
        "State": random.choice(STATES), "Balance": money(), "Active": random.choice(YESNO),
    },
}


def build(rows=25):
    for name, mk in SECTORS.items():
        recs = [mk() for _ in range(rows)]
        path = OUT / f"{name}_sample.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
            w.writeheader()
            w.writerows(recs)
        print(f"wrote {path}  ({rows} rows, {len(recs[0])} columns)")


if __name__ == "__main__":
    build()
