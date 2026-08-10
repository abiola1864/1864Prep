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

    # make JSON-safe: metrics tuples -> lists, fails tuples -> lists
    for R in RESULTS:
        R["metrics"] = [[k, v] for k, v in R["metrics"]]
        R["fails"] = [[str(a), str(b), str(c)] for a, b, c in R["fails"]]
    return RESULTS


import json, html, datetime


_PAGE_TMPL = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>1864 Prep - Feature scoreboard</title>
<style>
  :root{--ink:#1a1f24;--soft:#5a636e;--line:#e4e7ea;--paper:#f7f6f3;--navy:#243b53}
  *{box-sizing:border-box} body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--paper)}
  .wrap{max-width:900px;margin:0 auto;padding:28px 18px 60px}
  h1{font-size:24px;margin:0 0 4px} .sub{color:var(--soft);margin:0 0 16px}
  .runbar{display:flex;align-items:center;gap:12px;margin:0 0 18px;flex-wrap:wrap}
  .runbtn{background:var(--navy);color:#fff;border:none;border-radius:10px;padding:11px 20px;font:inherit;font-weight:700;cursor:pointer}
  .runbtn:disabled{opacity:.6;cursor:default}
  .runbtn:hover:not(:disabled){filter:brightness(1.08)}
  .runmsg{color:var(--soft);font-size:13px}
  .summary{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:18px}
  .summary b{font-size:30px;color:var(--navy)}
  .defs{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin-bottom:22px}
  .defs h2{font-size:14px;text-transform:uppercase;letter-spacing:.05em;color:var(--soft);margin:0 0 8px}
  .defs dl{margin:0;display:grid;grid-template-columns:150px 1fr;gap:6px 14px}
  .defs dt{font-weight:700} .defs dd{margin:0;color:var(--soft)}
  .feature{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:14px}
  .fhead{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .fhead h3{margin:0;font-size:17px}
  .badge{font-size:11px;font-weight:800;letter-spacing:.04em;padding:3px 10px;border-radius:99px}
  .fdesc{color:var(--soft);margin:6px 0 10px;font-size:14px}
  .metrics{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline}
  .mk{color:var(--soft);font-size:13px} .metrics b{color:var(--navy)}
  .n{margin-left:auto;color:#9aa0a8;font-size:12px;font-family:ui-monospace,monospace}
  .note{margin-top:10px;font-size:13px;color:var(--soft);border-left:3px solid var(--line);padding-left:10px}
  details{margin-top:10px} summary{cursor:pointer;font-size:13px;color:var(--navy);font-weight:600}
  table.fails{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}
  table.fails th,table.fails td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
  table.fails th{color:var(--soft);font-weight:600} .got{color:#a83a3a;font-family:ui-monospace,monospace}
  .foot{color:#9aa0a8;font-size:12px;margin-top:24px;text-align:center}
  @media(max-width:640px){.defs dl{grid-template-columns:1fr} .defs dt{margin-top:6px}}
</style></head><body><div class="wrap">
  <h1>Feature scoreboard</h1>
  <p class="sub">How each part of the engine is performing, measured on labelled test cases. Every number is from a live run - nothing is hand-entered.</p>
  <div class="runbar">
    <button class="runbtn" id="runbtn" onclick="runLive()">Run tests now</button>
    <span class="runmsg" id="runmsg">Showing results generated __GENERATED__.</span>
  </div>
  <div id="summary"></div>
  <div class="defs"><h2>How to read this</h2><dl>
    <dt>Accuracy</dt><dd>Share of test cases the feature got exactly right (correct answers / all cases).</dd>
    <dt>Precision</dt><dd>When the feature makes a positive call, how often it is right. Low precision = false positives (e.g. calling an address a "country").</dd>
    <dt>Recall</dt><dd>Of the cases that should have been caught, how many were. Low recall = misses (e.g. a real country left unresolved).</dd>
    <dt>False positive</dt><dd>Saying "yes/this type" when the truth is "no" - the costliest error, because it can change data silently.</dd>
    <dt>n</dt><dd>Number of labelled cases behind the score. Small n means the number is indicative, not definitive.</dd>
    <dt>Sentinel</dt><dd>A placeholder like -1, 999, or N/A that stands for "missing/refused", not a real value.</dd>
  </dl></div>
  <div id="cards"></div>
  <div class="foot">1864 Prep - "Run tests now" re-runs the benchmark live (needs the app running). Offline, run <code>python tests/benchmark.py</code>.</div>
</div>
<script>
const BADGE={good:['#1f7a44','#e6f4ec'],ok:['#8a6d1f','#f6efd9'],weak:['#a83a3a','#f6e5e5'],na:['#8a8f98','#eef0f2']};
const DATA = __DATA__;
function fmt(v){ return (typeof v==='number' && v<=1 && v>=0) ? Math.round(v*100)+'%' : v; }
function esc(s){ return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function render(results){
  const nums=results.filter(r=>typeof r.metrics[0][1]==='number');
  const avg=nums.length? nums.reduce((a,r)=>a+r.metrics[0][1],0)/nums.length : 0;
  document.getElementById('summary').innerHTML =
    '<div class="summary">Average accuracy across measured features: <b>'+Math.round(avg*100)+'%</b><br>'+
    '<span style="color:var(--soft);font-size:13px">Green = strong (&ge;90%), amber = usable (&ge;75%), red = needs work. Open "cases to improve" to see exactly what is failing.</span></div>';
  document.getElementById('cards').innerHTML = results.map(R=>{
    const b=BADGE[R.status]||BADGE.na;
    const metrics=R.metrics.map(([k,v])=>'<span class="mk">'+esc(k)+'</span> <b>'+esc(fmt(v))+'</b>').join(' ');
    let fails='';
    if(R.fails && R.fails.length){
      const rows=R.fails.slice(0,20).map(f=>'<tr><td>'+esc(f[0])+'</td><td>'+esc(f[1])+'</td><td class="got">'+esc(f[2])+'</td></tr>').join('');
      fails='<details><summary>'+R.fails.length+' case(s) to improve</summary><table class="fails"><tr><th>input</th><th>expected</th><th>got</th></tr>'+rows+'</table></details>';
    }
    const note=R.note?'<div class="note">'+esc(R.note)+'</div>':'';
    return '<div class="feature"><div class="fhead"><h3>'+esc(R.group)+'</h3>'+
      '<span class="badge" style="color:'+b[0]+';background:'+b[1]+'">'+R.status.toUpperCase()+'</span></div>'+
      '<div class="fdesc">'+esc(R.desc)+'</div>'+
      '<div class="metrics">'+metrics+' <span class="n">n='+R.n+'</span></div>'+note+fails+'</div>';
  }).join('');
}
async function runLive(){
  const btn=document.getElementById('runbtn'), msg=document.getElementById('runmsg');
  btn.disabled=true; const t0=Date.now(); msg.textContent='Running the benchmark...';
  try{
    const res=await fetch('/api/benchmark',{method:'POST'});
    if(!res.ok) throw new Error('HTTP '+res.status);
    const data=await res.json();
    render(data.results);
    msg.textContent='Ran live just now in '+((Date.now()-t0)/1000).toFixed(1)+'s.';
  }catch(e){
    msg.textContent='Could not run live (is the app running?). Showing the last generated results. ['+e.message+']';
  }finally{ btn.disabled=false; }
}
render(DATA);
</script></body></html>'''


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
