"""Dark terminal-style Plotly charts."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

COLORS = {
    "background": "#0E1117",
    "panel": "#151A23",
    "text": "#E6EAF0",
    "muted": "#8993A4",
    "green": "#16C784",
    "red": "#EA3943",
    "blue": "#3861FB",
    "grid": "#252C38",
}


def _layout(figure: go.Figure, *, height: int = 320) -> go.Figure:
    figure.update_layout(
        height=height,
        paper_bgcolor=COLORS["panel"],
        plot_bgcolor=COLORS["panel"],
        font={"family": "IBM Plex Mono, monospace", "color": COLORS["text"], "size": 12},
        margin={"l": 16, "r": 16, "t": 38, "b": 16},
        xaxis={"gridcolor": COLORS["grid"], "zerolinecolor": COLORS["grid"]},
        yaxis={"gridcolor": COLORS["grid"], "zerolinecolor": COLORS["grid"]},
        legend={"bgcolor": "rgba(0,0,0,0)"},
    )
    return figure


def gmp_leaderboard(frame: pd.DataFrame) -> go.Figure:
    valid = frame.dropna(subset=["GMP %"]).sort_values("GMP %", ascending=True).tail(10)
    figure = px.bar(
        valid,
        x="GMP %",
        y="IPO Name",
        orientation="h",
        color="GMP %",
        color_continuous_scale=[COLORS["blue"], COLORS["green"]],
        title="GMP LEADERS",
        text_auto=".1f",
    )
    return _layout(figure)


def gmp_trend(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    if not frame.empty:
        for name, group in frame.groupby("IPO Name"):
            figure.add_trace(
                go.Scatter(
                    x=group["Timestamp"],
                    y=group["GMP %"],
                    mode="lines+markers",
                    name=name,
                    line={"width": 2},
                )
            )
    figure.update_layout(title="GMP HISTORY", xaxis_title="Captured at", yaxis_title="GMP %")
    return _layout(figure)


def gmp_histogram(frame: pd.DataFrame) -> go.Figure:
    valid = frame.dropna(subset=["GMP %"])
    figure = px.histogram(valid, x="GMP %", nbins=16, title="GMP DISTRIBUTION")
    figure.update_traces(marker_color=COLORS["blue"])
    return _layout(figure)


def sector_heatmap(frame: pd.DataFrame) -> go.Figure:
    valid = frame.dropna(subset=["GMP %"]).copy()
    if valid.empty:
        figure = go.Figure()
    else:
        valid["Sector"] = valid["Sector"].fillna("Unclassified")
        aggregate = valid.groupby("Sector", as_index=False)["GMP %"].mean()
        figure = px.imshow(
            aggregate[["GMP %"]].to_numpy(),
            x=["Average GMP %"],
            y=aggregate["Sector"],
            color_continuous_scale=[COLORS["red"], "#E6B84A", COLORS["green"]],
            aspect="auto",
            title="SECTOR GMP HEATMAP",
        )
    return _layout(figure)
