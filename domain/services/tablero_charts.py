import base64
import logging
from collections import Counter
from typing import Any

import plotly.graph_objects as go

logger = logging.getLogger(__name__)

_GOLD    = "#E8A838"
_NAVY    = "#0F172A"
_GRAY    = "#475569"
_BG      = "#EEF2F9"
_WHITE   = "#FFFFFF"
_BORDER  = "#CBD5E1"
_CYAN    = "#06B6D4"
_TEAL    = "#0D9488"
_GREEN   = "#10B981"
_RED     = "#EF4444"
_PURPLE  = "#8B5CF6"
_AMBER   = "#F59E0B"
_SLATE   = "#475569"

_COLORS = [
    "#E8A838", "#06B6D4", "#10B981", "#8B5CF6",
    "#EF4444", "#F59E0B", "#0D9488", "#3B82F6",
    "#EC4899", "#F97316", "#84CC16", "#0EA5E9",
]

_FONT       = dict(family="system-ui, -apple-system, Arial, sans-serif", size=11, color=_NAVY)
_TITLE_FONT = dict(size=11, color=_NAVY)


def _to_b64(fig: go.Figure, width: int = 800, height: int = 360) -> str:
    try:
        png = fig.to_image(format="png", width=width, height=height, scale=2)
        return base64.b64encode(png).decode()
    except Exception:
        logger.exception("Error converting Plotly figure to PNG")
        return ""


def _base_layout(**extra) -> dict:
    return dict(
        paper_bgcolor=_WHITE,
        plot_bgcolor=_WHITE,
        font=_FONT,
        **extra,
    )


# ── Gauge (Semi-gauge) ────────────────────────────────────────────────────────

def gauge_chart(value: float, title: str, color: str = _GOLD, compact: bool = False) -> str:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%", "font": {"size": 18 if compact else 22, "color": _NAVY}},
        title={"text": title, "font": {"size": 9 if compact else 10, "color": _GRAY}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickfont": {"size": 7 if compact else 8}, "tickcolor": _BORDER},
            "bar": {"color": color, "thickness": 0.65},
            "bgcolor": "#E2E8F0",
            "borderwidth": 0,
            "steps": [{"range": [0, 100], "color": "#E2E8F0"}],
        },
    ))
    fig.update_layout(
        **_base_layout(),
        margin=dict(l=15, r=15, t=32, b=8) if compact else dict(l=20, r=20, t=40, b=10),
    )
    return _to_b64(fig, 180, 125) if compact else _to_b64(fig, 260, 190)


# ── Pie / Donut ───────────────────────────────────────────────────────────────

def pie_chart(labels: list[str], values: list[float], title: str = "") -> str:
    if not labels or not values:
        return ""
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.45,
        marker=dict(colors=_COLORS, line=dict(color=_WHITE, width=2)),
        textinfo="label+percent",
        textfont=dict(size=8),
        insidetextorientation="radial",
    ))
    fig.update_layout(
        **_base_layout(),
        title=dict(text=title, font=_TITLE_FONT, x=0),
        margin=dict(l=20, r=140, t=36, b=20),
        legend=dict(orientation="v", x=1.02, font=dict(size=8)),
    )
    return _to_b64(fig, 540, 300)


# ── Bar ───────────────────────────────────────────────────────────────────────

def bar_chart(
    x: list[str],
    y: list[float],
    title: str = "",
    color: str | list[str] = _GOLD,
    horizontal: bool = False,
    y_label: str = "",
) -> str:
    if not x or not y:
        return ""
    marker = dict(color=color, line=dict(color=_WHITE, width=0.5))
    if horizontal:
        height = max(200, len(x) * 25)
        fig = go.Figure(go.Bar(
            x=y, y=x, orientation="h",
            marker=marker,
            text=[f"{v:,.1f}" for v in y],
            textposition="outside",
            textfont=dict(size=8),
        ))
        fig.update_layout(
            **_base_layout(),
            title=dict(text=title, font=_TITLE_FONT, x=0),
            margin=dict(l=130, r=60, t=36, b=20),
            xaxis=dict(showgrid=True, gridcolor="#F0F0F0", title=y_label or None),
            yaxis=dict(automargin=True),
        )
        return _to_b64(fig, 680, height)
    else:
        fig = go.Figure(go.Bar(
            x=x, y=y, marker=marker,
        ))
        fig.update_layout(
            **_base_layout(),
            title=dict(text=title, font=_TITLE_FONT, x=0),
            margin=dict(l=50, r=20, t=36, b=50),
            yaxis=dict(showgrid=True, gridcolor="#F0F0F0", title=y_label or None),
        )
        return _to_b64(fig, 700, 300)


# ── Grouped bar ───────────────────────────────────────────────────────────────

def grouped_bar_chart(
    x: list[str],
    series: dict[str, list[float]],
    title: str = "",
    horizontal: bool = False,
    colors: list[str] | None = None,
) -> str:
    if not x or not series:
        return ""
    bar_colors = colors or _COLORS
    if horizontal:
        height = max(220, len(x) * 28)
        fig = go.Figure()
        for i, (name, vals) in enumerate(series.items()):
            fig.add_trace(go.Bar(
                name=name, x=vals, y=x, orientation="h",
                marker=dict(color=bar_colors[i % len(bar_colors)], line=dict(color=_WHITE, width=0.5)),
            ))
        fig.update_layout(
            **_base_layout(),
            barmode="group",
            title=dict(text=title, font=_TITLE_FONT, x=0),
            margin=dict(l=130, r=20, t=36, b=30),
            legend=dict(orientation="h", y=-0.12, font=dict(size=8)),
            xaxis=dict(showgrid=True, gridcolor="#F0F0F0"),
            yaxis=dict(automargin=True),
        )
        return _to_b64(fig, 700, height)
    else:
        fig = go.Figure()
        for i, (name, vals) in enumerate(series.items()):
            fig.add_trace(go.Bar(
                name=name, x=x, y=vals,
                marker=dict(color=bar_colors[i % len(bar_colors)], line=dict(color=_WHITE, width=0.5)),
            ))
        fig.update_layout(
            **_base_layout(),
            barmode="group",
            title=dict(text=title, font=_TITLE_FONT, x=0),
            margin=dict(l=50, r=20, t=36, b=50),
            legend=dict(orientation="h", y=-0.22, font=dict(size=8)),
            yaxis=dict(showgrid=True, gridcolor="#F0F0F0"),
        )
        return _to_b64(fig, 750, 320)


# ── Stacked bar ───────────────────────────────────────────────────────────────

def stacked_bar_chart(
    x: list[str],
    series: dict[str, list[float]],
    title: str = "",
    colors: list[str] | None = None,
    horizontal: bool = False,
) -> str:
    if not x or not series:
        return ""
    bar_colors = colors or _COLORS
    if horizontal:
        height = max(200, len(x) * 26)
        fig = go.Figure()
        for i, (name, vals) in enumerate(series.items()):
            fig.add_trace(go.Bar(
                name=name, x=vals, y=x, orientation="h",
                marker=dict(color=bar_colors[i % len(bar_colors)]),
            ))
        fig.update_layout(
            **_base_layout(),
            barmode="stack",
            title=dict(text=title, font=_TITLE_FONT, x=0),
            margin=dict(l=140, r=20, t=36, b=30),
            legend=dict(orientation="h", y=-0.12, font=dict(size=8)),
            xaxis=dict(showgrid=True, gridcolor="#F0F0F0"),
            yaxis=dict(automargin=True),
        )
        return _to_b64(fig, 700, height)
    else:
        fig = go.Figure()
        for i, (name, vals) in enumerate(series.items()):
            fig.add_trace(go.Bar(
                name=name, x=x, y=vals,
                marker=dict(color=bar_colors[i % len(bar_colors)]),
            ))
        fig.update_layout(
            **_base_layout(),
            barmode="stack",
            title=dict(text=title, font=_TITLE_FONT, x=0),
            margin=dict(l=50, r=20, t=36, b=50),
            legend=dict(orientation="h", y=-0.22, font=dict(size=8)),
            yaxis=dict(showgrid=True, gridcolor="#F0F0F0"),
        )
        return _to_b64(fig, 750, 300)


# ── Line ──────────────────────────────────────────────────────────────────────

def line_chart(
    series: list[dict],
    x_key: str,
    y_keys: list[str],
    title: str = "",
    labels: dict[str, str] | None = None,
    colors: list[str] | None = None,
) -> str:
    if not series or not y_keys:
        return ""
    labels = labels or {}
    line_colors = colors or _COLORS
    fig = go.Figure()
    for i, key in enumerate(y_keys):
        fig.add_trace(go.Scatter(
            x=[s[x_key] for s in series],
            y=[s.get(key) for s in series],
            mode="lines+markers",
            name=labels.get(key, key),
            line=dict(color=line_colors[i % len(line_colors)], width=2),
            marker=dict(size=4),
            fill="tozeroy" if i == 0 else "none",
            fillcolor=f"rgba{tuple(int(line_colors[i % len(line_colors)].lstrip('#')[j:j+2],16) for j in (0,2,4)) + (0.08,)}" if i == 0 else None,
        ))
    fig.update_layout(
        **_base_layout(),
        title=dict(text=title, font=_TITLE_FONT, x=0),
        margin=dict(l=50, r=20, t=36, b=50),
        legend=dict(orientation="h", y=-0.22, font=dict(size=8)),
        yaxis=dict(showgrid=True, gridcolor="#F0F0F0"),
    )
    return _to_b64(fig, 750, 300)


# ── Combo bar + line ──────────────────────────────────────────────────────────

def combo_bar_line_chart(
    x: list[str],
    bar_series: dict[str, list[float]],
    line_series: dict[str, list[float]],
    title: str = "",
    bar_colors: list[str] | None = None,
    line_colors: list[str] | None = None,
) -> str:
    if not x:
        return ""
    bc = bar_colors or [_GOLD]
    lc = line_colors or [_CYAN, "#B8860B"]
    fig = go.Figure()
    for i, (name, vals) in enumerate(bar_series.items()):
        fig.add_trace(go.Bar(
            name=name, x=x, y=vals,
            marker=dict(color=bc[i % len(bc)]),
        ))
    for i, (name, vals) in enumerate(line_series.items()):
        fig.add_trace(go.Scatter(
            name=name, x=x, y=vals,
            mode="lines+markers",
            line=dict(color=lc[i % len(lc)], width=2),
            marker=dict(size=5, symbol="circle"),
        ))
    fig.update_layout(
        **_base_layout(),
        barmode="group",
        title=dict(text=title, font=_TITLE_FONT, x=0),
        margin=dict(l=50, r=20, t=36, b=50),
        legend=dict(orientation="h", y=-0.24, font=dict(size=8)),
        yaxis=dict(showgrid=True, gridcolor="#F0F0F0"),
    )
    return _to_b64(fig, 750, 320)


# ── Sankey ────────────────────────────────────────────────────────────────────

def sankey_chart(rows: list[dict], levels: list[str] | None = None) -> str:
    if not rows:
        return ""
    if levels is None:
        levels = ["fondo", "estado", "etapa", "departamento", "municipio"]

    MAX_NODES: dict[str, int] = {
        "fondo": 10, "estado": 8, "etapa": 8,
        "departamento": 12, "municipio": 15,
    }

    top_per_level: dict[str, set[str]] = {}
    for lvl in levels:
        counts = Counter(str(r[lvl]) for r in rows if r.get(lvl))
        n = MAX_NODES.get(lvl, 10)
        top_per_level[lvl] = {v for v, _ in counts.most_common(n)}

    node_labels: list[str] = []
    node_index: dict[tuple[str, str], int] = {}
    for lvl in levels:
        for val in sorted(top_per_level.get(lvl, set())):
            node_index[(lvl, val)] = len(node_labels)
            node_labels.append(val)

    if not node_labels:
        return ""

    sources: list[int] = []
    targets: list[int] = []
    values: list[int] = []
    for i in range(len(levels) - 1):
        lvl_a, lvl_b = levels[i], levels[i + 1]
        link_counts: dict[tuple[str, str], int] = {}
        for r in rows:
            a = str(r.get(lvl_a, "")) if r.get(lvl_a) else None
            b = str(r.get(lvl_b, "")) if r.get(lvl_b) else None
            if a in top_per_level.get(lvl_a, set()) and b in top_per_level.get(lvl_b, set()):
                key = (a, b)
                link_counts[key] = link_counts.get(key, 0) + 1
        for (a, b), cnt in link_counts.items():
            if (lvl_a, a) in node_index and (lvl_b, b) in node_index:
                sources.append(node_index[(lvl_a, a)])
                targets.append(node_index[(lvl_b, b)])
                values.append(cnt)

    if not sources:
        return ""

    node_colors = [_COLORS[i % len(_COLORS)] for i in range(len(node_labels))]

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=12, thickness=16,
            label=node_labels,
            color=node_colors,
            line=dict(color=_BORDER, width=0.5),
        ),
        link=dict(
            source=sources, target=targets, value=values,
            color="rgba(200,200,200,0.35)",
        ),
        textfont=dict(size=8, family="system-ui, Arial, sans-serif", color=_NAVY),
    ))
    fig.update_layout(
        paper_bgcolor=_WHITE,
        font=dict(family="system-ui, sans-serif", size=8, color=_NAVY),
        margin=dict(l=10, r=10, t=16, b=10),
    )
    return _to_b64(fig, 950, 440)


# ── Stacked area chart ────────────────────────────────────────────────────────

def stacked_area_chart(
    x: list[str],
    areas: dict[str, list[float]],
    line_series: dict[str, list[float]] | None = None,
    title: str = "",
    area_colors: list[str] | None = None,
    line_colors: list[str] | None = None,
    y_axis_label: str = "",
    y2_axis_label: str = "",
) -> str:
    """Stacked area chart (tonexty) with optional overlay line series on secondary y-axis."""
    if not x or not areas:
        return ""
    a_colors = area_colors or _COLORS
    l_colors = line_colors or ["#D07050", "#7EC8E0", "#B8B8B8", "#CC4455"]
    fig = go.Figure()

    # Build cumulative stacks for tonexty fill
    cumulative = [0.0] * len(x)
    for i, (name, vals) in enumerate(areas.items()):
        upper = [cumulative[j] + (vals[j] if j < len(vals) else 0) for j in range(len(x))]
        fig.add_trace(go.Scatter(
            x=x, y=upper,
            name=name, mode="none",
            fill="tonexty" if i > 0 else "tozeroy",
            fillcolor=a_colors[i % len(a_colors)],
            line=dict(width=0),
            stackgroup="one",
        ))
        cumulative = upper

    # Overlay lines on secondary y-axis
    if line_series:
        for j, (name, vals) in enumerate(line_series.items()):
            fig.add_trace(go.Scatter(
                x=x, y=vals, name=name, mode="lines",
                line=dict(color=l_colors[j % len(l_colors)], width=1.5, dash="dot" if j > 0 else "solid"),
                yaxis="y2",
            ))

    has_y2 = bool(line_series)
    fig.update_layout(
        **_base_layout(),
        title=dict(text=title, font=_TITLE_FONT, x=0),
        margin=dict(l=55, r=55 if has_y2 else 20, t=36, b=50),
        xaxis=dict(showgrid=False, tickangle=-45, nticks=15, tickfont=dict(size=7)),
        yaxis=dict(
            showgrid=True, gridcolor="#F0F0F0",
            title=dict(text=y_axis_label, font=dict(size=8)) if y_axis_label else None,
        ),
        yaxis2=dict(
            overlaying="y", side="right",
            showgrid=False,
            title=dict(text=y2_axis_label or "% SIN", font=dict(size=8)),
            range=[0, 110],
        ) if has_y2 else {},
        legend=dict(orientation="h", y=-0.25, font=dict(size=8), traceorder="normal"),
    )
    return _to_b64(fig, 780, 300)


# ── Geo scatter ───────────────────────────────────────────────────────────────

def geo_scatter(
    puntos: list[dict],
    color_key: str | None = None,
    title: str = "",
) -> str:
    valid = [p for p in puntos if p.get("lat") is not None and p.get("lng") is not None]
    if not valid:
        return ""

    lats = [p["lat"] for p in valid]
    lons = [p["lng"] for p in valid]
    texts = [p.get("nombre", "") for p in valid]

    if color_key:
        cats = [str(p.get(color_key, "N/A")) for p in valid]
        unique_cats = sorted(set(cats))
        color_map = {c: _COLORS[i % len(_COLORS)] for i, c in enumerate(unique_cats)}
        marker_colors = [color_map[c] for c in cats]
    else:
        marker_colors = _GOLD

    fig = go.Figure(go.Scattergeo(
        lat=lats, lon=lons, text=texts, mode="markers",
        marker=dict(size=6, color=marker_colors,
                    line=dict(color=_WHITE, width=0.5), opacity=0.85),
        hoverinfo="text",
    ))
    fig.update_geos(
        scope="south america", fitbounds="locations",
        showland=True, landcolor=_BG,
        showocean=True, oceancolor="#D0E8F8",
        showcoastlines=True, coastlinecolor=_BORDER,
        showcountries=True, countrycolor=_BORDER,
        showframe=False,
    )
    fig.update_layout(
        paper_bgcolor=_WHITE,
        margin=dict(l=0, r=0, t=28 if title else 4, b=4),
        title=dict(text=title, font=dict(size=10, color=_NAVY), x=0.5) if title else {},
        geo=dict(bgcolor=_WHITE),
    )
    return _to_b64(fig, 620, 400)
