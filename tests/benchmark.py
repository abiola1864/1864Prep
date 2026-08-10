"""Feature scoreboard: run labelled cases through each feature, compute real
metrics, and write a self-contained test.html. Every number here comes from an
actual engine run on the labelled sets below - nothing is hand-entered.

Run:  python tests/benchmark.py   ->  writes prototype/ui/test.html
"""
import sys, html, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

from engine.profile import profile_column, infer_date_order, infer_decimal_convention
from engine import domains as D
from engine import ng_admin as NG
from engine.dedupe import cluster_similar
from engine import embeddings as EMB
try:
    from engine.names import name_gender, available as names_available
except Exception:
    names_available = lambda: False

def _status(score):
    return "good" if score >= 0.9 else ("ok" if score >= 0.75 else "weak")


def pr_metrics(cases, predict):
    """cases: list[(input, expected_or_None)]; predict(input)->value_or_None.
    Positive = expected is not None. Computes precision/recall/accuracy + fails."""
    tp = fp = fn = tn = 0
    fails = []
    for inp, exp in cases:
        got = predict(inp)
        pos_exp, pos_got = exp is not None, got is not None
        if pos_exp and pos_got and got == exp: tp += 1
        elif pos_exp and pos_got and got != exp: fp += 1; fn += 1; fails.append((inp, exp, got))
        elif pos_exp and not pos_got: fn += 1; fails.append((inp, exp, "(missed)"))
        elif not pos_exp and pos_got: fp += 1; fails.append((inp, "(none)", got))
        else: tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    acc = (tp + tn) / len(cases) if cases else 1.0
    return precision, recall, acc, fails


def accuracy_cases(cases, predict):
    correct, fails = 0, []
    for inp, exp in cases:
        got = predict(inp)
        if got == exp: correct += 1
        else: fails.append((inp, exp, got))
    return (correct / len(cases) if cases else 1.0), fails


def run_benchmark():
    RESULTS = []

    # ---------------- 1. Column type detection (multi-class) ----------------
    type_cols = [
        ("phone", ["+2348012345678","08087654321","+2347013649377","08123456789"], "phone"),
        ("email", ["a@b.com","x.y@z.org","q@r.co"], "email"),
        ("date", ["2020-01-15","2020-06-30","2019-12-01"], "date"),
        ("amount", ["1200.50","3400","950.75","12000"], "numeric"),
        ("age", ["23","45","31","67","19","52","38","41"], "numeric"),
        ("name", ["Ngozi Okonjo","Emeka Obi","Musa Yakubu"], "name"),
        ("id", ["0001234567","0007654321","0009999999"], "identifier"),
        ("code", ["ABC123","1234567890","0001234567","ABC123"], "identifier"),
        ("sex", ["Male","Female","M","F","male"], "gender"),
        ("comment", ["good service here","very far from road","okay place"], "free_text"),
    ]
    def _type_of(vals):
        return profile_column(pd.Series(vals), "c").semantic_type
    tp=fp=fn=0; typefails=[]
    per_type = {}
    for _, vals, exp in type_cols:
        got = _type_of(vals)
        ok = (got == exp)
        per_type.setdefault(exp, [0,0]); per_type[exp][1]+=1
        if ok: per_type[exp][0]+=1
        else: typefails.append((", ".join(vals[:3])+" ...", exp, got))
    type_acc = sum(v[0] for v in per_type.values())/sum(v[1] for v in per_type.values())
    RESULTS.append({"group":"Column type detection","desc":"Deciding what each column holds (phone, date, number, name, code, category, free text) from its values.",
        "metrics":[("Accuracy", type_acc), ("Types correct", f"{sum(v[0] for v in per_type.values())}/{sum(v[1] for v in per_type.values())}")],
        "n":len(type_cols), "status":_status(type_acc), "fails":typefails,
        "note":"Accuracy = share of columns typed correctly."})

    # ---------------- 2. Date-order inference ----------------
    date_cases = [
        (("12.28.2020","06.30.2020","11.22.2019","03.14.2021"), "MDY"),
        (("28.12.2020","30.06.2020","22.11.2019","14.03.2021"), "DMY"),
        (("2020-12-28","2021-01-15","2019-06-30"), "YMD"),
        (("05.03.2021","01.02.2020"), None),   # ambiguous -> asks
    ]
    acc, fails = accuracy_cases(date_cases, lambda vals: infer_date_order(list(vals)*3)[0])
    RESULTS.append({"group":"Date-order inference","desc":"Reading the whole column to decide day/month/year order (51% majority, so one typo can't flip it).",
        "metrics":[("Accuracy", acc)], "n":len(date_cases), "status":_status(acc),
        "fails":[(", ".join(i), e, g) for i,e,g in fails],
        "note":"Ambiguous columns (every part <=12) should return 'ambiguous' (None) rather than guess."})

    # ---------------- 3. Decimal convention ----------------
    dec_cases = [
        (("42.959","43.245","12.5","900"), "dot"),
        (("1.234,56","2.500,00","12,5","7,80"), "comma"),
        (("1,200.50","3,400.00","950.75"), "dot"),
    ]
    acc, fails = accuracy_cases(dec_cases, lambda vals: infer_decimal_convention(list(vals)*3)[0])
    RESULTS.append({"group":"Decimal convention","desc":"Deciding if '.' or ',' is the decimal separator, from the whole column, so 42.959 is never turned into 42959.",
        "metrics":[("Accuracy", acc)], "n":len(dec_cases), "status":_status(acc),
        "fails":[(", ".join(i), e, g) for i,e,g in fails], "note":""})

    # ---------------- 4. Country resolution (precision matters: no false positives) ----------------
    country_cases = [
        ("Nigeria","NGA"),("naija","NGA"),("USA","USA"),("United States","USA"),
        ("Cote d'Ivoire","CIV"),("DRC","COD"),("Niger","NER"),
        ("12 Broad Street",None),("Yes",None),("Male",None),("hello world",None),("Ikeja",None),
    ]
    p,r,a,fails = pr_metrics(country_cases, lambda v: D.canonical_of("country", v))
    RESULTS.append({"group":"Country resolution","desc":"Matching country names to ISO3, while refusing to turn non-countries (addresses, 'Yes') into a country.",
        "metrics":[("Precision", p),("Recall", r),("Accuracy", a)], "n":len(country_cases),
        "status":_status(min(p,r)), "fails":fails,
        "note":"Precision here means: when it says 'country', it is right. False positives (addresses becoming a country) hurt precision most."})

    # ---------------- 5. NG state resolution ----------------
    state_cases = [
        ("Katsina","Katsina"),("Cros River","Cross River"),("Akwa-Ibom","Akwa Ibom"),
        ("FCT","Federal Capital Territory"),("Abuja","Federal Capital Territory"),
        ("Lagos","Lagos"),("Kano","Kano"),
    ]
    acc, fails = accuracy_cases(state_cases, lambda v: NG.resolve_state(v))
    RESULTS.append({"group":"NG state resolution","desc":"Standardising the 36 states + FCT, tolerating typos (Cros River -> Cross River).",
        "metrics":[("Accuracy", acc)], "n":len(state_cases), "status":_status(acc), "fails":fails, "note":""})

    # ---------------- 6. NG LGA validation (kind classification) ----------------
    lga_cases = [
        ("Ikeja","lga"),("Surulere","lga"),("Bakory","lga"),("Kosofe Local Government Area","lga"),
        ("Lagos","is_state"),("Kano","is_state"),
        ("Computer Village","unknown"),("Agboyi-Ketu","unknown"),
    ]
    acc, fails = accuracy_cases(lga_cases, lambda v: NG.validate_lga_value(v)["kind"])
    RESULTS.append({"group":"NG LGA validation","desc":"Checking values in an LGA column against all 774 LGAs: real LGA, wrong level (a state), or unknown (a city/community).",
        "metrics":[("Accuracy", acc)], "n":len(lga_cases), "status":_status(acc), "fails":fails,
        "note":"Lagos LCDAs (Agboyi-Ketu) are correctly 'unknown' - they are not federal LGAs."})

    # ---------------- 7. Number-merge safety (must NOT merge different numbers) ----------------
    def _merges_diff_numbers():
        fails=[]
        for group in [["-1","1","1","-1"], ["7","7.0"], ["0","-0"], ["1-5","6-10"]]:
            clusters = cluster_similar(group*3)
            for c in clusters:
                m=set(c["members"])
                if {"-1","1"} <= m or {"1-5","6-10"} <= m:
                    fails.append((" / ".join(group), "kept separate", "MERGED"))
        return fails
    nf = _merges_diff_numbers()
    safety = 1.0 if not nf else 0.0
    RESULTS.append({"group":"Number-merge safety","desc":"Guard that different numbers never merge (-1 is a sentinel, not 1), while 7.0 == 7.",
        "metrics":[("Pass", "yes" if safety else "no")], "n":4, "status":_status(safety), "fails":nf,
        "note":"A single failure here is serious - it would silently corrupt data."})

    # ---------------- 8. Name gender (optional; probabilistic) ----------------
    if names_available():
        gender_cases = [
            ("Ngozi","Female"),("Emeka","Male"),("Folake","Female"),("Musa","Male"),
            ("Adaeze","Female"),("Yakubu","Male"),("Oluwaseun",None),   # unisex -> unknown
        ]
        acc, fails = accuracy_cases(gender_cases, lambda v: name_gender(v)[0])
        RESULTS.append({"group":"Name gender estimate (optional)","desc":"Probabilistic gender from a first name; unisex names correctly return unknown. Never overwrites data.",
            "metrics":[("Accuracy", acc)], "n":len(gender_cases), "status":_status(acc), "fails":fails,
            "note":"This is a labelled ESTIMATE, not a fact. Requires the names-dataset package."})
    else:
        RESULTS.append({"group":"Name gender estimate (optional)","desc":"Probabilistic gender from a first name.",
            "metrics":[("Status","not installed")], "n":0, "status":"na", "fails":[],
            "note":"Install with: pip install names-dataset"})

    # ---------------- 9. Embedding layer (honest backend report) ----------------
    V = EMB.embed(["Ikeja market","Ikeja markt","Groceries","Provisions"])
    typo_sim = EMB.cosine(V[0], V[1]); syn_sim = EMB.cosine(V[2], V[3])
    RESULTS.append({"group":"Semantic embedding layer","desc":"Backend that powers meaning-based matching. Falls back to lexical vectors when no model is installed.",
        "metrics":[("Active backend", EMB.get_embedder().backend),
                   ("Typo similarity (high=good)", round(float(typo_sim),2)),
                   ("Synonym similarity", round(float(syn_sim),2))],
        "n":4, "status":"good" if EMB.is_semantic() else "ok",
        "fails":[],
        "note":"With the lexical fallback, synonym similarity is expectedly low; installing a neural model ([semantic]) raises it. This row reports reality, not a target."})

    # ---------------- 10. Excel date serials ----------------
    from engine.ingest import _fix_serial_header
    from engine import get_transform as _gt
    _dser = _gt("date_iso")
    serial_cases = [
        ("header 44562", _fix_serial_header("44562"), "2022-01-01"),
        ("header ABC (not a serial)", _fix_serial_header("ABC"), "ABC"),
        ("value 44197", _dser.apply_value("44197")[0], "2021-01-01"),
        ("value 44562.5 (fractional)", _dser.apply_value("44562.5")[0], "2022-01-01"),
    ]
    sfails = [(a, exp, got) for a, got, exp in serial_cases if got != exp]
    sacc = 1 - len(sfails) / len(serial_cases)
    RESULTS.append({"group":"Excel date serials","desc":"Excel often leaks dates as 5-digit numbers, in cells and even as column headers. These are turned back into real dates.",
        "metrics":[("Accuracy", sacc)], "n":len(serial_cases), "status":_status(sacc), "fails":sfails,
        "note":"A whole column of serials is only read as dates when the column name hints a date, so real ID/code columns are never corrupted."})

    # ---------------- 11. Robust file reading (encoding) ----------------
    import tempfile as _tf, os as _os
    from engine.ingest import read_any as _ra
    enc_fails = []
    try:
        raw = b"\xff\xfe" + "name,age\nJo\u00e3o,30\nRen\u00e9,40\n".encode("utf-16-le")
        p = _tf.mktemp(suffix=".csv"); open(p, "wb").write(raw)
        df_e, rep_e = _ra(p); _os.unlink(p)
        if not (len(df_e) == 2 and str(df_e.iloc[0, 0]) == "Jo\u00e3o"):
            enc_fails.append(("UTF-16 file with accents", "Jo\u00e3o / 2 rows", f"{df_e.iloc[0,0]} / {len(df_e)} rows"))
    except Exception as e:
        enc_fails.append(("UTF-16 file", "reads cleanly", f"error: {e}"))
    epass = 1.0 if not enc_fails else 0.0
    RESULTS.append({"group":"Robust file reading","desc":"Reads files whatever their encoding: detects byte-order marks (UTF-16, UTF-8-BOM) and falls back safely so a mangled export still loads.",
        "metrics":[("Pass", "yes" if epass else "no")], "n":1, "status":_status(epass), "fails":enc_fails,
        "note":"Accented characters survive; invalid bytes are removed rather than crashing the read."})

    # ---------------- 12. Export safety ----------------
    from engine.exporters import _export_safe as _es
    import pandas as _pd
    _eo = _es(_pd.DataFrame({"t": ["a\nb", "c\rd", "e\ufffdf", "fine"]}))
    exp_expected = ["a b", "cd", "ef", "fine"]
    xfails = [(inp, e, g) for inp, e, g in zip(["a\\nb","c\\rd","e\\ufffdf","fine"], exp_expected, list(_eo["t"])) if e != g]
    xacc = 1 - len(xfails) / len(exp_expected)
    RESULTS.append({"group":"Export safety","desc":"Cleans values so the file opens correctly in the next tool: removes in-field line breaks and stray control characters that break CSV and spreadsheet readers.",
        "metrics":[("Accuracy", xacc)], "n":len(exp_expected), "status":_status(xacc), "fails":xfails,
        "note":"Only breakage is removed; the meaning of every value is preserved."})

    # make JSON-safe: metrics tuples -> lists, fails tuples -> lists
    for R in RESULTS:
        R["metrics"] = [[k, v] for k, v in R["metrics"]]
        R["fails"] = [[str(a), str(b), str(c)] for a, b, c in R["fails"]]
    return RESULTS


import json, html, datetime


_PAGE_TMPL = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>1864 Prep — Engine diagnostics</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#fbfbf9; --panel:#ffffff; --ink:#14171a; --muted:#6b7078; --faint:#9aa0a8;
    --line:#e8e9ec; --line2:#f0f1f3; --accent:#1b3a5b;
    --good:#1f7a44; --good-bg:#e8f3ec; --ok:#8a6a12; --ok-bg:#f6efd7; --weak:#b23b3b; --weak-bg:#f7e6e6; --na:#8a8f98; --na-bg:#eef0f2;
    --disp:"Space Grotesk",ui-sans-serif,system-ui,sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
    --body:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
  .wrap{max-width:920px;margin:0 auto;padding:34px 20px 72px}
  .eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin:0 0 10px}
  header.top{display:grid;grid-template-columns:1fr auto;gap:24px;align-items:end;border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:22px}
  h1{font-family:var(--disp);font-weight:700;font-size:34px;line-height:1.05;letter-spacing:-.01em;margin:0 0 8px}
  .lede{color:var(--muted);max-width:52ch;margin:0}
  .gauge{text-align:right;min-width:180px}
  .gauge .big{font-family:var(--mono);font-weight:600;font-size:46px;line-height:1;letter-spacing:-.02em;color:var(--accent)}
  .gauge .glabel{font-size:12px;color:var(--muted);margin-top:4px}
  .gmeter{height:6px;border-radius:99px;background:var(--line);overflow:hidden;margin-top:10px}
  .gmeter i{display:block;height:100%;background:var(--accent)}
  .controls{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:0 0 26px}
  .run{font-family:var(--disp);font-weight:600;font-size:15px;color:#fff;background:var(--accent);border:none;border-radius:10px;padding:11px 22px;cursor:pointer;transition:filter .15s}
  .run:hover:not(:disabled){filter:brightness(1.12)} .run:disabled{opacity:.55;cursor:default}
  .run:focus-visible{outline:3px solid #b9cbe0;outline-offset:2px}
  .runmsg{font-size:13px;color:var(--muted)}
  .legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--muted);margin:0 0 26px}
  .legend span{display:inline-flex;align-items:center;gap:7px}
  .dot{width:9px;height:9px;border-radius:99px;display:inline-block}
  section.defs{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin:0 0 30px}
  section.defs h2{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin:0 0 12px}
  .defs dl{margin:0;display:grid;grid-template-columns:132px 1fr;gap:0}
  .defs dt{font-family:var(--disp);font-weight:600;padding:9px 0;border-top:1px solid var(--line2)}
  .defs dd{margin:0;color:var(--muted);padding:9px 0;border-top:1px solid var(--line2)}
  .defs dl>dt:first-of-type,.defs dl>dd:nth-of-type(1){border-top:none}
  .rowlist{display:flex;flex-direction:column;gap:0;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:var(--panel)}
  .feat{padding:20px;border-top:1px solid var(--line)}
  .feat:first-child{border-top:none}
  .feat-head{display:flex;align-items:center;gap:12px;margin-bottom:4px}
  .idx{font-family:var(--mono);font-size:12px;color:var(--faint);width:26px;flex:0 0 26px}
  .feat-head h3{font-family:var(--disp);font-weight:600;font-size:18px;margin:0;flex:1}
  .pill{font-family:var(--mono);font-size:10.5px;font-weight:600;letter-spacing:.08em;padding:3px 9px;border-radius:99px}
  .desc{color:var(--muted);font-size:14px;margin:0 0 14px;padding-left:38px}
  .readout{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:center;padding-left:38px}
  .meter{height:8px;border-radius:99px;background:var(--line);overflow:hidden}
  .meter i{display:block;height:100%;border-radius:99px;transition:width .5s cubic-bezier(.2,.7,.2,1)}
  .chips{display:flex;gap:22px;flex-wrap:wrap;align-items:flex-end}
  .chip{display:flex;flex-direction:column;gap:2px}
  .chip .k{font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--faint)}
  .chip .v{font-family:var(--mono);font-weight:600;font-size:19px;line-height:1;color:var(--ink)}
  .chip .v.small{font-size:14px;font-weight:500}
  .note{color:var(--muted);font-size:13px;margin:14px 0 0;padding-left:38px;border-left:0}
  .note b{color:var(--ink)}
  details{margin:12px 0 0 38px}
  summary{cursor:pointer;font-family:var(--disp);font-weight:600;font-size:13px;color:var(--accent);list-style:none}
  summary::-webkit-details-marker{display:none}
  summary::before{content:"▸ ";color:var(--faint)}
  details[open] summary::before{content:"▾ "}
  table.fails{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}
  table.fails th{text-align:left;font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:600;padding:6px 10px;border-bottom:1px solid var(--line)}
  table.fails td{padding:7px 10px;border-bottom:1px solid var(--line2);vertical-align:top;font-family:var(--mono);font-size:12.5px}
  table.fails td.exp{color:var(--good)} table.fails td.got{color:var(--weak)}
  .foot{color:var(--faint);font-size:12px;margin-top:26px;text-align:center;line-height:1.7}
  .foot code{font-family:var(--mono);background:var(--line2);padding:2px 6px;border-radius:6px}
  @media(max-width:640px){
    header.top{grid-template-columns:1fr;align-items:start} .gauge{text-align:left}
    h1{font-size:27px} .defs dl{grid-template-columns:1fr} .defs dt{padding-bottom:0;border-top:1px solid var(--line2)} .defs dd{padding-top:2px;border-top:none}
    .desc,.readout,.note,details{padding-left:0;margin-left:0} .idx{display:none}
    .readout{grid-template-columns:1fr}
  }
  @media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body><div class="wrap">
  <p class="eyebrow">1864 Prep · Engine diagnostics</p>
  <header class="top">
    <div>
      <h1>Feature scoreboard</h1>
      <p class="lede">How each part of the engine performs, measured on labelled test cases. Every number is from a live run — nothing is hand-entered.</p>
    </div>
    <div class="gauge">
      <div class="big" id="gauge-num">—</div>
      <div class="glabel">average accuracy · measured features</div>
      <div class="gmeter"><i id="gauge-bar" style="width:0%"></i></div>
    </div>
  </header>

  <div class="controls">
    <button class="run" id="runbtn" onclick="runLive()">Run tests now</button>
    <span class="runmsg" id="runmsg">Showing results generated __GENERATED__.</span>
  </div>

  <div class="legend">
    <span><i class="dot" style="background:var(--good)"></i> strong · ≥90%</span>
    <span><i class="dot" style="background:var(--ok)"></i> usable · ≥75%</span>
    <span><i class="dot" style="background:var(--weak)"></i> needs work · &lt;75%</span>
    <span style="color:var(--faint)">open a feature's “cases to improve” to see exactly what failed</span>
  </div>

  <section class="defs"><h2>How to read this</h2><dl>
    <dt>Accuracy</dt><dd>Share of test cases the feature got exactly right — correct answers ÷ all cases.</dd>
    <dt>Precision</dt><dd>When the feature makes a positive call, how often it's right. Low precision means false positives (calling an address a “country”).</dd>
    <dt>Recall</dt><dd>Of the cases that should have been caught, how many were. Low recall means misses (a real country left unresolved).</dd>
    <dt>False positive</dt><dd>Saying “yes / this type” when the truth is “no” — the costliest error, because it can change data silently.</dd>
    <dt>n</dt><dd>Number of labelled cases behind the score. A small n means the number is indicative, not definitive.</dd>
    <dt>Sentinel</dt><dd>A placeholder like -1, 999, or N/A that stands for “missing / refused”, not a real value.</dd>
  </dl></section>

  <div class="rowlist" id="cards"></div>
  <p class="foot">Run <code>python tests/benchmark.py</code> to regenerate offline · “Run tests now” re-runs the benchmark live when the app is running.</p>
</div>
<script>
const C={good:['var(--good)','var(--good-bg)'],ok:['var(--ok)','var(--ok-bg)'],weak:['var(--weak)','var(--weak-bg)'],na:['var(--na)','var(--na-bg)']};
const LABEL={good:'STRONG',ok:'USABLE',weak:'NEEDS WORK',na:'N/A'};
const DATA = __DATA__;
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function isScore(v){return typeof v==='number' && v>=0 && v<=1;}
function fmt(v){return isScore(v)?Math.round(v*100)+'%':esc(v);}
function primaryScore(m){for(const [k,v] of m){if(isScore(v))return v;}return null;}
function render(results){
  const nums=results.filter(r=>isScore(r.metrics[0][1]));
  const avg=nums.length?nums.reduce((a,r)=>a+r.metrics[0][1],0)/nums.length:0;
  document.getElementById('gauge-num').textContent=Math.round(avg*100)+'%';
  document.getElementById('gauge-bar').style.width=Math.round(avg*100)+'%';
  document.getElementById('cards').innerHTML=results.map((R,i)=>{
    const col=C[R.status]||C.na;
    const score=primaryScore(R.metrics);
    const meter = score!==null
      ? '<div class="meter" role="img" aria-label="score '+Math.round(score*100)+' percent"><i style="width:'+Math.round(score*100)+'%;background:'+col[0]+'"></i></div>'
      : '<div></div>';
    const chips=R.metrics.map(([k,v])=>'<span class="chip"><span class="k">'+esc(k)+'</span><span class="v'+(isScore(v)?'':' small')+'">'+fmt(v)+'</span></span>').join('')
      +'<span class="chip"><span class="k">cases</span><span class="v small">n='+R.n+'</span></span>';
    let fails='';
    if(R.fails&&R.fails.length){
      const rows=R.fails.slice(0,20).map(f=>'<tr><td>'+esc(f[0])+'</td><td class="exp">'+esc(f[1])+'</td><td class="got">'+esc(f[2])+'</td></tr>').join('');
      fails='<details><summary>'+R.fails.length+' case'+(R.fails.length>1?'s':'')+' to improve</summary>'+
        '<table class="fails"><thead><tr><th>input</th><th>expected</th><th>got</th></tr></thead><tbody>'+rows+'</tbody></table></details>';
    }
    const note=R.note?'<p class="note">'+esc(R.note)+'</p>':'';
    return '<div class="feat"><div class="feat-head"><span class="idx">'+String(i+1).padStart(2,'0')+'</span>'+
      '<h3>'+esc(R.group)+'</h3><span class="pill" style="color:'+col[0]+';background:'+col[1]+'">'+LABEL[R.status]+'</span></div>'+
      '<p class="desc">'+esc(R.desc)+'</p>'+
      '<div class="readout">'+meter+'<div class="chips">'+chips+'</div></div>'+note+fails+'</div>';
  }).join('');
}
async function runLive(){
  const btn=document.getElementById('runbtn'),msg=document.getElementById('runmsg');
  btn.disabled=true;const t0=Date.now();msg.textContent='Running the benchmark…';
  try{
    const res=await fetch('/api/benchmark',{method:'POST'});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const data=await res.json();render(data.results);
    msg.textContent='Ran live just now in '+((Date.now()-t0)/1000).toFixed(1)+'s.';
  }catch(e){msg.textContent='Could not run live (is the app running?). Showing the last generated results.';}
  finally{btn.disabled=false;}
}
render(DATA);
</script></body></html>"""


def build_page(results):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return (_PAGE_TMPL
            .replace("__DATA__", json.dumps(results))
            .replace("__GENERATED__", now))


if __name__ == "__main__":
    from pathlib import Path as _P
    results = run_benchmark()
    out = _P(__file__).resolve().parents[1] / "prototype" / "ui" / "test.html"
    out.write_text(build_page(results))
    print("wrote", out)
    nums = [r for r in results if isinstance(r["metrics"][0][1], float)]
    avg = sum(r["metrics"][0][1] for r in nums) / len(nums) if nums else 0
    print(f"average accuracy across measured features: {avg*100:.0f}%")
    for R in results:
        k, v = R["metrics"][0]
        val = f"{v*100:.0f}%" if isinstance(v, float) else v
        print(f"  [{R['status']:>4}] {R['group']:<32} {k}={val}  (n={R['n']}, {len(R['fails'])} fails)")
