"""
Gráficas Plotly (PNG) — réplica visual de los tableros del portal.
Un PNG por gráfica del dashboard; claves estables para el HTML del PDF.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SERVER_DIR = Path(__file__).resolve().parent.parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

CHARTS_DIR = SERVER_DIR / "data" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

GEOJSON_PATHS = [
    SERVER_DIR / "assets" / "departamentos_colombia.geojson",
    Path("/home/admonctrlxm/portal-direccion-mme/public/departamentos_colombia.geojson"),
]

C = {
    "primary": "#254553",
    "teal": "#287270",
    "gray": "#737373",
    "orange": "#e76f50",
    "gold": "#c9a227",
    "blue": "#125685",
    "green": "#2E7D32",
    "light": "#94A3B8",
}


def _save(fig: go.Figure, key: str, width: int = 1280, height: int = 560) -> Optional[str]:
    out = CHARTS_DIR / f"portal_{key}.png"
    try:
        fig.update_layout(
            template="plotly_white",
            font=dict(family="Arial, sans-serif", size=11, color="#1e293b"),
            title=dict(font=dict(size=15, color=C["primary"])),
            legend=dict(orientation="h", yanchor="bottom", y=-0.22, x=0),
            margin=dict(l=55, r=25, t=55, b=90),
        )
        fig.write_image(str(out), width=width, height=height, scale=1)
        return str(out)
    except Exception as exc:
        logger.warning("[portal_charts] %s: %s", key, exc)
        return None


def _load_geojson() -> Optional[dict]:
    for p in GEOJSON_PATHS:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def _gauge(value: float, title: str, key: str, max_val: float = 100) -> Optional[str]:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=min(float(value), max_val),
        number={"suffix": "%", "font": {"size": 28}},
        title={"text": title, "font": {"size": 13}},
        gauge={
            "axis": {"range": [0, max_val], "tickwidth": 1},
            "bar": {"color": C["teal"]},
            "steps": [
                {"range": [0, 33], "color": "#fee2e2"},
                {"range": [33, 66], "color": "#fef3c7"},
                {"range": [66, max_val], "color": "#d1fae5"},
            ],
            "threshold": {"line": {"color": C["orange"], "width": 3}, "value": value},
        },
    ))
    fig.update_layout(margin=dict(l=30, r=30, t=50, b=20), height=380)
    return _save(fig, key, height=400)


# ── Cap. 2 Comunidades ──────────────────────────────────────────────────────

def chart_com_mapa(data: Dict[str, Any]) -> Optional[str]:
    rows = data.get("por_departamento") or []
    if not rows:
        return None
    geojson = _load_geojson()
    locs = [r["departamento_geo"] for r in rows]
    z = [r["count"] for r in rows]
    if geojson:
        try:
            fig = go.Figure(go.Choropleth(
                geojson=geojson, locations=locs, z=z,
                featureidkey="properties.NOMBRE_DPT",
                colorscale=[[0, "#e0f2fe"], [0.5, "#287270"], [1, "#254553"]],
                colorbar_title="CEs", marker_line_width=0.4,
            ))
            fig.update_geos(fitbounds="locations", visible=False)
            fig.update_layout(title="Comunidades implementadas — Mapa por departamento")
            return _save(fig, "com_mapa", height=600)
        except Exception as exc:
            logger.warning("choropleth: %s", exc)
    top = rows[:12]
    fig = go.Figure(go.Bar(
        x=[r["departamento"] for r in top], y=[r["count"] for r in top],
        marker_color=C["primary"],
    ))
    fig.update_layout(title="Comunidades implementadas por departamento", xaxis_tickangle=-35)
    return _save(fig, "com_mapa")


def chart_com_barras_ces(data: Dict[str, Any]) -> Optional[str]:
    top = (data.get("por_departamento") or [])[:12]
    if not top:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="N° CEs", x=[r["departamento"] for r in top],
        y=[r["count"] for r in top], marker_color=C["primary"],
    ))
    fig.add_trace(go.Bar(
        name="kWp (÷10)", x=[r["departamento"] for r in top],
        y=[r["capacidad_kwp"] / 10 for r in top], marker_color=C["teal"],
    ))
    fig.update_layout(title="CEs y capacidad por departamento (Top 12)", barmode="group", xaxis_tickangle=-35)
    return _save(fig, "com_barras_ces")


def chart_com_inversion(data: Dict[str, Any]) -> Optional[str]:
    top = sorted(data.get("por_departamento") or [], key=lambda x: -x["inversion"])[:12]
    if not top:
        return None
    fig = go.Figure(go.Bar(
        x=[r["departamento"] for r in top],
        y=[r["inversion"] / 1e9 for r in top],
        marker_color=C["gold"], text=[f'{r["inversion"]/1e9:.1f}' for r in top],
        textposition="outside",
    ))
    fig.update_layout(title="Inversión estimada por departamento (miles de millones COP)", xaxis_tickangle=-35)
    return _save(fig, "com_inversion")


# ── Contratos OR + Curva S ────────────────────────────────────────────────────

def chart_or_gauge_fin(data: Dict[str, Any]) -> Optional[str]:
    return _gauge(data.get("avance_financiero", 0), "Avance Financiero — Portafolio OR", "or_gauge_fin")


def chart_or_gauge_gen(data: Dict[str, Any]) -> Optional[str]:
    return _gauge(data.get("avance_general", 0), "Avance General — Portafolio OR", "or_gauge_gen")


def chart_or_gauge_fis(data: Dict[str, Any]) -> Optional[str]:
    return _gauge(data.get("avance_fisico", 0), "Avance Físico — Actividades OR", "or_gauge_fis")


def chart_or_proyectos(data: Dict[str, Any]) -> Optional[str]:
    proys = (data.get("proyectos") or [])[:15]
    if not proys:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Avance general", y=[p["nombre"][:35] for p in proys],
        x=[p["avance_general"] for p in proys], orientation="h", marker_color=C["primary"],
    ))
    fig.add_trace(go.Bar(
        name="Avance financiero", y=[p["nombre"][:35] for p in proys],
        x=[p["avance_financiero"] for p in proys], orientation="h", marker_color=C["teal"],
    ))
    fig.update_layout(title="Avance por proyecto OR (%)", barmode="group", height=640,
                      margin=dict(l=180, r=30, t=55, b=40))
    return _save(fig, "or_proyectos", height=680)


def chart_curva_s(curvas: List[Dict[str, Any]], cat_id: str, key: str) -> Optional[str]:
    cat = next((c for c in curvas if c.get("id") == cat_id), None)
    if not cat:
        return None
    prog = cat.get("programado") or []
    real = cat.get("real") or []
    if len(prog) < 2 and len(real) < 2:
        return None
    fig = go.Figure()
    if prog:
        fig.add_trace(go.Scatter(
            x=[p["fecha"] for p in prog], y=[p["pct"] for p in prog],
            name="Programado", mode="lines+markers", line=dict(color=C["gray"], dash="dash"),
        ))
    if real:
        fig.add_trace(go.Scatter(
            x=[p["fecha"] for p in real], y=[p["pct"] for p in real],
            name="Real", mode="lines+markers", line=dict(color=C["teal"], width=2),
        ))
    fig.update_layout(
        title=f"Curva S — {cat.get('label', cat_id)} (% acumulado portafolio)",
        yaxis_title="% acumulado", xaxis_title="Fecha",
    )
    return _save(fig, key)


# ── Fenoge ────────────────────────────────────────────────────────────────────

def chart_fen_deptos(data: Dict[str, Any]) -> Optional[str]:
    top = (data.get("por_departamento") or [])[:12]
    if not top:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(name="CEs", x=[r["departamento"] for r in top],
                         y=[r["count"] for r in top], marker_color=C["gold"]))
    fig.add_trace(go.Bar(name="kWp (÷10)", x=[r["departamento"] for r in top],
                         y=[r["kwp"] / 10 for r in top], marker_color=C["orange"]))
    fig.update_layout(title="Fenoge — CEs y capacidad por departamento", barmode="group", xaxis_tickangle=-35)
    return _save(fig, "fen_deptos")


def chart_fen_inversion(data: Dict[str, Any]) -> Optional[str]:
    top = sorted(data.get("por_departamento") or [], key=lambda x: -x["inversion"])[:12]
    if not top:
        return None
    fig = go.Figure(go.Bar(
        x=[r["departamento"] for r in top], y=[r["inversion"] / 1e9 for r in top], marker_color=C["gold"],
    ))
    fig.update_layout(title="Fenoge — Inversión por departamento (miles de millones COP)", xaxis_tickangle=-35)
    return _save(fig, "fen_inversion")


def chart_fen_seguimiento(data: Dict[str, Any]) -> Optional[str]:
    rows = data.get("seguimiento") or []
    if len(rows) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[r["fecha"] for r in rows], y=[r["programado"] for r in rows],
                             name="Programado", mode="lines", line=dict(color=C["gray"], dash="dash")))
    fig.add_trace(go.Scatter(x=[r["fecha"] for r in rows], y=[r["real"] for r in rows],
                             name="Real acumulado", mode="lines", line=dict(color=C["teal"], width=2)))
    fig.update_layout(title="Fenoge — Avance de obra acumulado (promedio portafolio)", yaxis_title="%")
    return _save(fig, "fen_seguimiento")


# ── Subsidios ─────────────────────────────────────────────────────────────────

def chart_sub_subsidios_contrib(rows: List[Dict[str, Any]]) -> Optional[str]:
    if len(rows) < 2:
        return None
    anios = [r["anio"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Subsidios", x=anios, y=[r["subsidios"] / 1e6 for r in rows], marker_color=C["primary"]))
    fig.add_trace(go.Bar(name="Contribuciones", x=anios, y=[r["contribuciones"] / 1e6 for r in rows], marker_color=C["teal"]))
    fig.update_layout(title="Subsidios y contribuciones por año (millones COP)", barmode="group")
    return _save(fig, "sub_subsidios_contrib")


def chart_sub_deficit_combo(rows: List[Dict[str, Any]]) -> Optional[str]:
    if len(rows) < 2:
        return None
    anios = [r["anio"] for r in rows]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(name="Déficit acumulado", x=anios,
                         y=[r["deficit_acumulado"] / 1e9 for r in rows], marker_color=C["primary"]), secondary_y=False)
    fig.add_trace(go.Scatter(name="Déficit anual", x=anios,
                             y=[r["deficit_anual"] / 1e9 for r in rows], mode="lines+markers",
                             line=dict(color=C["orange"], width=2)), secondary_y=True)
    fig.add_trace(go.Scatter(name="Apropiación PGN", x=anios,
                             y=[r["apropiacion_pgn"] / 1e9 for r in rows], mode="lines+markers",
                             line=dict(color=C["gold"], width=2, dash="dot")), secondary_y=True)
    fig.update_layout(title="Déficit acumulado, déficit anual y apropiación PGN")
    fig.update_yaxes(title_text="Acumulado (miles de millones)", secondary_y=False)
    fig.update_yaxes(title_text="Anual / PGN (miles de millones)", secondary_y=True)
    return _save(fig, "sub_deficit_combo")


def chart_sub_apropiacion(rows: List[Dict[str, Any]]) -> Optional[str]:
    if len(rows) < 2:
        return None
    anios = [r["anio"] for r in rows]
    a1 = [rows[i - 1]["deficit_acumulado"] / 1e9 if i > 0 else 0 for i in range(len(rows))]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Apropiación PGN", x=anios,
                         y=[r["apropiacion_pgn"] / 1e9 for r in rows], marker_color=C["teal"]))
    fig.add_trace(go.Bar(name="Déficit acum. A-1", x=anios, y=a1, marker_color=C["orange"]))
    fig.update_layout(title="Apropiación PGN y déficit acumulado año anterior", barmode="stack")
    return _save(fig, "sub_apropiacion")


def chart_sub_trimestres(trimestres: List[Dict[str, Any]]) -> Optional[str]:
    if not trimestres:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Pagado", x=[t["concepto_trimestre"] for t in trimestres],
                         y=[float(t["pagado"] or 0) / 1e6 for t in trimestres], marker_color=C["green"]))
    fig.add_trace(go.Bar(name="Pendiente", x=[t["concepto_trimestre"] for t in trimestres],
                         y=[float(t["pendiente"] or 0) / 1e6 for t in trimestres], marker_color=C["orange"]))
    fig.update_layout(title="Valores pagados y pendientes por trimestre (millones COP)", barmode="group",
                      xaxis_tickangle=-30)
    return _save(fig, "sub_trimestres")


def chart_sub_gauge_pagado(pct: float) -> Optional[str]:
    return _gauge(pct, "Porcentaje pagado sobre comprometido", "sub_gauge_pagado")


def chart_sub_prestadores(prestadores: List[Dict[str, Any]]) -> Optional[str]:
    if not prestadores:
        return None
    fig = go.Figure(go.Bar(
        y=[p["nombre_prestador"][:40] for p in prestadores],
        x=[float(p["deuda"] or 0) / 1e6 for p in prestadores],
        orientation="h", marker_color=C["orange"],
    ))
    fig.update_layout(title="Prestadores con mayor saldo pendiente (millones COP)",
                      margin=dict(l=200, r=30, t=55, b=40), height=520)
    return _save(fig, "sub_prestadores", height=560)


def chart_sub_valid_area(serie: List[Dict[str, Any]], area: str, key: str) -> Optional[str]:
    subset = [s for s in serie if s.get("area") == area]
    if not subset:
        return None
    trim_keys = sorted({(s["anio"], s["trimestre"]) for s in subset})
    labels = [f"{a}-T{t}" for a, t in trim_keys[-8:]]
    estados = sorted({s["estado"] for s in subset})
    colors = [C["green"], C["teal"], C["gold"], C["orange"], C["gray"], C["blue"]]
    fig = go.Figure()
    for i, est in enumerate(estados):
        vals = []
        for lbl in labels:
            a, t = lbl.split("-T")
            match = next((s for s in subset if str(s["anio"]) == a and str(s["trimestre"]) == t and s["estado"] == est), None)
            vals.append(int(match["conteo"]) if match else 0)
        fig.add_trace(go.Bar(name=est, x=labels, y=vals, marker_color=colors[i % len(colors)]))
    fig.update_layout(title=f"Validaciones {area} — distribución por trimestre (conteo)", barmode="stack",
                      xaxis_tickangle=-30)
    return _save(fig, key)


# ── Supervisión ───────────────────────────────────────────────────────────────

def chart_sup_gauge_pf(data: Dict[str, Any]) -> Optional[str]:
    return _gauge(data.get("gauges_portafolio", {}).get("fisico", 0), "Avance físico — Portafolio", "sup_gauge_pf")


def chart_sup_gauge_pfin(data: Dict[str, Any]) -> Optional[str]:
    return _gauge(data.get("gauges_portafolio", {}).get("financiero", 0), "Avance financiero — Portafolio", "sup_gauge_pfin")


def chart_sup_gauge_ef(data: Dict[str, Any]) -> Optional[str]:
    return _gauge(data.get("gauges_ejecucion", {}).get("fisico", 0), "Avance físico — En ejecución", "sup_gauge_ef")


def chart_sup_gauge_efin(data: Dict[str, Any]) -> Optional[str]:
    return _gauge(data.get("gauges_ejecucion", {}).get("financiero", 0), "Avance financiero — En ejecución", "sup_gauge_efin")


def chart_sup_pie_fondos(por_fondo: List[Dict[str, Any]]) -> Optional[str]:
    if not por_fondo:
        return None
    fig = go.Figure(go.Pie(
        labels=[f["fondo"] for f in por_fondo], values=[f["contratos"] for f in por_fondo],
        hole=0.4, marker_colors=[C["primary"], C["teal"], C["gold"], C["orange"], C["blue"], C["gray"]],
    ))
    fig.update_layout(title="Contratos por fondo")
    return _save(fig, "sup_pie_fondos", height=480)


def chart_sup_evolucion(evolucion: List[Dict[str, Any]]) -> Optional[str]:
    if len(evolucion) < 2:
        return None
    fig = go.Figure(go.Scatter(
        x=[e["anio"] for e in evolucion], y=[e["avance"] for e in evolucion],
        mode="lines+markers", fill="tozeroy", line=dict(color=C["teal"], width=2),
    ))
    fig.update_layout(title="Evolución del avance de obra promedio por año", yaxis_title="% avance")
    return _save(fig, "sup_evolucion")


def chart_sup_fondo_estado(sankey: List[Dict[str, Any]]) -> Optional[str]:
    if not sankey:
        return None
    labels = [f'{r["fondo"][:18]} | {r["estado_del_contrato"][:22]}' for r in sankey[:15]]
    fig = go.Figure(go.Bar(
        x=[int(r["n"]) for r in sankey[:15]], y=labels, orientation="h", marker_color=C["primary"],
    ))
    fig.update_layout(title="Flujo de contratos — Fondo × Estado (Top 15)", margin=dict(l=220, r=30, t=55, b=40),
                      height=560)
    return _save(fig, "sup_fondo_estado", height=600)


# ── Presupuesto ───────────────────────────────────────────────────────────────

def chart_pre_gauge_comp(pct: float) -> Optional[str]:
    return _gauge(pct, "Comprometido (% apropiación)", "pre_gauge_comp")


def chart_pre_gauge_obl(pct: float) -> Optional[str]:
    return _gauge(pct, "Obligado (% apropiación)", "pre_gauge_obl")


def chart_pre_gauge_disp(pct: float) -> Optional[str]:
    return _gauge(pct, "Disponible sin comprometer (% apropiación)", "pre_gauge_disp")


def chart_pre_ejecucion(totales: Dict[str, Any]) -> Optional[str]:
    labels = ["Obligado", "Comprometido no obligado", "Disponible"]
    obl = float(totales.get("obligados") or 0)
    comp = float(totales.get("comprometido") or 0)
    disp = float(totales.get("disponible") or 0)
    comp_no_obl = max(comp - obl, 0)
    fig = go.Figure(go.Bar(
        x=labels, y=[obl / 1e9, comp_no_obl / 1e9, disp / 1e9],
        marker_color=[C["teal"], C["gold"], C["light"]],
        text=[f"{v/1e9:.1f}" for v in [obl, comp_no_obl, disp]], textposition="outside",
    ))
    fig.update_layout(title="Ejecución presupuestal DEE — composición (miles de millones COP)")
    return _save(fig, "pre_ejecucion")


def chart_pre_proyectos(proyectos: List[Dict[str, Any]]) -> Optional[str]:
    if not proyectos:
        return None
    top = proyectos[:8]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Apropiación", x=[p["proyecto"][:30] for p in top],
                         y=[float(p["apropiacion"] or 0) / 1e9 for p in top], marker_color=C["primary"]))
    fig.add_trace(go.Bar(name="Comprometido", x=[p["proyecto"][:30] for p in top],
                         y=[float(p["compromisos"] or 0) / 1e9 for p in top], marker_color=C["teal"]))
    fig.add_trace(go.Bar(name="Obligado", x=[p["proyecto"][:30] for p in top],
                         y=[float(p["obligados"] or 0) / 1e9 for p in top], marker_color=C["gold"]))
    fig.update_layout(title="Comparativo por proyecto (miles de millones COP)", barmode="group", xaxis_tickangle=-25,
                      height=580)
    return _save(fig, "pre_proyectos", height=620)


# ── Orquestador ───────────────────────────────────────────────────────────────

def generate_all_portal_charts(portal_data: Dict[str, Any]) -> Dict[str, str]:
    com = portal_data.get("comunidades") or {}
    or_d = portal_data.get("contratos_or") or {}
    fen = portal_data.get("fenoge") or {}
    curvas = portal_data.get("colombia_solar") or []
    sub = portal_data.get("subsidios") or {}
    sup = portal_data.get("supervision") or {}
    pre = portal_data.get("presupuesto") or {}
    deficit = sub.get("deficit_historico") or []
    pagos = sub.get("pagos") or {}
    val = sub.get("validaciones") or {}
    tot = pre.get("totales") or {}

    jobs: List[Tuple[str, Callable[[], Optional[str]]]] = [
        ("com_mapa", lambda: chart_com_mapa(com)),
        ("com_barras_ces", lambda: chart_com_barras_ces(com)),
        ("com_inversion", lambda: chart_com_inversion(com)),
        ("or_gauge_fin", lambda: chart_or_gauge_fin(or_d)),
        ("or_gauge_gen", lambda: chart_or_gauge_gen(or_d)),
        ("or_gauge_fis", lambda: chart_or_gauge_fis(or_d)),
        ("or_proyectos", lambda: chart_or_proyectos(or_d)),
        ("curva_obras", lambda: chart_curva_s(curvas, "obras", "curva_obras")),
        ("curva_usuarios", lambda: chart_curva_s(curvas, "usuarios", "curva_usuarios")),
        ("curva_potencia", lambda: chart_curva_s(curvas, "potencia", "curva_potencia")),
        ("curva_internas", lambda: chart_curva_s(curvas, "internas", "curva_internas")),
        ("fen_deptos", lambda: chart_fen_deptos(fen)),
        ("fen_inversion", lambda: chart_fen_inversion(fen)),
        ("fen_seguimiento", lambda: chart_fen_seguimiento(fen)),
        ("sub_subsidios_contrib", lambda: chart_sub_subsidios_contrib(deficit)),
        ("sub_deficit_combo", lambda: chart_sub_deficit_combo(deficit)),
        ("sub_apropiacion", lambda: chart_sub_apropiacion(deficit)),
        ("sub_trimestres", lambda: chart_sub_trimestres(pagos.get("trimestres") or [])),
        ("sub_gauge_pagado", lambda: chart_sub_gauge_pagado(pagos.get("pct_pagado", 0))),
        ("sub_prestadores", lambda: chart_sub_prestadores(pagos.get("prestadores") or [])),
        ("sub_valid_sin", lambda: chart_sub_valid_area(val.get("serie") or [], "SIN", "sub_valid_sin")),
        ("sub_valid_zni", lambda: chart_sub_valid_area(val.get("serie") or [], "ZNI", "sub_valid_zni")),
        ("sup_gauge_pf", lambda: chart_sup_gauge_pf(sup)),
        ("sup_gauge_pfin", lambda: chart_sup_gauge_pfin(sup)),
        ("sup_gauge_ef", lambda: chart_sup_gauge_ef(sup)),
        ("sup_gauge_efin", lambda: chart_sup_gauge_efin(sup)),
        ("sup_pie_fondos", lambda: chart_sup_pie_fondos(sup.get("por_fondo") or [])),
        ("sup_evolucion", lambda: chart_sup_evolucion(sup.get("evolucion") or [])),
        ("sup_fondo_estado", lambda: chart_sup_fondo_estado(sup.get("sankey") or [])),
        ("pre_gauge_comp", lambda: chart_pre_gauge_comp(tot.get("pct_comprometido", 0))),
        ("pre_gauge_obl", lambda: chart_pre_gauge_obl(tot.get("pct_obligado", 0))),
        ("pre_gauge_disp", lambda: chart_pre_gauge_disp(tot.get("pct_disponible", 0))),
        ("pre_ejecucion", lambda: chart_pre_ejecucion(tot)),
        ("pre_proyectos", lambda: chart_pre_proyectos(pre.get("proyectos") or [])),
    ]

    paths: Dict[str, str] = {}
    for key, fn in jobs:
        try:
            path = fn()
            if path:
                paths[key] = path
        except Exception as exc:
            logger.warning("[portal_charts] %s: %s", key, exc)

    logger.info("[portal_charts] Generados %d/%d gráficos", len(paths), len(jobs))
    return paths
