"""Interactive scouting explorer -> outputs/beat_the_rush_explorer.html (open in any browser)."""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
COLORS = {"WR": "#2a78d6", "TE": "#1baf7a", "RB": "#eb6834"}


def main():
    rec = pd.read_csv(OUT / "receivers.csv")
    d = rec[(rec.n_man >= 40) & (rec.n_zone >= 60)].copy()

    fig = go.Figure()
    for pos, col in COLORS.items():
        s = d[d.pos == pos]
        fig.add_trace(go.Scatter(
            x=s.broe_man * 100, y=s.broe_zone * 100, mode="markers", name=pos,
            marker=dict(size=11, color=col, line=dict(color="#fcfcfb", width=1.5)),
            customdata=s[["name", "team", "routes", "beat_rate", "x_beat", "broe", "med_t_win", "targets"]],
            hovertemplate=("<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                           "routes: %{customdata[2]} · targets: %{customdata[7]}<br>"
                           "beat-the-rush: %{customdata[3]:.0%} (expected %{customdata[4]:.0%})<br>"
                           "over expected: %{customdata[5]:+.1%}<br>"
                           "median time to win: %{customdata[6]:.1f}s<br>"
                           "vs man: %{x:+.1f} pts · vs zone: %{y:+.1f} pts<extra></extra>"),
        ))
    fig.add_hline(y=0, line_color="#52514e", line_width=1)
    fig.add_vline(x=0, line_color="#52514e", line_width=1)
    for x, y, t in [(0.98, 0.98, "Beats everything"), (0.02, 0.98, "Zone-beater only → play him man"),
                    (0.98, 0.02, "Man-beater only → play him zone"), (0.02, 0.02, "Loses the race either way")]:
        fig.add_annotation(x=x, y=y, xref="paper", yref="paper", text=f"<b>{t}</b>", showarrow=False,
                           xanchor="right" if x > 0.5 else "left", yanchor="top" if y > 0.5 else "bottom",
                           font=dict(color="#52514e", size=12))
    fig.update_layout(
        title="Beat the Rush: the man/zone tell (hover any player; click legend to filter)",
        xaxis_title="vs MAN: beat-the-rush rate over expected (pct pts)",
        yaxis_title="vs ZONE: beat-the-rush rate over expected (pct pts)",
        template="simple_white", plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb", height=700,
        legend=dict(orientation="h", y=1.04, x=0),
    )

    t = rec.sort_values("broe", ascending=False)
    table = go.Figure(go.Table(
        header=dict(values=["Player", "Pos", "Team", "Routes", "Beat-rush %", "Expected %",
                            "Over exp.", "vs Man", "vs Zone", "Median t_win (s)"],
                    fill_color="#2a78d6", font=dict(color="white"), align="left"),
        cells=dict(values=[t.name, t.pos, t.team, t.routes, (t.beat_rate * 100).round(1),
                           (t.x_beat * 100).round(1), (t.broe * 100).round(1),
                           (t.broe_man * 100).round(1), (t.broe_zone * 100).round(1), t.med_t_win],
                   fill_color="#fcfcfb", align="left"),
    ))
    table.update_layout(title="All receivers (min 100 routes), sorted by Beat-the-Rush Over Expected",
                        height=900, paper_bgcolor="#fcfcfb")

    html = ("<html><head><meta charset='utf-8'><title>Beat the Rush Explorer</title></head>"
            "<body style='background:#fcfcfb;font-family:sans-serif;max-width:1100px;margin:auto'>"
            + fig.to_html(full_html=False, include_plotlyjs="cdn")
            + table.to_html(full_html=False, include_plotlyjs=False) + "</body></html>")
    (OUT / "beat_the_rush_explorer.html").write_text(html)
    print("explorer ->", OUT / "beat_the_rush_explorer.html")


if __name__ == "__main__":
    main()
