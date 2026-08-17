"""Data Toolkit — self-serve operations agencies reach for after cleaning.

Each function is deterministic and returns (result, summary): `result` is either
a DataFrame (a dataset to download) or a report dict; `summary` is a short,
plain-language description for the preview. Nothing is destructive — inputs are
never mutated.
"""
from __future__ import annotations

import hashlib
from collections import Counter

import pandas as pd

from .dedupe import near_duplicate_rows
from .profile import profile_dataframe


# ── helpers ────────────────────────────────────────────────────────────────
def _norm_header(h: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "", str(h).lower())


def detect_keys(df: pd.DataFrame) -> list[str]:
    """Columns that look like unique identifiers (id/phone/email, high-distinct)."""
    profs = {p.column: p for p in profile_dataframe(df)}
    keys = []
    for c in df.columns:
        p = profs.get(c)
        distinct_ratio = df[c].nunique(dropna=True) / max(1, df[c].notna().sum())
        if p and p.semantic_type in ("identifier", "phone", "email") and distinct_ratio >= 0.9:
            keys.append(c)
    if not keys:  # fall back to any near-unique column
        for c in df.columns:
            if df[c].notna().sum() and df[c].nunique() / df[c].notna().sum() >= 0.98:
                keys.append(c)
    return keys


# ── 1. duplicates ────────────────────────────────────────────────────────────
def find_duplicates(df: pd.DataFrame, subset: list[str] | None = None):
    groups = near_duplicate_rows(df, subset=subset)
    idxs = sorted({i for g in groups for i in g["rows"]})
    result = df.iloc[idxs].copy() if idxs else df.iloc[0:0].copy()
    result.insert(0, "_dup_group", "")
    for gi, g in enumerate(groups, 1):
        for i in g["rows"]:
            if i in result.index:
                result.at[i, "_dup_group"] = f"G{gi} ({g['kind']})"
    summary = {"duplicate_groups": len(groups), "rows_involved": len(idxs)}
    return result, summary


# ── 2. outliers ──────────────────────────────────────────────────────────────
def find_outliers(df: pd.DataFrame):
    profs = profile_dataframe(df, use_ml=True)
    rows = []
    for p in profs:
        if p.semantic_type != "numeric":
            continue
        s = pd.to_numeric(df[p.column].astype(str).str.replace(r"[,\s%$₦£€]", "", regex=True),
                          errors="coerce").dropna()
        if len(s) < 8:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for i, v in s.items():
            if v < lo or v > hi:
                rows.append({"row": int(i), "column": p.column, "value": df[p.column].iloc[i],
                             "reason": f"outside {round(lo,2)}..{round(hi,2)}"})
    result = pd.DataFrame(rows)
    return result, {"outliers": len(rows), "numeric_columns_checked":
                    sum(1 for p in profs if p.semantic_type == "numeric")}


def outlier_evaluate(df: pd.DataFrame, columns: list[str] | None = None) -> list[dict]:
    """The 'look at the spread' step. For each numeric column, return a plain
    read-out (count, missing, min, quartiles, max, skew) and a suggested method,
    so the person can judge the shape before flagging anything. Best practice:
    IQR for skewed data, Z-score for roughly symmetric data."""
    profs = {p.column: p for p in profile_dataframe(df, use_ml=True)}
    cols = columns or [c for c in df.columns if profs.get(c) and profs[c].semantic_type == "numeric"]
    out = []
    for c in cols:
        s = pd.to_numeric(df[c].astype(str).str.replace(r"[,\s%$₦£€]", "", regex=True),
                          errors="coerce")
        vals = s.dropna()
        if len(vals) < 5:
            out.append({"column": c, "note": "too few numbers to evaluate"})
            continue
        q1, q3, med = vals.quantile(0.25), vals.quantile(0.75), vals.median()
        skew = float(vals.skew()) if len(vals) > 2 else 0.0
        method = "IQR — best for skewed data" if abs(skew) >= 1 else "Z-score — best for bell-shaped data"
        out.append({
            "column": c, "count": int(len(vals)), "missing": int(s.isna().sum()),
            "min": round(float(vals.min()), 3), "q1": round(float(q1), 3),
            "median": round(float(med), 3), "q3": round(float(q3), 3),
            "max": round(float(vals.max()), 3), "skew": round(skew, 2),
            "suggested_method": method,
            "shape": ("right-skewed" if skew >= 1 else "left-skewed" if skew <= -1 else "roughly symmetric"),
        })
    return out


def dedupe_confusion(df: pd.DataFrame, subset: list[str] | None = None) -> list[dict]:
    """The 'check confusing columns' step for duplicates. Before matching, warn
    about columns whose own values are inconsistent, because that quietly makes
    the tool miss real duplicates or merge different records. Returns one warning
    per problem, with an example, so the person can tidy first."""
    cols = subset or list(df.columns)
    warnings = []
    for c in cols:
        s = df[c].dropna().astype(str)
        if s.empty:
            continue
        stripped = s.str.strip()
        # case/whitespace variants that collapse to the same key
        collapsed = stripped.str.lower()
        distinct_raw = s.nunique()
        distinct_key = collapsed.nunique()
        if distinct_key < distinct_raw:
            example = next((v for v in s.unique()
                            if sum(1 for w in s.unique() if str(w).strip().lower() == str(v).strip().lower()) > 1), None)
            warnings.append({"column": c, "issue": "case or spacing variants",
                             "detail": f"{distinct_raw - distinct_key} value(s) differ only by capitals or spaces",
                             "example": example,
                             "advice": "Standardise this column first, or matches on it will be missed."})
        # values with separators (multi-code) are risky as match keys
        multi = stripped.str.contains(r"[;,/|]").mean()
        if multi >= 0.1:
            warnings.append({"column": c, "issue": "multiple values in one cell",
                             "detail": f"about {round(multi*100)}% of cells contain separators (comma, slash)",
                             "example": next((v for v in stripped if any(x in v for x in ";,/|")), None),
                             "advice": "This is a coded/multi-value column; it is a poor key for matching duplicates."})
    return warnings


# ── 3. match & merge across files ────────────────────────────────────────────
def match_files(dfs: list[pd.DataFrame], how: str = "outer", key: str | None = None):
    if len(dfs) < 2:
        raise ValueError("Need at least two files to match.")
    # auto-detect a shared key by normalised header present in all files
    if key is None:
        per = [{_norm_header(c): c for c in d.columns} for d in dfs]
        common = set(per[0]).intersection(*[set(p) for p in per[1:]])
        cand = []
        for nk in common:
            cols = [p[nk] for p in per]
            # overlap of values between file 0 and file 1
            a = set(dfs[0][cols[0]].dropna().astype(str))
            b = set(dfs[1][cols[1]].dropna().astype(str))
            overlap = len(a & b) / max(1, min(len(a), len(b)))
            if a and b:
                cand.append((overlap, nk, cols))
        cand.sort(reverse=True)
        if not cand:
            raise ValueError("No shared key column found across the files.")
        _, nk, keycols = cand[0]
    else:
        keycols = [key] * len(dfs)
    merged = dfs[0].rename(columns={keycols[0]: "_key"})
    merged["_key"] = merged["_key"].astype(str)
    for j, d in enumerate(dfs[1:], 1):
        d2 = d.rename(columns={keycols[j]: "_key"}); d2["_key"] = d2["_key"].astype(str)
        merged = merged.merge(d2, on="_key", how=how, suffixes=("", f"_f{j+1}"))
    summary = {"files": len(dfs), "key_detected": keycols[0], "join": how, "rows": len(merged)}
    return merged, summary


# ── 4. validate ──────────────────────────────────────────────────────────────
def validate(df: pd.DataFrame, required: list[str] | None = None):
    import re
    profs = {p.column: p for p in profile_dataframe(df, use_ml=True)}
    issues = []
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for c in df.columns:
        p = profs.get(c)
        for i, raw in df[c].items():
            v = "" if pd.isna(raw) else str(raw).strip()
            if required and c in required and v == "":
                issues.append({"row": int(i), "column": c, "issue": "required value missing"})
            if v == "":
                continue
            if p and p.semantic_type == "email" and not email_re.match(v):
                issues.append({"row": int(i), "column": c, "issue": "invalid email"})
            if p and p.semantic_type == "phone" and sum(ch.isdigit() for ch in v) < 7:
                issues.append({"row": int(i), "column": c, "issue": "phone too short"})
    result = pd.DataFrame(issues)
    return result, {"issues": len(issues), "rows_checked": len(df), "columns_checked": len(df.columns)}


# ── 5. summarise / profile ───────────────────────────────────────────────────
def summarise(df: pd.DataFrame):
    profs = {p.column: p for p in profile_dataframe(df, use_ml=True)}
    rows = []
    for c in df.columns:
        s = df[c]
        nonnull = s.notna().sum()
        rows.append({
            "column": c,
            "detected_type": profs[c].semantic_type if c in profs else "",
            "filled": int(nonnull),
            "missing_%": round(100 * (len(s) - nonnull) / max(1, len(s)), 1),
            "distinct": int(s.nunique(dropna=True)),
            "example": next((str(x) for x in s if str(x).strip()), ""),
        })
    result = pd.DataFrame(rows)
    return result, {"rows": len(df), "columns": len(df.columns)}


# ── 6. de-duplicate (produce cleaned file) ───────────────────────────────────
def dedupe_file(df: pd.DataFrame, subset: list[str] | None = None, keep: str = "first"):
    groups = near_duplicate_rows(df, subset=subset)
    drop = set()
    for g in groups:
        rows = sorted(g["rows"])
        drop.update(rows[1:] if keep == "first" else rows[:-1])
    result = df.drop(index=list(drop)).reset_index(drop=True)
    return result, {"removed": len(drop), "remaining": len(result)}


TOOLS = {
    "duplicates": ("Find duplicates", "Flag duplicate & near-duplicate records to download.", "dataset"),
    "outliers": ("Find outliers", "List numeric values that fall outside the normal range.", "report"),
    "match": ("Match & merge files", "Upload several files; auto-detects a shared ID and joins them.", "dataset"),
    "validate": ("Validate data", "Check required fields, valid emails/phones; download an issues report.", "report"),
    "summarise": ("Summarise / profile", "Per-column type, filled %, distinct, example — a data-quality report.", "report"),
    "dedupe": ("Remove duplicates", "Produce a cleaned file with duplicate rows removed.", "dataset"),
}


# ── 7. compare two files ─────────────────────────────────────────────────────
def compare_files(dfs: list[pd.DataFrame], key: str | None = None):
    if len(dfs) != 2:
        raise ValueError("Compare needs exactly two files (old, new).")
    a, b = dfs[0], dfs[1]
    if key is None:
        per = [{_norm_header(c): c for c in d.columns} for d in (a, b)]
        common = set(per[0]) & set(per[1])
        best = None
        for nk in common:
            ca, cb = per[0][nk], per[1][nk]
            sa, sb = set(a[ca].dropna().astype(str)), set(b[cb].dropna().astype(str))
            if sa and sb:
                ov = len(sa & sb) / max(1, min(len(sa), len(sb)))
                if best is None or ov > best[0]:
                    best = (ov, ca, cb)
        if not best:
            raise ValueError("No shared key column found.")
        _, ka, kb = best
    else:
        ka = kb = key
    a2 = a.copy(); a2[ka] = a2[ka].astype(str)
    b2 = b.copy(); b2[kb] = b2[kb].astype(str)
    sa, sb = set(a2[ka]), set(b2[kb])
    common_cols = [c for c in a.columns if c in b.columns and c != ka]
    rows = []
    for k in sb - sa:
        rows.append({"_status": "added", "key": k})
    for k in sa - sb:
        rows.append({"_status": "removed", "key": k})
    ai = a2.set_index(ka); bi = b2.set_index(kb)
    for k in sa & sb:
        changed = [c for c in common_cols
                   if str(ai.loc[k, c] if k in ai.index else "") != str(bi.loc[k, c] if k in bi.index else "")]
        if changed:
            rows.append({"_status": "changed", "key": k, "changed_columns": ", ".join(map(str, changed))})
    result = pd.DataFrame(rows)
    summary = {"added": sum(r["_status"] == "added" for r in rows),
               "removed": sum(r["_status"] == "removed" for r in rows),
               "changed": sum(r["_status"] == "changed" for r in rows), "key": ka}
    return result, summary


# ── 8. combine / append files ────────────────────────────────────────────────
def combine_files(dfs: list[pd.DataFrame]):
    if len(dfs) < 2:
        raise ValueError("Combine needs at least two files.")
    tagged = []
    for i, d in enumerate(dfs, 1):
        d = d.copy(); d.insert(0, "_source_file", f"file{i}")
        tagged.append(d)
    result = pd.concat(tagged, ignore_index=True, sort=False).fillna("")
    return result, {"files": len(dfs), "rows": len(result), "columns": len(result.columns) - 1}


# ── 9. anonymise / mask ──────────────────────────────────────────────────────
def anonymise(df: pd.DataFrame):
    profs = {p.column: p for p in profile_dataframe(df, use_ml=True)}
    out = df.copy()
    masked = []
    for c in out.columns:
        p = profs.get(c)
        if p and p.semantic_type in ("identifier", "phone", "email", "name"):
            vals = [str(v) for v in out[c] if str(v).strip()]
            digits_only = [v for v in vals if v.replace(".", "").isdigit()]
            if vals and len(digits_only) / len(vals) > 0.9 and all(len(v) <= 4 for v in digits_only):
                continue   # short pure numbers are ages/counts, not identifiers
            out[c] = out[c].map(lambda v: "" if pd.isna(v) or str(v).strip() == ""
                                else hashlib.sha256(str(v).strip().encode()).hexdigest()[:12])
            masked.append(c)
    return out, {"columns_masked": len(masked), "which": ", ".join(masked)}


# ── 10. quick clean (whole file, one click) ──────────────────────────────────
def quick_clean(df: pd.DataFrame):
    from .pipeline import run_plan
    from .profile import profile_to_plan
    try:
        import regions
        ref = regions.load_reference()
        profs = profile_dataframe(df, ref["gazetteers"], ref["place_index"], use_ml=True)
        plan = profile_to_plan(profs, "auto", ref["gazetteer_refs"])
    except Exception:
        profs = profile_dataframe(df, use_ml=True)
        plan = profile_to_plan(profs, "auto")
    cleaned, report, _ = run_plan(df, plan, "quick_clean")
    changed = sum(c.get("changed", 0) for c in report.columns)
    return cleaned, {"columns": len(cleaned.columns), "rows": len(cleaned), "values_changed": int(changed)}


TOOLS.update({
    "compare": ("Compare two files", "Old vs new: what was added, removed, or changed (auto-detects the key).", "report"),
    "combine": ("Combine / append files", "Stack several files with the same columns into one.", "dataset"),
    "anonymise": ("Anonymise / mask", "Hash IDs, phones, emails and names for safe sharing.", "dataset"),
    "quick_clean": ("Quick clean (whole file)", "One-click: clean every column automatically and download.", "dataset"),
})


def _name_column_score(header: str, values: list) -> float:
    """How name-like a column is, from its header and its values. Used to find the
    right column for gender estimation instead of guessing."""
    import re as _re
    h = str(header).lower()
    score = 0.0
    if _re.search(r"\b(name|surname|firstname|first name|fullname|full name|given|forename)\b", h):
        score += 0.6
    if _re.search(r"\b(id|code|email|phone|amount|date|number|no\.?)\b", h):
        score -= 0.5
    vals = [str(v).strip() for v in values if str(v).strip()][:200]
    if not vals:
        return score
    alpha = sum(1 for v in vals if _re.fullmatch(r"[A-Za-z][A-Za-z '\-\.]+", v))
    onetothree = sum(1 for v in vals if 1 <= len(v.split()) <= 3)
    titlecase = sum(1 for v in vals if v[:1].isupper())
    score += 0.4 * (alpha / len(vals)) + 0.2 * (onetothree / len(vals)) + 0.1 * (titlecase / len(vals))
    distinct = len(set(v.lower() for v in vals)) / len(vals)
    score += 0.1 * distinct
    return score


def guess_gender(df: pd.DataFrame, how: dict | None = None):
    """Add a clearly-labelled gender ESTIMATE from a name column (opt-in).
    Never overwrites data; adds '<col>_gender_estimate' + confidence. Unisex or
    unknown names are left blank. Requires the optional names-dataset package.
    """
    how = how or {}
    from .names import available, name_gender
    col = how.get("column")
    if not col:
        # score every column for name-likeness; require a clear winner
        scored = sorted(((_name_column_score(c, df[c].tolist()), c) for c in df.columns), reverse=True)
        best_score, best_col = scored[0] if scored else (0, None)
        if best_score < 0.4:
            return df, {"note": "No clear name column found. Please pick the column that holds people's names.",
                        "candidates": [c for _, c in scored[:3]]}
        col = best_col
    if not col or col not in df.columns:
        return df, {"note": "no name column found"}
    if not available():
        return df, {"note": "names-dataset not installed; run: pip install names-dataset",
                    "column": col}
    out = df.copy()
    est, conf = [], []
    for v in out[col].tolist():
        g, p = name_gender(v)
        est.append(g or "")
        conf.append(p if g else "")
    out[f"{col}_gender_estimate"] = est
    out[f"{col}_gender_confidence"] = conf
    filled = sum(1 for g in est if g)
    return out, {"column": col, "filled": filled, "total": len(est),
                 "note": "Estimate from first name (probabilistic). Blank = unisex/unknown. Not a fact."}


TOOLS.update({
    "guess_gender": ("Estimate gender from name", "Adds a labelled gender estimate from a name column (opt-in; works for Nigerian names). Never overwrites data.", "dataset"),
})
