"""Generate a deliberately messy sample register that exercises every transform.

Not real citizen data — synthetic rows built to contain the exact problems the
transforms exist to fix: mixed phone formats, mixed date formats, ALL-CAPS
names, misspelled and concatenated place names, short NINs, odd gender codes.
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

random.seed(1864)

FIRST = ["Abiola", "FATIMA", "musa", "ngozi", "IBRAHIM", "Chidi", "Aisha", "TUNDE", "amina", "Emeka"]
LAST = ["OYEBANJO", "bello", "Sani", "OKAFOR", "mohammed", "ADEYEMI", "usman", "Nwosu", "IDRIS", "obi"]
LGAS = ["Zaria", "sabongari", "Kaduna North", "ZariaTudunWada", "chikun", "Kajaru", "Jemaa", "Zangonkataf", "Makarfe", "Kubau"]
STATES = ["Kaduna", "kaduna ", "KADUNA", "Kastina", "Kaduna(Kastina)", "kd", "Katsina", "Nassarawa", "FCT", "abuja"]
SEXES = ["M", "f", "Male", "FEMALE", "1", "2", "man", "woman", "", "girl"]


def _phone() -> str:
    body = random.choice(["803", "806", "701", "905", "816", "999"]) + "".join(random.choice("0123456789") for _ in range(7))
    fmt = random.choice([
        lambda b: "0" + b,
        lambda b: b,
        lambda b: "+234" + b,
        lambda b: "234" + b,
        lambda b: "+234 " + b[:3] + " " + b[3:6] + " " + b[6:],
        lambda b: "0" + b[:3] + "-" + b[3:6] + "-" + b[6:],
    ])
    return fmt(body)


def _nin() -> str:
    if random.random() < 0.04:  # ~4% bad, like the real 7/18k in the mockup
        return "".join(random.choice("0123456789") for _ in range(random.choice([7, 9, 12])))
    return "".join(random.choice("0123456789") for _ in range(11))


def _dob() -> str:
    y = random.randint(1960, 2005)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    fmt = random.choice([
        lambda: f"{d}/{m}/{y}",
        lambda: f"{d}/{m}/{str(y)[2:]}",
        lambda: f"{d}-{m:02d}-{y}",
        lambda: f"{y}-{m:02d}-{d:02d}",
        lambda: f"{d:02d}.{m:02d}.{y}",
    ])
    return fmt()


def build(n: int = 500) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        rows.append({
            "NIN Number": _nin(),
            "Ph No": _phone(),
            "Other Names": random.choice(FIRST) + (" T." if random.random() < 0.2 else ""),
            "Surname": random.choice(LAST),
            "D.O.B": _dob(),
            "Sex": random.choice(SEXES),
            "State of Origin": random.choice(STATES),
            "LGA": random.choice(LGAS),
            "Household ID": f"HH-{random.randint(10000, 99999)}",
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent
    df = build(500)
    csv_path = out_dir / "socu_sample_raw.csv"
    xlsx_path = out_dir / "socu_sample_raw.xlsx"
    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)
    print(f"Wrote {len(df)} rows to:")
    print(f"  {csv_path}")
    print(f"  {xlsx_path}")
