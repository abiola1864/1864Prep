"""Render the two verification views into a self-contained HTML review report.

Consumes the JSON emitted by gen_review.py (column overview + spot-check pool)
and writes a single HTML file. The report is the CONSENT step: it shows what
cleaning would change, before anything is saved.
"""
import json
import sys
from pathlib import Path

DATA = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/review_data.json"))
OUT = sys.argv[2] if len(sys.argv) > 2 else "/mnt/user-data/outputs/cleaning_review.html"

meta = DATA["meta"]
total_changes = sum(c["n_changed"] for c in DATA["overview"])
total_flagged = sum(c["n_flagged"] for c in DATA["overview"])
cols_touched = sum(1 for c in DATA["overview"] if c["n_changed"] > 0)

payload = json.dumps(DATA).replace("</", "<\\/")

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cleaning review — verify before saving</title>
<style>
  :root{
    --ink:#1b2431; --ink-soft:#5a6675; --faint:#9aa4b2;
    --paper:#faf9f6; --card:#ffffff; --line:#e8e4dc; --line-soft:#f0ede6;
    --accent:#2f6f57;            /* verified / ok */
    --accent-bg:#e7f1ec;
    --change:#b5761c;            /* proposed change / attention */
    --change-bg:#f8efdc;
    --flag:#a83a3a; --flag-bg:#f7e7e5;
    --mono:"SFMono-Regular",ui-monospace,Menlo,Consolas,monospace;
    --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.5;
       -webkit-font-smoothing:antialiased}
  @media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
  .wrap{max-width:1000px;margin:0 auto;padding:28px 22px 90px}

  header h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}
  header p{margin:0;color:var(--ink-soft);font-size:14px;max-width:64ch}
  .consent-note{margin-top:14px;background:var(--accent-bg);border:1px solid #cfe3d8;border-radius:10px;
       padding:11px 14px;font-size:13px;color:#1f4d3c;display:flex;gap:9px;align-items:flex-start}
  .consent-note b{color:var(--accent)}

  .stats{display:flex;gap:10px;margin:18px 0 6px;flex-wrap:wrap}
  .stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 15px;min-width:120px}
  .stat .n{font-size:20px;font-weight:700;font-family:var(--mono)}
  .stat .l{font-size:11.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.08em}
  .stat.change .n{color:var(--change)} .stat.flag .n{color:var(--flag)} .stat.ok .n{color:var(--accent)}

  .tabs{display:flex;gap:4px;margin:22px 0 0;border-bottom:1px solid var(--line)}
  .tab{border:none;background:none;font:inherit;font-size:14px;font-weight:600;color:var(--faint);
       padding:10px 16px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
  .tab.on{color:var(--ink);border-bottom-color:var(--ink)}
  .view{display:none;padding-top:18px} .view.on{display:block}

  /* ---- column overview ---- */
  .col{background:var(--card);border:1px solid var(--line);border-radius:11px;margin-bottom:10px;overflow:hidden}
  .col-head{display:grid;grid-template-columns:1.4fr .9fr 1fr 1fr 26px;gap:12px;align-items:center;
       padding:13px 16px;cursor:pointer}
  .col-head:hover{background:var(--line-soft)}
  .col-name{font-family:var(--mono);font-weight:600;font-size:13.5px}
  .col-type{font-size:12px;color:var(--ink-soft)}
  .badge{font-size:11.5px;font-weight:700;font-family:var(--mono);padding:2px 8px;border-radius:20px;justify-self:start}
  .badge.change{background:var(--change-bg);color:var(--change)}
  .badge.flag{background:var(--flag-bg);color:var(--flag)}
  .badge.none{background:var(--line-soft);color:var(--faint)}
  .chev{color:var(--faint);transition:transform .15s;justify-self:center}
  .col.open .chev{transform:rotate(90deg)}
  .col-body{display:none;padding:2px 16px 16px;border-top:1px solid var(--line-soft)}
  .col.open .col-body{display:block}
  .ex{display:flex;align-items:center;gap:10px;padding:7px 0;font-family:var(--mono);font-size:12.5px;
      border-bottom:1px dashed var(--line-soft)}
  .ex:last-child{border-bottom:none}
  .ex .b{color:var(--ink-soft);text-decoration:line-through;text-decoration-color:#c9b48a}
  .ex .arr{color:var(--change)}
  .ex .a{color:var(--accent);font-weight:600}
  .ex-empty{color:var(--faint);font-size:12.5px;padding:8px 0;font-style:italic}

  /* ---- spot-check ---- */
  .sc-bar{display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}
  .sc-bar .verified{font-size:13px;color:var(--ink-soft)} .sc-bar .verified b{color:var(--accent)}
  .btn{border:1px solid var(--ink);background:var(--ink);color:#fff;font:inherit;font-size:13px;font-weight:600;
       padding:8px 15px;border-radius:8px;cursor:pointer}
  .btn:hover{background:#0f1620}
  .btn.ghost{background:#fff;color:var(--ink);border-color:var(--line)}
  .btn.ghost:hover{border-color:var(--ink)}
  .btn:disabled{opacity:.45;cursor:not-allowed}
  .rec{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:12px 14px;margin-bottom:10px}
  .rec-top{display:flex;align-items:center;gap:10px;margin-bottom:8px}
  .rec-id{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
  .chk{margin-left:auto;display:inline-flex;align-items:center;gap:7px;font-size:12.5px;color:var(--ink-soft);cursor:pointer;user-select:none}
  .chk input{width:15px;height:15px;accent-color:var(--accent)}
  .rec.ok{border-color:#cfe3d8;background:#fcfefd}
  .cells{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px 18px}
  .cell{font-size:12.5px;display:flex;flex-direction:column;gap:1px;padding:4px 0}
  .cell .k{font-size:10.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.06em}
  .cell .v{font-family:var(--mono);font-size:12.5px}
  .cell.changed .v .b{color:var(--ink-soft);text-decoration:line-through;text-decoration-color:#c9b48a}
  .cell.changed .v .a{color:var(--accent);font-weight:600}
  .cell.changed{background:linear-gradient(0deg,var(--change-bg),transparent);border-radius:6px;padding:4px 8px}

  /* ---- consent gate ---- */
  .gate{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);
        padding:12px 22px;display:flex;align-items:center;gap:16px;box-shadow:0 -4px 16px rgba(20,25,35,.05)}
  .gate .inner{max-width:1000px;margin:0 auto;display:flex;align-items:center;gap:16px;width:100%}
  .gate label{display:inline-flex;align-items:center;gap:9px;font-size:13.5px;cursor:pointer}
  .gate label input{width:17px;height:17px;accent-color:var(--accent)}
  .gate .sp{flex:1}
  .toast{position:fixed;bottom:74px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;
         padding:10px 18px;border-radius:8px;font-size:13.5px;font-weight:600;opacity:0;pointer-events:none;transition:opacity .2s}
  .toast.show{opacity:1}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Review the cleaning before it's saved</h1>
    <p>Cleaning is only a proposal until you approve it. Below is exactly what would change,
       column by column, plus a random sample of real records to spot-check. Nothing is
       written to your file until you approve.</p>
    <div class="consent-note"><span>✓</span>
      <div><b>Your data isn't changed yet.</b> These are suggestions. Anything uncertain is flagged,
      not applied. You can approve, or reject and adjust — the choice, and the data, stay yours.</div>
    </div>
  </header>

  <div class="stats" id="stats"></div>

  <div class="tabs">
    <button class="tab on" data-view="cols">All columns · before &amp; after</button>
    <button class="tab" data-view="spot">Spot-check · random records</button>
  </div>

  <section class="view on" id="view-cols"></section>

  <section class="view" id="view-spot">
    <div class="sc-bar">
      <button class="btn ghost" id="shuffle">New random sample</button>
      <span class="verified">Verified <b id="vcount">0</b> / <span id="vtotal">0</span> in this sample</span>
    </div>
    <div id="records"></div>
  </section>
</div>

<div class="gate">
  <div class="inner">
    <label><input type="checkbox" id="reviewed"> I've reviewed the proposed changes</label>
    <span class="sp"></span>
    <button class="btn ghost" onclick="reject()">Reject &amp; adjust</button>
    <button class="btn" id="approve" disabled onclick="approve()">Approve &amp; save cleaned file</button>
  </div>
</div>
<div class="toast" id="toast"></div>

<script id="data" type="application/json">__PAYLOAD__</script>
<script>
  const DATA = JSON.parse(document.getElementById('data').textContent);
  const $ = (s,r=document)=>r.querySelector(s);
  const esc = s => (s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

  // ---- stats ----
  const changes = DATA.overview.reduce((a,c)=>a+c.n_changed,0);
  const flagged = DATA.overview.reduce((a,c)=>a+c.n_flagged,0);
  const touched = DATA.overview.filter(c=>c.n_changed>0).length;
  $('#stats').innerHTML = [
    ['ok', DATA.meta.rows.toLocaleString(), 'rows'],
    ['ok', DATA.meta.cols, 'columns'],
    ['change', touched, 'columns changed'],
    ['change', changes.toLocaleString(), 'values changed'],
    ['flag', flagged.toLocaleString(), 'flagged for you'],
  ].map(([k,n,l])=>`<div class="stat ${k}"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');

  // ---- column overview ----
  $('#view-cols').innerHTML = DATA.overview.map((c,i)=>{
    const badge = c.n_flagged>0
      ? `<span class="badge flag">${c.n_flagged} flagged</span>`
      : (c.n_changed>0 ? `<span class="badge change">${c.n_changed} changed · ${c.pct_changed}%</span>`
                       : `<span class="badge none">no change</span>`);
    const ex = c.examples.length
      ? c.examples.map(e=>`<div class="ex"><span class="b">${esc(e.before)||'∅'}</span>
           <span class="arr">→</span><span class="a">${esc(e.after)||'∅'}</span></div>`).join('')
      : `<div class="ex-empty">No value changes proposed for this column.</div>`;
    return `<div class="col" data-i="${i}">
      <div class="col-head" onclick="this.parentNode.classList.toggle('open')">
        <span class="col-name">${esc(c.column)}</span>
        <span class="col-type">read as: ${esc(c.read_as)}</span>
        ${badge}<span></span>
        <span class="chev">▸</span>
      </div>
      <div class="col-body">${ex}</div>
    </div>`;
  }).join('');

  // ---- spot-check ----
  const SHOW = 8;
  let sample = [];
  function draw(){
    const pool = DATA.pool.records.slice();
    for(let i=pool.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[pool[i],pool[j]]=[pool[j],pool[i]];}
    sample = pool.slice(0, SHOW);
    $('#records').innerHTML = sample.map((r,ri)=>{
      const cells = r.cells.map(c=>{
        const v = c.changed
          ? `<span class="b">${esc(c.before)||'∅'}</span> → <span class="a">${esc(c.after)||'∅'}</span>`
          : `${esc(c.after)||'∅'}`;
        return `<div class="cell ${c.changed?'changed':''}"><span class="k">${esc(c.column)}</span><span class="v">${v}</span></div>`;
      }).join('');
      return `<div class="rec" data-ri="${ri}">
        <div class="rec-top"><span class="rec-id">record #${r.row}</span>
          <label class="chk"><input type="checkbox" onchange="mark(${ri},this.checked)"> looks right</label></div>
        <div class="cells">${cells}</div></div>`;
    }).join('');
    $('#vtotal').textContent = sample.length; $('#vcount').textContent = 0;
  }
  window.mark = (ri,ok)=>{
    const rec = document.querySelector(`.rec[data-ri="${ri}"]`);
    rec.classList.toggle('ok', ok);
    $('#vcount').textContent = document.querySelectorAll('.rec.ok').length;
  };
  $('#shuffle').onclick = draw;

  // ---- tabs ----
  document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));
    $('#view-cols').classList.toggle('on', t.dataset.view==='cols');
    $('#view-spot').classList.toggle('on', t.dataset.view==='spot');
  });

  // ---- consent gate ----
  $('#reviewed').onchange = e => $('#approve').disabled = !e.target.checked;
  function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800);}
  window.approve = ()=>toast('Approved — cleaned file would be saved now.');
  window.reject  = ()=>toast('Rejected — nothing saved. Adjust the mappings and re-run.');

  draw();
</script>
</body>
</html>"""

Path(OUT).parent.mkdir(parents=True, exist_ok=True)
Path(OUT).write_text(HTML.replace("__PAYLOAD__", payload), encoding="utf-8")
print(f"wrote {OUT}")
print(f"summary: {meta['rows']} rows, {meta['cols']} cols, {cols_touched} cols changed, "
      f"{total_changes} values changed, {total_flagged} flagged")
