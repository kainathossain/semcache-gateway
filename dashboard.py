"""Dashboard. `serve(metrics)` runs a live page (polls /api/stats every 2s);
`export_html(metrics, path)` writes a self-contained static snapshot."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from metrics import MetricsStore

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Gateway Dashboard</title>
<style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e4e4de;--a:#2f6fed;--b:#c9ccd3;--g:#1f9d6b;--o:#e08a1e}
@media(prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececea;--mut:#9a9a94;--card:#1f1f22;--line:#323236;--b:#4a4d57}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;padding:20px;max-width:1100px;margin:auto}
h1{font-size:20px;margin:0 0 16px}h2{font-size:13px;color:var(--mut);margin:0 0 10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--mut);font-size:12px}
.two{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:12.5px}td,th{padding:5px 6px;border-bottom:1px solid var(--line);text-align:left}
td.q{max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tag{padding:1px 7px;border-radius:9px;font-size:11px;background:var(--line)}.hit{background:var(--g);color:#fff}.large,.escalated{background:var(--o);color:#fff}
svg{width:100%;height:auto}.leg{font-size:12px;color:var(--mut)}
</style></head><body><h1>Semantic cache &amp; routing gateway</h1><div id="app">Waiting for data…</div>
<script>
const EMBED=__DATA__;
const $=s=>document.querySelector(s), usd=v=>"$"+(v<1?v.toFixed(4):v.toFixed(2)), ms=v=>Math.round(v*1000)+" ms", pct=v=>(v*100).toFixed(1)+"%";
function bars(series){const W=520,H=160,n=series.length,m=Math.max(...series.map(s=>s.baseline),1e-9),bw=W/n;
 return `<svg viewBox="0 0 ${W} ${H+16}" role="img" aria-label="Cost per time bucket">`+series.map((s,i)=>{
 const hb=s.baseline/m*H,h=s.cost/m*H;return `<rect x="${i*bw+2}" y="${H-hb}" width="${bw-4}" height="${hb}" fill="var(--b)"/><rect x="${i*bw+2}" y="${H-h}" width="${bw-4}" height="${h}" fill="var(--a)"/>`}).join("")+
 `</svg><div class="leg">Grey: baseline (always large model) &nbsp; Blue: actual spend</div>`}
function line(series){const W=520,H=160,n=series.length;const pts=series.map((s,i)=>`${(i/(Math.max(n-1,1)))*W},${H-s.hit_rate*H}`).join(" ");
 return `<svg viewBox="0 0 ${W} ${H+16}" role="img" aria-label="Hit rate over time"><polyline points="${pts}" fill="none" stroke="var(--g)" stroke-width="2.5"/></svg><div class="leg">Cache hit rate over time (0–100%)</div>`}
function split(o,n){const c={hit:"var(--g)",small:"var(--a)",large:"var(--o)",escalated:"#c4452d"};let x=0;
 const segs=Object.entries(o).map(([k,v])=>{const w=v/n*100,r=`<div style="width:${w}%;background:${c[k]||'#888'}" title="${k}: ${v}"></div>`;return r}).join("");
 const lg=Object.entries(o).map(([k,v])=>`<span style="color:${c[k]}">&#9632;</span> ${k} ${pct(v/n)}`).join(" &nbsp; ");
 return `<div style="display:flex;height:26px;border-radius:6px;overflow:hidden">${segs}</div><div class="leg" style="margin-top:8px">${lg}</div>`}
function render(d){if(!d||!d.requests){$("#app").textContent="No requests yet.";return}
 const k=(l,v)=>`<div class="card kpi"><b>${v}</b><span>${l}</span></div>`;
 $("#app").innerHTML=`<div class="grid">${k("Requests",d.requests)}${k("Cache hit rate",pct(d.hit_rate))}${k("Spend",usd(d.cost))}${k("Baseline (all large)",usd(d.baseline_cost))}${k("Savings",pct(d.savings_pct)+" ("+usd(d.savings)+")")}${k("Cost / 1k requests",usd(d.cost_per_1k))}</div>
 <div class="grid">${k("Latency p50",ms(d.latency.p50))}${k("Latency p95",ms(d.latency.p95))}${k("p50 on hit",ms(d.latency.hit_p50))}${k("p50 on miss",ms(d.latency.miss_p50))}</div>
 <div class="two"><div class="card"><h2>Spend vs baseline</h2>${bars(d.series)}</div><div class="card"><h2>Hit rate</h2>${line(d.series)}</div></div>
 <div class="card" style="margin-bottom:12px"><h2>Where requests were served</h2>${split(d.outcomes,d.requests)}</div>
 <div class="card"><h2>Recent requests</h2><table><tr><th>#</th><th>Query</th><th>Outcome</th><th>Sim</th><th>Cost</th><th>Latency</th></tr>${d.recent.map(r=>`<tr><td>${r.id}</td><td class="q">${r.query.replace(/</g,"&lt;")}</td><td><span class="tag ${r.outcome}">${r.outcome}</span></td><td>${r.similarity.toFixed(2)}</td><td>${usd(r.cost)}</td><td>${ms(r.latency_s)}</td></tr>`).join("")}</table></div>`}
async function tick(){try{render(await (await fetch("/api/stats")).json())}catch(e){}}
if(EMBED){render(EMBED)}else{tick();setInterval(tick,2000)}
</script></body></html>"""


def export_html(metrics: MetricsStore, path: str = "dashboard.html") -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(metrics.stats()).replace("</", "<\\/")))
    return path


def serve(metrics: MetricsStore, port: int = 8765, background: bool = False):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/stats"):
                body, ctype = json.dumps(metrics.stats()).encode(), "application/json"
            else:
                body, ctype = PAGE.replace("__DATA__", "null").encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    if background:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    print(f"Dashboard on http://127.0.0.1:{port}")
    srv.serve_forever()