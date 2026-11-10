"""Build docs/index.html: interactive Chip Tax scout tool (single self-contained page)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "index.html"
SNAP = {"ball_snap", "autoevent_ballsnap"}
END = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run"}


def r1(a):
    return [round(float(v), 1) for v in a]


def load_players():
    p = pd.read_csv(ROOT / "outputs" / "chip_tax_by_player.csv")
    p = p[p.pos.isin(["TE", "RB"])].copy()
    pff = pd.read_csv(ROOT / "data" / "pffScoutingData.csv", usecols=["nflId", "pff_role", "pff_blockType"])
    pff = pff[pff.pff_role.isin(["Pass Route", "Pass Block"])]
    rate = pff.groupby("nflId").pff_blockType.apply(lambda s: (s == "CH").mean())
    p["chip_rate"] = p.nflId.map(rate).fillna(0) * 100
    return p.sort_values("chip_tax")


def load_routes(ids):
    cr = pd.read_parquet(ROOT / "outputs" / "chip_routes.parquet", columns=["gameId", "playId", "nflId", "chip"])
    cr = cr[cr.nflId.isin(ids)]
    out = {int(i): [] for i in ids}
    for gid, g in cr.groupby("gameId"):
        f = ROOT / "data" / "tracking" / f"tracking_{gid}.csv"
        if not f.exists():
            continue
        t = pd.read_csv(f, usecols=["playId", "nflId", "frameId", "team", "playDirection", "x", "y", "event"])
        t = t[t.playId.isin(g.playId.unique())]
        left = t.playDirection == "left"
        t.loc[left, "x"] = 120 - t.loc[left, "x"]
        t.loc[left, "y"] = 53.3 - t.loc[left, "y"]
        for pid, p in t.groupby("playId"):
            ev = p.drop_duplicates("frameId").set_index("frameId").event
            snaps = ev[ev.isin(SNAP)].index
            if len(snaps) == 0:
                continue
            sf = snaps.min()
            ends = ev[(ev.index > sf) & ev.isin(END)].index
            ef = min(ends.min() if len(ends) else sf + 30, sf + 30)
            ball = p[(p.team == "football") & (p.frameId == sf)]
            if ball.empty:
                continue
            los, by = ball.x.iloc[0], ball.y.iloc[0]
            for r in g[g.playId == pid].itertuples():
                me = p[p.nflId == r.nflId].sort_values("frameId")
                me = me[(me.frameId >= sf) & (me.frameId <= ef)]
                if me.empty or me.frameId.iloc[0] != sf:
                    continue
                y0 = me.y.iloc[0]
                dx = me.x.values - los
                lat = me.y.values - y0
                if y0 > by:
                    lat = -lat
                fr = me.frameId.values
                i2 = np.where(fr == sf + 20)[0]
                keep = np.r_[np.arange(0, len(dx), 2), len(dx) - 1] if len(dx) > 1 else [0]
                keep = sorted(set(int(k) for k in keep))
                out[int(r.nflId)].append(dict(c=int(bool(r.chip)), x=r1(lat[keep]), y=r1(dx[keep]),
                                              d2=round(float(dx[i2[0]]), 2) if len(i2) else None))
    return out


def main():
    players = load_players()
    routes = load_routes(players.nflId.unique())
    data = []
    for r in players.itertuples():
        data.append(dict(id=int(r.nflId), name=r.name, pos=r.pos, chips=int(r.chips),
                         routes=int(r.routes_no_chip), raw=round(float(r.depth_tax_yds), 2),
                         tax=round(float(r.chip_tax), 2), sd=round(float(r.chip_tax_sd), 2),
                         pos_mean=round(float(r.pos_mean), 2), verdict=r.verdict,
                         chip_rate=round(float(r.chip_rate), 1), tracks=routes.get(int(r.nflId), [])))
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB), {len(data)} players, "
          f"{sum(len(d['tracks']) for d in data)} routes")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Chip Tax: Scout Tool</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
body{margin:0;background:#fcfcfb;color:#0b0b0b;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px 40px}
h1{margin:0 0 6px;font-size:28px}
.intro{color:#52514e;margin:0 0 18px}
select{font-size:15px;padding:6px 8px;max-width:100%;border:1px solid #ccc;border-radius:6px;background:#fff}
.card{border:1px solid #e3e2df;border-radius:10px;background:#fff;padding:14px 18px;margin:16px 0}
.card h2{margin:0 0 4px;font-size:22px}
.pos{font-size:13px;font-weight:600;padding:2px 8px;border-radius:10px;color:#fff;vertical-align:middle;margin-left:6px}
.stats{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:10px}
.stat .k{font-size:12px;color:#52514e;text-transform:uppercase;letter-spacing:.03em}
.stat .v{font-size:20px;font-weight:600}
.verdict{margin-top:10px;color:#52514e}
.grid{display:grid;grid-template-columns:3fr 2fr;gap:16px}
@media (max-width:820px){.grid{grid-template-columns:1fr}}
.panel h3{margin:0 0 4px;font-size:16px}.panel p{margin:0 0 6px;color:#52514e;font-size:13px}
footer{margin-top:24px;color:#52514e;font-size:13px}footer a{color:#2a78d6}
</style></head><body><div class="wrap">
<h1>The Chip Tax: Scout Tool</h1>
<div style="background:#fff4ec;border-left:4px solid #eb6834;padding:12px 16px;margin:10px 0 14px;border-radius:6px;font-size:15px;line-height:1.5"><b>The Chip Tax in one line:</b> a chip halves the chipped rusher&#39;s pressure (13% &rarr; 6%), but costs the chipper 3.1 yds of route depth at 2 s and a third of his targets (TE &asymp; 4.7 yds, RB &asymp; 1.7). Each player is compared <b>with himself</b>. Cheap chippers don&#39;t chip less; they <b>hit the rusher sooner (first 0.7 s) and get off</b>. <a href="https://github.com/HivanshD/NFLxAWSDatabowlNYU#readme">Full analysis, methods and checks &rarr;</a></div>
<p class="intro">Pick a tight end or running back to see what a chip block costs his route (2021 NFL Weeks 1-8, NGS tracking + PFF).</p>
<select id="pick"></select>
<div class="card" id="card"></div>
<div class="grid">
 <div class="panel"><h3>Route tree, snap to throw (max 3.0 s)</h3>
  <p><span style="color:#ff8a3d;font-weight:700">Orange</span> = routes after a chip, grey/white = normal routes. Dashed lines = mean depth at 2.0 s. Offense moves up; outside is to the right.</p>
  <div id="tree" style="height:620px"></div></div>
 <div class="panel"><h3>League view</h3>
  <p>Chip rate vs Chip Tax relative to position average (higher = pays less). Selected player ringed.</p>
  <div id="league" style="height:460px"></div></div>
</div>
<footer>Method, data and code: <a href="https://github.com/HivanshD/NFLxAWSDatabowlNYU">github.com/HivanshD/NFLxAWSDatabowlNYU</a> (see README).</footer>
</div>
<script>
const DATA = __DATA__;
const ORANGE = "#ff8a3d", TURF = "#2e6b3a", COL = {TE: "#2a78d6", RB: "#eb6834"};
const sel = document.getElementById("pick");
DATA.forEach((d, i) => {
  const o = document.createElement("option");
  o.value = i; o.textContent = `${d.name} (${d.pos}) - Chip Tax ${d.tax.toFixed(1)} yds`;
  sel.appendChild(o);
});
function mean(a) { return a.length ? a.reduce((s, v) => s + v, 0) / a.length : NaN; }
function fmt(v, n = 1) { return isNaN(v) ? "n/a" : (v > 0 ? "+" : "") + v.toFixed(n); }

function card(d) {
  const tot = d.chips + d.routes;
  document.getElementById("card").innerHTML = `
   <h2>${d.name}<span class="pos" style="background:${COL[d.pos]}">${d.pos}</span></h2>
   <div class="stats">
    <div class="stat"><div class="k">Chip Tax (shrunk)</div><div class="v">${d.tax.toFixed(1)} yds</div></div>
    <div class="stat"><div class="k">Raw gap</div><div class="v">${d.raw.toFixed(1)} yds</div></div>
    <div class="stat"><div class="k">${d.pos} average</div><div class="v">${d.pos_mean.toFixed(1)} yds</div></div>
    <div class="stat"><div class="k">Chips / routes</div><div class="v">${d.chips} / ${tot}</div></div>
    <div class="stat"><div class="k">Chip rate</div><div class="v">${d.chip_rate.toFixed(1)}%</div></div>
   </div>
   <div class="verdict">Verdict: <b>${d.verdict}</b>. Chip Tax = how much shallower his route is at 2.0 s after a chip (yds, shrunk toward the ${d.pos} average; &plusmn;${d.sd.toFixed(1)}). Chip rate = share of his pass snaps with a chip block.</div>`;
}

function tree(d) {
  const lines = {0: {x: [], y: []}, 1: {x: [], y: []}};
  const d2 = {0: [], 1: []};
  let ymin = -3, ymax = 12;
  d.tracks.forEach(t => {
    const L = lines[t.c];
    L.x.push(...t.x, null); L.y.push(...t.y, null);
    if (t.d2 !== null) d2[t.c].push(t.d2);
    ymin = Math.min(ymin, ...t.y); ymax = Math.max(ymax, ...t.y);
  });
  ymin = Math.max(Math.floor(ymin) - 1, -12); ymax = Math.min(Math.ceil(ymax) + 1, 30);
  const xr = [-15, 20];
  const shapes = [];
  for (let yd = Math.ceil(ymin / 5) * 5; yd <= ymax; yd += 5)
    shapes.push({type: "line", x0: xr[0], x1: xr[1], y0: yd, y1: yd, line: {color: "rgba(255,255,255,0.45)", width: 1}, layer: "below"});
  shapes.push({type: "line", x0: xr[0], x1: xr[1], y0: 0, y1: 0, line: {color: "white", width: 4}, layer: "below"});
  const mN = mean(d2[0]), mC = mean(d2[1]);
  const ann = [{x: xr[0] + 0.5, y: 0, text: "<b>LOS</b>", showarrow: false, font: {color: "white"}, xanchor: "left", yanchor: "bottom"},
               {x: xr[1] - 0.5, y: ymin + 0.3, text: "outside →", showarrow: false, font: {color: "rgba(255,255,255,0.75)"}, xanchor: "right", yanchor: "bottom"}];
  if (!isNaN(mN)) { shapes.push({type: "line", x0: xr[0], x1: xr[1], y0: mN, y1: mN, line: {color: "white", width: 2, dash: "dash"}});
    ann.push({x: xr[1] - 0.5, y: mN, text: `<b>normal ${mN.toFixed(1)} yds</b>`, showarrow: false, font: {color: "white"}, xanchor: "right", yanchor: "bottom"}); }
  if (!isNaN(mC)) { shapes.push({type: "line", x0: xr[0], x1: xr[1], y0: mC, y1: mC, line: {color: ORANGE, width: 2.5, dash: "dash"}});
    ann.push({x: xr[1] - 0.5, y: mC, text: `<b>chip ${mC.toFixed(1)} yds</b>`, showarrow: false, font: {color: ORANGE}, xanchor: "right", yanchor: "top"}); }
  const traces = [
    {x: lines[0].x, y: lines[0].y, mode: "lines", line: {color: "rgba(255,255,255,0.3)", width: 1}, name: `normal (${d.routes})`, hoverinfo: "skip"},
    {x: lines[1].x, y: lines[1].y, mode: "lines", line: {color: ORANGE, width: 2.5}, name: `chip (${d.chips})`, hoverinfo: "skip"}];
  Plotly.react("tree", traces, {
    paper_bgcolor: "#fcfcfb", plot_bgcolor: TURF, margin: {l: 45, r: 10, t: 10, b: 30}, shapes, annotations: ann,
    xaxis: {range: xr, zeroline: false, showgrid: false, title: {text: "lateral yds from snap spot", font: {size: 11}}},
    yaxis: {range: [ymin, ymax], zeroline: false, showgrid: false, title: {text: "yds past LOS", font: {size: 11}}},
    legend: {orientation: "h", y: 1.0, x: 0, bgcolor: "rgba(0,0,0,0.25)", font: {color: "white"}}, showlegend: true
  }, {displayModeBar: false, responsive: true});
}

function league(d) {
  const traces = ["TE", "RB"].map(p => {
    const s = DATA.filter(e => e.pos === p);
    return {x: s.map(e => e.chip_rate), y: s.map(e => e.tax - e.pos_mean), text: s.map(e => `${e.name} (${p})<br>chip rate ${e.chip_rate.toFixed(1)}%<br>tax ${e.tax.toFixed(1)} vs avg ${e.pos_mean.toFixed(1)}`),
      mode: "markers", name: p, marker: {color: COL[p], size: 9, opacity: 0.75}, hoverinfo: "text"};
  });
  traces.push({x: [d.chip_rate], y: [d.tax - d.pos_mean], mode: "markers+text", text: [d.name], textposition: "top center",
    marker: {color: COL[d.pos], size: 16, line: {color: "#0b0b0b", width: 2.5}}, name: "selected", hoverinfo: "skip", showlegend: false, textfont: {color: "#0b0b0b", size: 12}});
  const xs = DATA.map(e => e.chip_rate), ys = DATA.map(e => e.tax - e.pos_mean);
  const xm = mean(xs), x0 = Math.min(...xs) - 1, x1 = Math.max(...xs) + 1;
  const ya = Math.max(...ys.map(Math.abs)) * 1.25;
  const q = (x, y, t, xa, yan) => ({x, y, text: t, showarrow: false, font: {size: 10, color: "#52514e"}, xanchor: xa, yanchor: yan});
  Plotly.react("league", traces, {
    paper_bgcolor: "#fcfcfb", plot_bgcolor: "#fcfcfb", margin: {l: 50, r: 10, t: 10, b: 45},
    xaxis: {range: [x0, x1], title: {text: "chip rate (% of pass snaps)", font: {size: 11}}, gridcolor: "#eee", zeroline: false},
    yaxis: {range: [-ya, ya], title: {text: "Chip Tax minus position avg (yds)", font: {size: 11}}, gridcolor: "#eee", zeroline: false},
    shapes: [{type: "line", x0, x1, y0: 0, y1: 0, line: {color: "#999", width: 1}},
             {type: "line", x0: xm, x1: xm, y0: -ya, y1: ya, line: {color: "#999", width: 1, dash: "dot"}}],
    annotations: [q(x1, ya, "Workhorse: chip a lot, pay little", "right", "top"),
                  q(x0, ya, "Light use, pays little", "left", "top"),
                  q(x1, -ya, "Chip a lot, pay a lot", "right", "bottom"),
                  q(x0, -ya, "Rarely chips, pays a lot", "left", "bottom")],
    legend: {orientation: "h", y: -0.18, x: 0}
  }, {displayModeBar: false, responsive: true});
}

function show(i) { const d = DATA[i]; card(d); tree(d); league(d); }
sel.addEventListener("change", e => show(+e.target.value));
show(0);
</script></body></html>
"""

if __name__ == "__main__":
    main()
