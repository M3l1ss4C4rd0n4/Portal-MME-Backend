import logging
import math
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "http://localhost:8000"


def _get_api_key() -> str:
    from core.config import settings
    return settings.API_KEY


async def _fetch(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_API_BASE}{path}",
            params=params or {},
            headers={"X-API-Key": _get_api_key()},
        )
        r.raise_for_status()
        return r.json()


def _fetch_curvas_s_contratos_or() -> list[dict]:
    """Query Curvas S (obras civiles + usuarios) for CE: Contratos OR from the DB."""
    import re
    DATE_RE = re.compile(r"^col_(\d{1,2})_(\d{1,2})_(\d{4})$")

    def col_to_label(col: str) -> str:
        m = DATE_RE.match(col)
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}" if m else col

    PROGRAMA = "CE: Contratos OR"
    # (label, proj_table, rep_table, proj_denom_col, rep_denom_col)
    CATEGORIAS = [
        ("Obras Civiles", "proyectado_obras_civiles", "reportado_obras_civiles", "usuarios_totales",         "usuarios_totales"),
        ("Usuarios",      "proyectado_usuarios",      "reportado_usuarios",      "usuarios_totales",         "usuarios_totales"),
        ("Potencia",      "proyectado_potencia",      "reportado_potencia",      "potencia_a_instalar_mwp",  "usuarios_totales"),
        ("Internas",      "proyectado_internas",      "reportado_internas",      "usuarios_totales",         "usuarios_totales"),
    ]

    results: list[dict] = []
    try:
        from infrastructure.database.connection import PostgreSQLConnectionManager
        cm = PostgreSQLConnectionManager()
        with cm.get_connection() as conn:
            with conn.cursor() as cur:

                def get_date_cols(tbl: str) -> list[str]:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='colombia_solar' AND table_name=%s "
                        "AND column_name LIKE 'col_%%' ORDER BY ordinal_position",
                        (tbl,),
                    )
                    return [r[0] for r in cur.fetchall()]

                def fetch_table(tbl: str, denom_col: str, date_cols: list[str]) -> list:
                    if not date_cols:
                        return []
                    cols_sql = ", ".join(f'"{c}"' for c in date_cols)
                    cur.execute(
                        f'SELECT "{denom_col}", {cols_sql} '
                        f'FROM colombia_solar."{tbl}" WHERE programa=%s',
                        (PROGRAMA,),
                    )
                    return cur.fetchall()

                def iso_from_col(col: str) -> str:
                    m = DATE_RE.match(col)
                    if not m:
                        return col
                    return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

                def aggregate_pct(rows: list, n_cols: int) -> list[float]:
                    if not rows:
                        return [0.0] * n_cols
                    totals = []
                    for row in rows:
                        t = float(row[0] or 0)
                        if t <= 1:
                            t = max((float(v) for v in row[1:] if v is not None and float(v) > 0), default=0)
                        totals.append(max(t, 1.0))
                    cum = [0.0] * len(rows)
                    pcts: list[float] = []
                    for ci in range(n_cols):
                        for ri, row in enumerate(rows):
                            v = row[ci + 1]
                            if v is not None and float(v) > 0:
                                cum[ri] = max(cum[ri], float(v))
                        pcts.append(min(sum(c / t * 100 for c, t in zip(cum, totals)) / len(totals), 100.0))
                    return pcts

                for label, proj_tbl, rep_tbl, proj_denom, rep_denom in CATEGORIAS:
                    proj_cols = get_date_cols(proj_tbl)
                    rep_cols  = get_date_cols(rep_tbl)
                    if not proj_cols:
                        continue

                    proj_iso = {iso_from_col(c): c for c in proj_cols}
                    rep_iso  = {iso_from_col(c): c for c in rep_cols}
                    common_iso = sorted(set(proj_iso) & set(rep_iso))
                    if not common_iso:
                        common_iso = sorted(proj_iso)

                    proj_date_cols = [proj_iso[iso] for iso in common_iso]
                    rep_date_cols  = [rep_iso[iso] for iso in common_iso if iso in rep_iso]

                    proj_rows = fetch_table(proj_tbl, proj_denom, proj_date_cols)
                    rep_rows  = fetch_table(rep_tbl, rep_denom, rep_date_cols)

                    prog_pct = aggregate_pct(proj_rows, len(common_iso))
                    real_pct = aggregate_pct(rep_rows, len(rep_date_cols))

                    # Detectar último corte desde datos crudos (no del acumulado)
                    last_rep_col_with_data = -1
                    for ci in range(len(rep_date_cols)):
                        for row in rep_rows:
                            v = row[ci + 1]
                            if v is not None and float(v) > 0:
                                last_rep_col_with_data = ci
                    if last_rep_col_with_data >= 0:
                        last_real_iso = iso_from_col(rep_date_cols[last_rep_col_with_data])
                        last_real = common_iso.index(last_real_iso) if last_real_iso in common_iso else -1
                    else:
                        last_real = -1

                    # Pad real to same length as prog if rep has fewer dates
                    if len(real_pct) < len(common_iso):
                        real_pct.extend([0.0] * (len(common_iso) - len(real_pct)))

                    real_trimmed: list[float | None] = [
                        v if i <= last_real else None for i, v in enumerate(real_pct)
                    ]

                    results.append({
                        "label": label,
                        "fechas": [col_to_label(proj_iso[iso]) for iso in common_iso],
                        "prog_pct": prog_pct,
                        "real_pct": real_trimmed,
                    })
    except Exception as exc:
        logger.warning("[Curvas S] No se pudo obtener datos: %s", exc)

    return results


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
:root {
  --gold:    #E8A838;
  --navy:    #0F172A;
  --gray:    #475569;
  --muted:   #64748B;
  --bg:      #EEF2F9;
  --white:   #FFFFFF;
  --border:  #CBD5E1;
  --success: #10B981;
  --danger:  #EF4444;
  --cyan:    #06B6D4;
  --teal:    #0D9488;
  --amber:   #F59E0B;
  --purple:  #8B5CF6;
}
* { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, Arial, sans-serif;
  font-size: 10.5px;
  background: var(--white);
  color: var(--navy);
  margin: 0;
  line-height: 1.4;
}
.pdf-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  border-bottom: 2.5px solid var(--gold);
  padding-bottom: 7px;
  margin-bottom: 12px;
}
.pdf-header-title  { font-size: 15px; font-weight: 800; color: var(--navy); }
.pdf-header-sub    { font-size: 8px; color: var(--gray); margin-top: 2px; }
.pdf-header-date   { font-size: 8px; color: var(--muted); text-align: right; line-height: 1.7; }

/* KPI grids */
.kpi-grid   { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px; }
.kpi-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin-bottom: 10px; }
.kpi-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px; }
.kpi-grid-6 { display: grid; grid-template-columns: repeat(6, 1fr); gap: 5px; margin-bottom: 10px; }
.kpi-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 7px 9px;
  break-inside: avoid;
}
.kpi-value  { font-size: 18px; font-weight: 800; color: var(--navy); line-height: 1.1; }
.kpi-unit   { font-size: 9px; font-weight: 500; color: var(--gray); }
.kpi-label  { font-size: 7.5px; color: var(--gray); text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }
.kpi-sub    { font-size: 7.5px; color: var(--muted); margin-top: 2px; }

/* PDF Cards */
.card-pdf {
  background: #F8FAFC;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  break-inside: avoid;
}
.card-title {
  font-size: 9px;
  font-weight: 700;
  color: var(--amber);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.card-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 10px; }
.card-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 10px; }
.card-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 10px; }
.card-grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-bottom: 10px; }

/* KPI chips pequeños */
.kpi-chip-pdf {
  background: #EEF2F9;
  border-radius: 5px;
  padding: 6px 8px;
  break-inside: avoid;
}
.kpi-chip-value { font-size: 14px; font-weight: 800; color: var(--navy); line-height: 1.1; }
.kpi-chip-value-accent { color: var(--amber); }
.kpi-chip-sub { font-size: 7.5px; color: var(--muted); margin-top: 1px; }
.kpi-chip-label { font-size: 7px; color: var(--gray); text-transform: uppercase; letter-spacing: 0.03em; margin-top: 2px; }

/* Progress bar mejorado */
.progress-pdf { margin-bottom: 6px; }
.progress-pdf-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
.progress-pdf-label { font-size: 8px; font-weight: 600; color: var(--navy); }
.progress-pdf-value { font-size: 8px; font-weight: 700; }
.progress-pdf-bar { background: #E2E8F0; border-radius: 3px; height: 7px; overflow: hidden; }
.progress-pdf-fill { height: 100%; border-radius: 3px; }
.progress-pdf-meta { font-size: 7px; color: var(--muted); margin-top: 1px; text-align: right; }

/* Gauge semi-circular nativo */
.gauge-pdf { display: flex; flex-direction: column; align-items: center; width: 100%; }
.gauge-pdf-label { font-size: 9px; color: var(--gray); text-align: center; margin-top: 1px; }

/* Section title */
.section-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--navy);
  border-left: 3px solid var(--gold);
  padding-left: 8px;
  margin: 12px 0 6px;
}

/* Charts */
.chart-wrap  { margin-bottom: 9px; break-inside: avoid; page-break-inside: avoid; }
.chart-img   { width: 100%; display: block; border-radius: 3px; max-height: 115mm; object-fit: contain; }
.chart-tall .chart-img { max-height: 125mm; }
.chart-img-short { max-height: 70mm !important; }
.chart-img-tiny { max-height: 50mm !important; }
.mapa-pdf-wrap { max-height: 105mm; overflow: hidden; border-radius: 6px; text-align: center; margin-bottom: 6px; }
.mapa-pdf-wrap img { max-height: 105mm; width: auto; max-width: 100%; object-fit: contain; }
.gauge-pdf-wrap { border-radius: 3px; text-align: center; width: 100%; }
.gauge-pdf-wrap img { max-height: 45mm; width: auto; max-width: 100%; object-fit: contain; }
.chart-row-3 .chart-wrap img { max-height: 52mm; }
.chart-row   { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 9px; }
.chart-row-2-1 { display: grid; grid-template-columns: 2fr 1fr; gap: 8px; margin-bottom: 9px; }
.chart-row-1-2 { display: grid; grid-template-columns: 1fr 2fr; gap: 8px; margin-bottom: 9px; }
.chart-row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 9px; }
.chart-row .chart-wrap, .chart-row-2-1 .chart-wrap, .chart-row-3 .chart-wrap { margin-bottom: 0; }

/* Hybrid v6: screenshots adaptativas, evitar cortes internos */
.hybrid-img-wrap { break-inside: avoid; margin-bottom: 0; }
.hybrid-img { max-width: 100%; max-height: 160mm; width: auto; height: auto; display: block; margin: 0 auto; border-radius: 3px; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 8.5px; margin-bottom: 10px; }
th {
  background: var(--bg); color: var(--navy); font-weight: 700;
  padding: 4px 5px; border-bottom: 1.5px solid var(--border); text-align: left;
}
td { padding: 3px 5px; border-bottom: 1px solid #f0f0f0; }
tr:nth-child(even) td { background: #fafbfd; }
tr { break-inside: avoid; page-break-inside: avoid; }
.tr-total td { background: rgba(245,158,11,.07) !important; font-weight: 700; border-top: 1.5px solid var(--border); }

/* Progress bar */
.pb-wrap { background: #E2E8F0; border-radius: 3px; height: 6px; width: 100%; }
.pb-fill  { border-radius: 3px; height: 6px; }

/* Badges / chips */
.badge { display: inline-block; padding: 1px 5px; border-radius: 8px; font-size: 7.5px; font-weight: 600; }
.badge-ok   { background: rgba(16,185,129,.12); color: #059669; }
.badge-pend { background: rgba(245,158,11,.12);  color: #D97706; }

/* KPI Bar (subsidios) */
.kpi-bar {
  display: grid; grid-template-columns: 80px repeat(5, 1fr);
  background: var(--bg); border: 2px solid var(--gold);
  border-radius: 6px; overflow: hidden; margin-bottom: 10px;
}
.kpi-bar-cell {
  padding: 8px 10px;
  border-right: 1px solid var(--border);
  break-inside: avoid;
}
.kpi-bar-cell:last-child { border-right: none; }
.kpi-bar-val   { font-size: 13px; font-weight: 800; color: var(--navy); line-height: 1.2; }
.kpi-bar-label { font-size: 7.5px; color: var(--gray); text-transform: uppercase; margin-top: 2px; }
.kpi-bar-year  { font-size: 7px; color: var(--muted); }

/* Utils */
.avoid-break { break-inside: avoid; }
.page-break  { break-before: page; }
.meta        { font-size: 7.5px; color: var(--muted); }
.nota        { font-size: 8px; color: var(--gray); margin: 4px 0 8px; padding: 5px 8px; background: var(--bg); border-radius: 4px; border-left: 2px solid var(--gold); }
"""


def _full_html(title: str, body: str, update_time: str = "", orientation: str = "landscape") -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    upd = f"Datos: {update_time}" if update_time else now
    page_rule = f"@page {{ size: A4 {orientation}; margin: 10mm 10mm; }}"
    # En landscape el ancho sobra; limitar altura para evitar páginas casi vacías.
    max_h = "125mm" if orientation == "landscape" else "255mm"
    hybrid_extra = f"""
    .hybrid-img {{ max-height: {max_h}; }}
    """
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><style>{page_rule}{_CSS}{hybrid_extra}</style></head>
<body>
  <div class="pdf-header">
    <div>
      <div class="pdf-header-title">{title}</div>
      <div class="pdf-header-sub">Ministerio de Minas y Energía · Dirección de Energización</div>
    </div>
    <div class="pdf-header-date">Generado: {now}<br/><span style="color:var(--gold)">{upd}</span></div>
  </div>
  {body}
</body>
</html>"""


def _to_pdf(html: str) -> bytes:
    from weasyprint import HTML
    return HTML(string=html).write_pdf()


def _kpi(label: str, value: str, unit: str = "", accent: str = "", sub: str = "") -> str:
    style = f"color:{accent}" if accent else ""
    unit_html = f'<span class="kpi-unit"> {unit}</span>' if unit else ""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card avoid-break">
      <div class="kpi-value" style="{style}">{value}{unit_html}</div>
      <div class="kpi-label">{label}</div>
      {sub_html}
    </div>"""


def _section(text: str) -> str:
    return f'<div class="section-title">{text}</div>'


def _chart(b64: str, cls: str = "") -> str:
    if not b64:
        return ""
    img_cls = f"chart-img {cls}".strip()
    return f'<div class="chart-wrap"><img class="{img_cls}" src="data:image/png;base64,{b64}"/></div>'


def _pb(pct: float, color: str = "#E8A838") -> str:
    w = min(100, max(0, pct))
    return f'<div class="pb-wrap"><div class="pb-fill" style="width:{w}%;background:{color}"></div></div>'


def _gauge_pdf(value: float, label: str, color: str = "#F59E0B", size: int = 70) -> str:
    """Semi-gauge SVG con % centrado dentro del arco como texto SVG nativo."""
    pct = min(100, max(0, float(value or 0)))
    cx, cy, r, sw = 50, 50, 44, 8

    bg = f"M {cx - r} {cy} A {r} {r} 0 0 1 {cx + r} {cy}"

    if pct >= 99.5:
        arc = (
            f'<path d="M {cx-r} {cy} A {r} {r} 0 0 1 {cx} {cy-r}'
            f' A {r} {r} 0 0 1 {cx+r} {cy}"'
            f' fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>'
        )
    elif pct < 0.5:
        arc = ""
    else:
        angle = math.pi * (1.0 - pct / 100.0)
        ex = round(cx + r * math.cos(angle), 2)
        ey = round(cy - r * math.sin(angle), 2)
        arc = (
            f'<path d="M {cx-r} {cy} A {r} {r} 0 0 1 {ex} {ey}"'
            f' fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>'
        )

    # Centroide visual del semicírculo: y ≈ cy - 4r/(3π) ≈ 31.
    # font-family explícito para que WeasyPrint use DejaVu Sans y no caiga
    # en un fallback que no soporta "%" o puntos decimales correctamente.
    pct_svg = (
        f'<text x="{cx}" y="31" text-anchor="middle" dominant-baseline="central"'
        f' font-family="DejaVu Sans,sans-serif" font-size="13" font-weight="bold"'
        f' fill="{color}">{pct:.1f}%</text>'
    )

    label_html = f'<div class="gauge-pdf-label" style="text-align:center;margin-top:2px">{label}</div>' if label else ''

    return f"""
    <div class="gauge-pdf">
      <svg viewBox="0 0 100 55" style="width:100%;max-width:{size}mm;display:block;margin:0 auto">
        <path d="{bg}" fill="none" stroke="#E2E8F0" stroke-width="{sw}" stroke-linecap="round"/>
        {arc}
        {pct_svg}
      </svg>
      {label_html}
    </div>"""


def _card_pdf(title: str, content: str, extra_class: str = "") -> str:
    return f"""
    <div class="card-pdf {extra_class}">
      <div class="card-title">{title}</div>
      {content}
    </div>"""


def _kpi_chip_pdf(label: str, value: str, accent: bool = False, sub: str = "") -> str:
    sub_html = f'<div class="kpi-chip-sub">{sub}</div>' if sub else ""
    val_cls = "kpi-chip-value" + (" kpi-chip-value-accent" if accent else "")
    return f"""
    <div class="kpi-chip-pdf">
      <div class="{val_cls}">{value}</div>
      {sub_html}
      <div class="kpi-chip-label">{label}</div>
    </div>"""


def _progress_pdf(label: str, pct: float, color: str = "#F59E0B", meta: str = "") -> str:
    pct = min(100, max(0, pct))
    meta_html = f'<div class="progress-pdf-meta">{meta}</div>' if meta else ""
    return f"""
    <div class="progress-pdf">
      <div class="progress-pdf-header">
        <span class="progress-pdf-label">{label}</span>
        <span class="progress-pdf-value" style="color:{color}">{pct:.0f}%</span>
      </div>
      <div class="progress-pdf-bar"><div class="progress-pdf-fill" style="width:{pct}%;background:{color}"></div></div>
      {meta_html}
    </div>"""


def _fmt_num(v: Any, dec: int = 0) -> str:
    if v is None:
        return "–"
    try:
        n = float(v)
        if dec == 0:
            return f"{int(round(n)):,}".replace(",", ".")
        return f"{n:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(v)


def _fmt_cop(v: Any) -> str:
    """Exact COP value — matches dashboard fmtCOP: $ 1.234.567.890"""
    if v is None:
        return "–"
    try:
        n = int(round(float(v)))
        return "$ " + f"{n:,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(v)


def _pct(v: Any, mult: float = 1.0) -> str:
    if v is None:
        return "–"
    try:
        return f"{float(v) * mult:.1f}%"
    except (ValueError, TypeError):
        return str(v)


# ── Supervisión ───────────────────────────────────────────────────────────────

async def _build_supervision(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import (
        sankey_chart, pie_chart, bar_chart, line_chart, gauge_chart,
    )
    captures = captures or {}
    params = params or {}

    data = await _fetch("/v1/supervision/dashboard", params=params)
    detalle_resp = await _fetch("/v1/supervision/detalle", params=params)
    rows = detalle_resp.get("proyectos", [])

    fin = data.get("financiero", {})
    usu = data.get("usuarios", {})

    suma_ciclo = (
        (data.get("enEjecucion") or 0)
        + (data.get("enAOM") or 0)
        + (data.get("enLiquidacion") or 0)
        + (data.get("liquidados") or 0)
        + (data.get("perdidaCompetencia") or 0)
    )

    # ── INDICADORES CLAVE ──
    kpis_ind = f"""
    {_section("INDICADORES CLAVE")}
    <div class="kpi-grid">
      {_kpi("Contratos", _fmt_num(data.get("nContratos")), "", "#F59E0B")}
      {_kpi("Proyectos", _fmt_num(data.get("nProyectos")))}
      {_kpi("En Ejecución", _fmt_num(data.get("enEjecucion")), "", "#06B6D4",
            _pct((data.get("enEjecucion") or 0) / max(data.get("nContratos") or 1, 1) * 100))}
      {_kpi("AOM", _fmt_num(data.get("enAOM")), "", "#0D9488",
            _pct((data.get("enAOM") or 0) / max(data.get("nContratos") or 1, 1) * 100))}
      {_kpi("En Liquidación", _fmt_num(data.get("enLiquidacion")), "", "#E8A838",
            _pct((data.get("enLiquidacion") or 0) / max(data.get("nContratos") or 1, 1) * 100))}
      {_kpi("Liquidados", _fmt_num(data.get("liquidados")), "", "#10B981",
            _pct((data.get("liquidados") or 0) / max(data.get("nContratos") or 1, 1) * 100))}
      {_kpi("Pérdida Competencia", _fmt_num(data.get("perdidaCompetencia")), "", "#EF4444",
            _pct((data.get("perdidaCompetencia") or 0) / max(data.get("nContratos") or 1, 1) * 100))}
      {_kpi("Suma Ciclo", _fmt_num(suma_ciclo))}
    </div>"""

    # ── AVANCE PORTAFOLIO (Gauges) ──
    gf  = gauge_chart(data.get("avanceFisico") or 0,       "Avance Físico",     "#10B981")
    gfi = gauge_chart(data.get("avanceFinanciero") or 0,   "Avance Financiero", "#10B981")
    gg  = gauge_chart(data.get("avanceContrato") or 0,     "Avance General",    "#E8A838")
    kpis_avance = f"""
    {_section("AVANCE PORTAFOLIO")}
    <div class="chart-row-3">
      {_chart(gf)}{_chart(gfi)}{_chart(gg)}
    </div>"""

    # ── PORTAFOLIO FINANCIERO ──
    pct_des = fin.get("pctDesembolsado") or 0
    kpis_fin = f"""
    {_section("PORTAFOLIO FINANCIERO")}
    <div class="kpi-grid-3">
      {_kpi("Valor Total", _fmt_cop(fin.get("valorProyecto")), "", "#E8A838")}
      {_kpi("Valor Desembolsado", _fmt_cop(fin.get("valorDesembolsado")), "", "#10B981",
            f"{_pct(pct_des)} desembolsado")}
      {_kpi("Valor por Desembolsar", _fmt_cop(fin.get("valorPorDesembolsar")), "", "#06B6D4")}
    </div>"""

    # ── USUARIOS ENERGÉTICOS ──
    kpis_usu = f"""
    {_section("USUARIOS ENERGÉTICOS")}
    <div class="kpi-grid">
      {_kpi("Contratados", _fmt_num(usu.get("contratados")), "", "#F59E0B")}
      {_kpi("Finales", _fmt_num(usu.get("finales")), "", "#0D9488")}
      {_kpi("Proyectos c/ usuarios cont.", _fmt_num(usu.get("filasContratados")))}
      {_kpi("Proyectos c/ usuarios fin.", _fmt_num(usu.get("filasFinales")))}
    </div>"""

    # ── CONTRATOS POR FONDO (Donut) ──
    por_fondo = data.get("porFondo", [])
    pie_b64 = captures.get("pie_fondo") or (
        pie_chart(
            [r["fondo"] for r in por_fondo],
            [r["contratos"] for r in por_fondo],
            "CONTRATOS POR FONDO",
        ) if por_fondo else ""
    )

    # ── TIPO DE SOLUCIÓN (list) ──
    por_tipo = data.get("porTipoSolucion", [])
    tipo_rows = "".join(
        f"<tr><td>{r['tipo']}</td>"
        f"<td style='text-align:right;color:#F59E0B;font-weight:700'>{_fmt_num(r['proyectos'])}</td></tr>"
        for r in por_tipo
    )
    nfoto = data.get("nFotovoltaicos", 0)
    tipo_html = f"""
    {_section("TIPO DE SOLUCIÓN")}
    <p class="meta" style="margin-bottom:5px">
      Parques solares/generadores: <strong>{_fmt_num(nfoto)}</strong> proyectos
    </p>
    <table class="avoid-break" style="max-width:340px">
      <thead><tr><th>Tipo de Solución</th><th style="text-align:right">Proyectos</th></tr></thead>
      <tbody>{tipo_rows}</tbody>
    </table>""" if por_tipo else ""

    # ── FLUJO DE CONTRATOS (Sankey) — screenshot del frontend o Plotly fallback ──
    sankey_b64 = captures.get("sankey") or (
        sankey_chart(rows, ["fondo", "estado", "etapa", "departamento", "municipio"]) if rows else ""
    )

    # ── EVOLUCIÓN AVANCE DE OBRA ──
    avance_anio = data.get("avancePorAnio", [])
    line_b64 = line_chart(
        avance_anio, "anio", ["avg_avance_obra"],
        "EVOLUCIÓN DEL AVANCE DE OBRA PROMEDIO",
        {"avg_avance_obra": "Avance Obra %"},
        ["#22C55E"],
    ) if avance_anio else ""

    body = (
        kpis_ind
        + kpis_avance
        + kpis_fin
        + kpis_usu
    )
    if pie_b64 or tipo_html:
        body += f'<div class="chart-row">{_chart(pie_b64) if pie_b64 else ""}'
        body += f'<div>{tipo_html}</div></div>'
    if sankey_b64:
        body += _section("FLUJO DE CONTRATOS — FONDO › ESTADO › ETAPA › DEPARTAMENTO › MUNICIPIO")
        body += _chart(sankey_b64)
    if line_b64:
        body += _section("EVOLUCIÓN DEL AVANCE DE OBRA PROMEDIO")
        body += _chart(line_b64)

    return _full_html("Supervisión de Contratos", body, str(data.get("ultima_actualizacion", "")))


# ── Presupuesto ───────────────────────────────────────────────────────────────

async def _build_presupuesto(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import stacked_bar_chart
    captures = captures or {}

    data = await _fetch("/v1/presupuesto/resumen")
    tot = data.get("totales", {})
    proyectos = data.get("proyectos", [])

    arop = tot.get("apropiacion") or 0
    comp = tot.get("comprometido") or 0
    obl  = tot.get("obligados") or 0
    disp = tot.get("disponible") or 0
    pct_c = (tot.get("pct_comprometido") or 0) * 100
    pct_o = (tot.get("pct_obligado") or 0) * 100
    pct_d = (disp / arop * 100) if arop else 0

    # ── Fila de 4 KPIs superiores ──
    kpis = f"""
    {_section("INDICADORES CLAVE")}
    <div class="kpi-grid">
      {_kpi("Apropiación Total", _fmt_cop(arop), "", "#F59E0B", "Dirección de EE")}
      {_kpi("Comprometido", _fmt_cop(comp), "", "#F59E0B", f"{pct_c:.2f}% del total")}
      {_kpi("Obligado", _fmt_cop(obl), "", "#EF4444", f"{pct_o:.2f}% del total")}
      {_kpi("Disponible", _fmt_cop(disp), "", "#64748B", f"{pct_d:.2f}% sin compromiso")}
    </div>"""

    # ── Card de Resumen Ejecución Presupuestal ──
    obl_pct  = (obl / arop * 100) if arop else 0
    cno_pct  = (max(0, comp - obl) / arop * 100) if arop else 0
    disp_pct = pct_d
    ejec_sobre_comp = (obl / comp * 100) if comp else 0
    resumen_card = _card_pdf("Resumen Ejecución Presupuestal", f"""
      <div style="background:linear-gradient(to right, rgba(245,158,11,.08), rgba(217,119,6,.04));border:1px solid rgba(245,158,11,.15);border-radius:5px;padding:8px 10px;margin-bottom:10px">
        <div style="font-size:8px;color:#B45309;text-transform:uppercase;letter-spacing:0.04em">Apropiación Total 2026</div>
        <div style="font-size:16px;font-weight:800;color:#B45309;line-height:1.1;margin-top:2px">{_fmt_cop(arop)}</div>
        <div style="font-size:7.5px;color:#64748B;margin-top:2px">Dirección de Energía Eléctrica</div>
      </div>
      <div class="card-grid-3" style="margin-bottom:10px">
        <div style="text-align:center;background:rgba(245,158,11,.05);border:1px solid rgba(245,158,11,.1);border-radius:5px;padding:6px 2px">
          <div style="font-size:7px;color:#B45309;text-transform:uppercase;margin-bottom:2px">Comprometido</div>
          {_gauge_pdf(pct_c, "", "#F59E0B", size=55)}
          <div style="font-size:10px;font-weight:800;color:#F59E0B">{pct_c:.2f}%</div>
          <div style="font-size:7px;color:#64748B">{_fmt_cop(comp)}</div>
          <div style="font-size:6.5px;color:#94A3B8">Recursos con destino definido</div>
        </div>
        <div style="text-align:center;background:rgba(239,68,68,.05);border:1px solid rgba(239,68,68,.1);border-radius:5px;padding:6px 2px">
          <div style="font-size:7px;color:#DC2626;text-transform:uppercase;margin-bottom:2px">Obligado</div>
          {_gauge_pdf(pct_o, "", "#EF4444", size=55)}
          <div style="font-size:10px;font-weight:800;color:#EF4444">{pct_o:.2f}%</div>
          <div style="font-size:7px;color:#64748B">{_fmt_cop(obl)}</div>
          <div style="font-size:6.5px;color:#94A3B8">del total apropiado</div>
        </div>
        <div style="text-align:center;background:rgba(100,116,139,.05);border:1px solid rgba(100,116,139,.1);border-radius:5px;padding:6px 2px">
          <div style="font-size:7px;color:#475569;text-transform:uppercase;margin-bottom:2px">Disponible</div>
          {_gauge_pdf(pct_d, "", "#64748B", size=55)}
          <div style="font-size:10px;font-weight:800;color:#64748B">{pct_d:.2f}%</div>
          <div style="font-size:7px;color:#64748B">{_fmt_cop(disp)}</div>
          <div style="font-size:6.5px;color:#94A3B8">Sin compromiso asignado</div>
        </div>
      </div>
      <div style="background:rgba(245,158,11,.04);border:1px solid rgba(245,158,11,.1);border-radius:5px;padding:8px 10px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">
          <div>
            <div style="font-size:8px;color:#B45309;text-transform:uppercase;font-weight:700">Ejecución sobre Comprometido</div>
            <div style="font-size:7px;color:#64748B">De {_fmt_cop(comp)} comprometidos</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:14px;font-weight:800;color:#0F172A">{ejec_sobre_comp:.2f}%</div>
            <div style="font-size:7px;color:#EF4444">{_fmt_cop(obl)} obligados</div>
          </div>
        </div>
        <div style="display:flex;height:14px;border-radius:3px;overflow:hidden">
          <div style="background:#EF4444;width:{obl_pct:.1f}%;display:flex;align-items:center;justify-content:center"><span style="font-size:6px;color:#fff;font-weight:700">{obl_pct>=5 and f'{obl_pct:.0f}%' or ''}</span></div>
          <div style="background:#F59E0B;width:{cno_pct:.1f}%;display:flex;align-items:center;justify-content:center"><span style="font-size:6px;color:#000;font-weight:700">{cno_pct>=5 and f'{cno_pct:.0f}%' or ''}</span></div>
          <div style="background:#64748B;width:{disp_pct:.1f}%;display:flex;align-items:center;justify-content:center"><span style="font-size:6px;color:#fff;font-weight:700">{disp_pct>=5 and f'{disp_pct:.0f}%' or ''}</span></div>
        </div>
        <div style="display:flex;gap:10px;margin-top:4px;font-size:7px">
          <span><span style="display:inline-block;width:6px;height:6px;background:#EF4444;border-radius:1px;margin-right:2px"></span>Obligado</span>
          <span><span style="display:inline-block;width:6px;height:6px;background:#F59E0B;border-radius:1px;margin-right:2px"></span>Comp. no Obl.</span>
          <span><span style="display:inline-block;width:6px;height:6px;background:#64748B;border-radius:1px;margin-right:2px"></span>Disponible</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:3px;font-size:6.5px;color:#94A3B8">
          <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
        </div>
      </div>
    """)

    # ── Comparativo por proyecto (captura del frontend o fallback Plotly) ──
    bar_b64 = captures.get("bar_comparativo")
    if not bar_b64 and proyectos:
        nombres = [p["proyecto"] for p in proyectos]
        obligs  = [p.get("obligados") or 0 for p in proyectos]
        c_no_o  = [max(0, (p.get("comprometido") or 0) - (p.get("obligados") or 0)) for p in proyectos]
        disps   = [p.get("disponible") or 0 for p in proyectos]
        bar_b64 = stacked_bar_chart(
            nombres,
            {"Obligado": obligs, "Comprometido (no Oblig.)": c_no_o, "Disponible": disps},
            "COMPARATIVO POR PROYECTO",
            colors=["#EF4444", "#F59E0B", "#64748B"],
            horizontal=True,
        )

    comparativo_card = ""
    if bar_b64:
        comparativo_card = _card_pdf("Comparativo por Proyecto (%)", f"""
          <div style="font-size:7px;color:#64748B;margin-bottom:6px">Distribución de ejecución</div>
          {_chart(bar_b64)}
          <div style="display:flex;gap:12px;justify-content:center;margin-top:4px;font-size:7px">
            <span><span style="display:inline-block;width:6px;height:6px;background:#EF4444;border-radius:1px;margin-right:2px"></span>Obligado</span>
            <span><span style="display:inline-block;width:6px;height:6px;background:#F59E0B;border-radius:1px;margin-right:2px"></span>Comprometido restante</span>
            <span><span style="display:inline-block;width:6px;height:6px;background:#64748B;border-radius:1px;margin-right:2px"></span>Disponible</span>
          </div>
        """)

    # ── Tabla detalle ──
    rows_html = ""
    for p in proyectos:
        pct_cp = (p.get("pct_comprometido") or 0) * 100
        pct_op = (p.get("pct_obligado") or 0) * 100
        rows_html += f"""
        <tr>
          <td>{p.get("proyecto","")}</td>
          <td style="text-align:right">{_fmt_cop(p.get("apropiacion"))}</td>
          <td style="text-align:right">{_fmt_cop(p.get("comprometido"))}</td>
          <td>
            {_pb(pct_cp,"#F59E0B")}
            <span style="font-size:7.5px;color:#F59E0B">{pct_cp:.1f}%</span>
          </td>
          <td style="text-align:right">{_fmt_cop(p.get("obligados"))}</td>
          <td>
            {_pb(pct_op,"#EF4444")}
            <span style="font-size:7.5px;color:#EF4444">{pct_op:.1f}%</span>
          </td>
          <td style="text-align:right">{_fmt_cop(p.get("disponible"))}</td>
        </tr>"""

    rows_html += f"""
    <tr class="tr-total">
      <td>TOTAL</td>
      <td style="text-align:right">{_fmt_cop(arop)}</td>
      <td style="text-align:right">{_fmt_cop(comp)}</td>
      <td><span style="color:#F59E0B;font-weight:700">{pct_c:.1f}%</span></td>
      <td style="text-align:right">{_fmt_cop(obl)}</td>
      <td><span style="color:#EF4444;font-weight:700">{pct_o:.1f}%</span></td>
      <td style="text-align:right">{_fmt_cop(disp)}</td>
    </tr>"""

    table = f"""
    {_section("DETALLE POR PROYECTO")}
    <table>
      <thead><tr>
        <th>Proyecto</th><th>Apropiación</th><th>Comprometido</th>
        <th style="min-width:80px">% Comp.</th><th>Obligado</th>
        <th style="min-width:80px">% Obl.</th><th>Disponible</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""

    body = kpis
    if comparativo_card:
        body += f"""
        <div class="chart-row-1-2">
          {resumen_card}
          {comparativo_card}
        </div>"""
    else:
        body += resumen_card
    body += table

    return _full_html("Ejecución Presupuestal 2026", body, str(data.get("ultima_actualizacion", "")))


# ── Contratos OR ──────────────────────────────────────────────────────────────

async def _build_contratos_or(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import grouped_bar_chart
    captures = captures or {}
    params = params or {}

    data = await _fetch("/v1/contratos-or/dashboard")
    desembolsos = data.get("desembolsos", [])
    proyectos_all = data.get("proyectos", [])

    # Obtener totalPotencia/totalUsuarios exactos desde el mismo origen del frontend
    _cs_raw: dict = {}
    try:
        _cs_raw = await _fetch_nextjs(
            "/api/colombia-solar/curva-s",
            params={"programa": "CE: Contratos OR"},
        ) or {}
    except Exception:
        pass
    _cs_cats = _cs_raw.get("categorias") or []
    _cs_proyectos: list = _cs_cats[0].get("proyectos") if _cs_cats else []
    _cs_proyectos = _cs_proyectos or []
    total_usuarios_cs = sum(p.get("usuarios") or 0 for p in _cs_proyectos) or (data.get("totalUsuarios") or 29911)
    total_potencia_cs = sum(p.get("potencia") or 0 for p in _cs_proyectos) or (data.get("totalPotencia") or 37.057)

    # Filtro por operadorDeRed (mapeado como ejecutor en el backend)
    _f_operador = params.get("operadorDeRed", "")
    proyectos = (
        [p for p in proyectos_all if p.get("ejecutor") == _f_operador]
        if _f_operador else proyectos_all
    )
    _or_banner = (
        f'<div style="background:#EDE9FE;border-left:3px solid #8B5CF6;padding:6px 10px;'
        f'font-size:9px;color:#4C1D95;margin-bottom:8px">'
        f'Filtro: Operador de Red = <strong style="color:#6D28D9">{_f_operador}</strong></div>'
        if _f_operador else ""
    )

    av_gen = data.get("avanceGeneral") or 0
    av_fin = data.get("avanceFinanciero") or 0
    av_fis = data.get("avanceFisico") or 0
    pagos_r = data.get("pagosRealizados") or 0
    pagos_p = data.get("pagosPosibles") or 0
    pct_pag = data.get("pctPagosRealizados") or 0

    ejecutores = len({p.get("ejecutor") for p in proyectos if p.get("ejecutor")})

    # ── CARD 1: RESUMEN ──
    resumen_card = _card_pdf("RESUMEN", f"""
      <div class="card-grid-2">
        {_kpi_chip_pdf("N° Contratos", _fmt_num(data.get("nContratos")), accent=True)}
        {_kpi_chip_pdf("Ejecutores", _fmt_num(ejecutores))}
        {_kpi_chip_pdf("Pagos Realizados", f"{_fmt_num(pagos_r)}/{_fmt_num(pagos_p)}")}
        {_kpi_chip_pdf("% Pagos", _pct(pct_pag), accent=True)}
      </div>
      <div style="display:flex;justify-content:space-around;margin-top:10px">
        <div style="flex:1;max-width:48%;text-align:center">{_gauge_pdf(av_fin, "Avance Financiero", "#E8A838", size=45)}</div>
        <div style="flex:1;max-width:48%;text-align:center">{_gauge_pdf(av_gen, "Avance General", "#1E293B", size=45)}</div>
      </div>
    """)

    # ── CARD 2: PROGRESO POR DESEMBOLSO ──
    desembolsos_html = ""
    for d in desembolsos:
        pct_d  = d.get("pctCompletado") or 0
        nec    = d.get("actNecesarias") or 0
        comp_d = d.get("actCompletas") or 0
        color = "#22C55E" if pct_d >= 100 else "#F59E0B"
        desembolsos_html += _progress_pdf(
            f"Desembolso {d['numero']}", pct_d, color,
            meta=f"{comp_d}/{nec} actividades"
        )
    progreso_card = _card_pdf("PROGRESO POR DESEMBOLSO", f"""
      <p class="meta" style="margin-bottom:6px">Actividades para liberar cada pago</p>
      {desembolsos_html}
      <div style="border-top:1px solid var(--border);padding-top:8px;margin-top:6px;text-align:center">
        {_gauge_pdf(av_fis, "Avance físico", "#F59E0B", size=55)}
      </div>
    """)

    # ── CARD 3: IMPACTO ESTIMADO + CONTRATOS POR EJECUTOR ──
    impacto_chips = f"""
      <div class="card-grid-2">
        {_kpi_chip_pdf("Usuarios Beneficiados", _fmt_num(total_usuarios_cs), accent=True)}
        {_kpi_chip_pdf("N° de CEs", _fmt_num(data.get("totalCes") or 2297))}
        {_kpi_chip_pdf("Inversión Total", _fmt_cop(data.get("totalInversion") or 968268668130))}
        {_kpi_chip_pdf("Potencia a Instalar", f"{_fmt_num(total_potencia_cs, dec=3)} MWp", accent=True)}
      </div>
    """
    # Contratos por ejecutor
    ejec_counter: dict = {}
    for p in proyectos:
        ej = p.get("ejecutor") or "Sin ejecutor"
        ejec_counter[ej] = ejec_counter.get(ej, 0) + 1
    total_proy = len(proyectos) or 1
    ejec_rows = ""
    for ej, cnt in sorted(ejec_counter.items(), key=lambda x: x[1], reverse=True):
        pct_e = cnt / total_proy * 100
        ejec_rows += f"""
          <div style="margin-bottom:5px">
            <div style="display:flex;justify-content:space-between;font-size:8px;margin-bottom:2px">
              <span style="color:#0F172A;font-weight:600">{ej}</span>
              <span style="color:#F59E0B;font-weight:700">{cnt} contrato{cnt != 1 and 's' or ''}</span>
            </div>
            <div class="progress-pdf-bar"><div class="progress-pdf-fill" style="width:{pct_e:.1f}%;background:#F59E0B"></div></div>
          </div>"""
    impacto_card = _card_pdf("IMPACTO ESTIMADO", impacto_chips + f"""
      <div style="border-top:1px solid var(--border);padding-top:8px;margin-top:8px">
        <div class="card-title" style="font-size:8px;margin-bottom:5px">CONTRATOS POR EJECUTOR</div>
        {ejec_rows}
      </div>
    """)

    top_cards = f"""
    {_or_banner}
    {_section("RESUMEN Y AVANCE DEL PROGRAMA")}
    <div class="card-grid-3">
      {resumen_card}
      {progreso_card}
      {impacto_card}
    </div>"""

    # ── AVANCE POR PROYECTO (horizontal grouped bar) ──
    bar_b64 = captures.get("bar_avance_proyecto")
    if not bar_b64 and proyectos:
        nombres = [(p.get("nombre", "") or "")[:28] for p in proyectos]
        bar_b64 = grouped_bar_chart(
            nombres,
            {
                "Av. General":    [p.get("avanceGeneral") or 0 for p in proyectos],
                "Av. Financiero": [p.get("avanceFinanciero") or 0 for p in proyectos],
                "Av. Físico":     [p.get("avanceFisico") or 0 for p in proyectos],
            },
            "AVANCE POR PROYECTO (%)",
            horizontal=True,
        )

    # ── CURVAS S ──
    # ── CURVAS S — screenshots del frontend (mismos datos y visual que el tablero) ──
    curvas_html = ""
    _curva_imgs = [
        captures.get("curva_obras_civiles"),
        captures.get("curva_usuarios"),
        captures.get("curva_potencia"),
        captures.get("curva_internas"),
    ]
    if any(_curva_imgs):
        _curvas_kpis = f"""
        <div class="kpi-grid" style="margin-bottom:8px">
          {_kpi("Número de Usuarios", _fmt_num(total_usuarios_cs), "", "#F59E0B")}
          {_kpi("Potencia Total Instalada", _fmt_num(total_potencia_cs, dec=3), "MWp", "#06B6D4")}
        </div>"""
        _row1 = "".join(_chart(img) for img in _curva_imgs[:2] if img)
        _row2 = "".join(_chart(img) for img in _curva_imgs[2:] if img)
        curvas_html = (
            f'{_section("CURVAS S — AVANCE DEL PROGRAMA")}'
            + _curvas_kpis
            + (f'<div class="chart-row">{_row1}</div>' if _row1 else "")
            + (f'<div class="chart-row">{_row2}</div>' if _row2 else "")
        )

    # ── TABLA DETALLE ──
    rows_html = ""
    for p in proyectos:
        av_g_p  = p.get("avanceGeneral") or 0
        av_fi_p = p.get("avanceFinanciero") or 0
        av_fs_p = p.get("avanceFisico") or 0
        rows_html += f"""
        <tr>
          <td>{p.get("nombre","")}</td>
          <td>{p.get("ejecutor","")}</td>
          <td>{p.get("departamento","")}</td>
          <td>
            {_pb(av_g_p,"#F59E0B")}
            <span style="font-size:7.5px;color:#F59E0B">{av_g_p:.1f}%</span>
          </td>
          <td>
            {_pb(av_fi_p,"#8B5CF6")}
            <span style="font-size:7.5px;color:#8B5CF6">{av_fi_p:.1f}%</span>
          </td>
          <td>
            {_pb(av_fs_p,"#10B981")}
            <span style="font-size:7.5px;color:#10B981">{av_fs_p:.1f}%</span>
          </td>
          <td style="text-align:right">
            {p.get("pagosRealizados","–")}/{p.get("totalDesembolsos","–")}
          </td>
        </tr>"""

    table = f"""
    {_section("DETALLE DE CONTRATOS")}
    <table>
      <thead><tr>
        <th>Proyecto</th><th>Ejecutor</th><th>Departamento</th>
        <th style="min-width:80px">Av. General</th>
        <th style="min-width:80px">Av. Financiero</th>
        <th style="min-width:80px">Av. Físico</th>
        <th>Pagos</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""

    body = top_cards
    if bar_b64:
        body += _section("AVANCE POR PROYECTO (%)")
        body += f'<div class="chart-tall">{_chart(bar_b64)}</div>'
    body += table + curvas_html

    return _full_html("Contratos OR 2025", body, str(data.get("ultima_actualizacion", "")))


# ── Fenoge ────────────────────────────────────────────────────────────────────

async def _build_fenoge(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import geo_scatter, bar_chart, grouped_bar_chart, line_chart
    captures = captures or {}
    params   = params   or {}

    mapa = await _fetch("/v1/fenoge/mapa")
    seg  = await _fetch("/v1/fenoge/seguimiento")

    # Aplicar filtros del usuario
    _f_region    = params.get("region", "TODOS")
    _f_contrato  = params.get("contrato", "TODOS")
    _f_comunidad = params.get("comunidad", "TODOS")

    total_ces  = mapa.get("totalCes") or 0
    avg_kwp    = mapa.get("avgKwp") or 0
    avg_benef  = mapa.get("avgBenef") or 0
    avg_inv    = mapa.get("avgInversion") or 0

    # Chip de filtros activos (aparece en el PDF si hay filtros)
    _filtros_activos = [
        f"Región: {_f_region}"    if _f_region    != "TODOS" else "",
        f"Contrato: {_f_contrato}" if _f_contrato  != "TODOS" else "",
        f"Comunidad: {_f_comunidad}" if _f_comunidad != "TODOS" else "",
    ]
    _filtros_html = " · ".join(f for f in _filtros_activos if f)
    _filtros_banner = (
        f'<div style="background:#FEF9C3;border-left:3px solid #F59E0B;padding:6px 10px;'
        f'font-size:9px;color:#713F12;margin-bottom:8px">'
        f'Filtros aplicados: <strong style="color:#92400E">{_filtros_html}</strong></div>'
        if _filtros_html else ""
    )

    # ── KPIs ──
    kpis = f"""
    {_filtros_banner}
    {_section("INDICADORES GENERALES")}
    <div class="kpi-grid">
      {_kpi("CEs Fenoge", _fmt_num(total_ces), "", "#F59E0B")}
      {_kpi("Inversión Estimada", _fmt_cop(mapa.get("totalInversion")), "",
            "", f"promedio: {_fmt_cop(avg_inv)} / CE")}
      {_kpi("Capacidad Instalada", _fmt_num(mapa.get("totalKwp"), 1), "kWp",
            "", f"promedio: {avg_kwp:.1f} kWp")}
      {_kpi("Beneficiarios", _fmt_num(mapa.get("totalBenef")), "",
            "", f"promedio: {avg_benef:.0f}")}
    </div>"""

    # ── FASES (table breakdown) ──
    detalle_fase = mapa.get("detalleFase", [])
    fases_data: dict[str, dict] = {}
    for r in detalle_fase:
        f_key = r.get("faseLabel") or r.get("fase") or "N/A"
        if f_key not in fases_data:
            fases_data[f_key] = {"count": 0, "capacidad": 0.0, "inversion": 0.0}
        fases_data[f_key]["count"]     += r.get("count") or 0
        fases_data[f_key]["capacidad"] += r.get("capacidad") or 0
        fases_data[f_key]["inversion"] += r.get("inversion") or 0

    fase_rows = ""
    for fase, vals in sorted(fases_data.items()):
        pct = vals["count"] / total_ces * 100 if total_ces else 0
        fase_rows += f"""
        <tr>
          <td><strong>{fase}</strong></td>
          <td style="text-align:right;color:#92400E">{_fmt_num(vals["count"])}</td>
          <td style="text-align:right">{pct:.1f}%</td>
          <td style="text-align:right">{_fmt_num(vals["capacidad"],1)} kWp</td>
          <td style="text-align:right">{_fmt_cop(vals["inversion"])}</td>
        </tr>"""

    fases_html = f"""
    {_section("DISTRIBUCIÓN POR FASE")}
    <table>
      <thead><tr><th>Fase</th><th style="text-align:right">N° CEs</th>
        <th style="text-align:right">%</th><th style="text-align:right">Capacidad</th>
        <th style="text-align:right">Inversión</th></tr></thead>
      <tbody>{fase_rows}</tbody>
    </table>""" if fase_rows else ""

    # ── MAPA — screenshot Leaflet del frontend (más fiel) o Plotly Scattergeo ──
    puntos = mapa.get("puntos", [])
    map_b64 = captures.get("mapa") or (
        geo_scatter(puntos, color_key="fase", title="CEs FENOGE — Mapa de Ubicación") if puntos else ""
    )

    # ── CHARTS: CEs x Dpto + Inversión x Dpto ──
    cap_barras_dept = captures.get("barras_departamento")
    por_dept = sorted(mapa.get("porDepartamento", []), key=lambda r: r["count"], reverse=True)[:15]
    bar_ces_plot = grouped_bar_chart(
        [r["departamento"] for r in por_dept],
        {
            "N° CEs":      [r["count"] for r in por_dept],
            "Capacidad÷10": [round((r.get("capacidad") or 0) / 10, 1) for r in por_dept],
        },
        "CES POR DEPARTAMENTO",
        horizontal=True,
        colors=["#F59E0B", "#06B6D4"],
    ) if por_dept else ""
    bar_inv = bar_chart(
        [r["departamento"] for r in por_dept],
        [r.get("inversion") or 0 for r in por_dept],
        "INVERSIÓN POR DEPARTAMENTO",
        "#8B5CF6", horizontal=True,
    ) if por_dept else ""

    # ── TABLA DEPARTAMENTOS ──
    all_dept = sorted(mapa.get("porDepartamento", []), key=lambda r: r["count"], reverse=True)
    dept_rows = "".join(
        f"<tr><td>{r['departamento']}</td>"
        f"<td style='text-align:right;color:#92400E'>{_fmt_num(r['count'])}</td>"
        f"<td style='text-align:right;color:#0E7490'>{_fmt_num(r.get('capacidad',0),1)} kWp</td>"
        f"<td style='text-align:right;color:#6D28D9'>{_fmt_cop(r.get('inversion',0))}</td></tr>"
        for r in all_dept
    )
    dept_table = f"""
    {_section("DETALLE POR DEPARTAMENTO")}
    <table>
      <thead><tr><th>Departamento</th><th style="text-align:right">N° CEs</th>
        <th style="text-align:right">Capacidad (kWp)</th>
        <th style="text-align:right">Inversión estimada</th></tr></thead>
      <tbody>{dept_rows}</tbody>
    </table>""" if dept_rows else ""

    # ── TABLA MUNICIPIOS (flatten por_muni) ──
    por_muni: dict = mapa.get("porMunicipio", {})
    all_munis_f = []
    for dept_name, munis in por_muni.items():
        for m in munis:
            all_munis_f.append({**m, "departamento": dept_name})
    all_munis_f.sort(key=lambda r: r.get("count", 0), reverse=True)
    muni_rows_f = "".join(
        f"<tr><td>{r['departamento']}</td><td>{r.get('municipio','')}</td>"
        f"<td style='text-align:right;color:#F59E0B'>{_fmt_num(r.get('count',0))}</td>"
        f"<td style='text-align:right;color:#06B6D4'>{_fmt_num(r.get('capacidad',0),1)} kWp</td>"
        f"<td style='text-align:right;color:#8B5CF6'>{_fmt_cop(r.get('inversion',0))}</td></tr>"
        for r in all_munis_f[:30]
    )
    muni_table_f = f"""
    {_section("DETALLE POR MUNICIPIO (Top 30)")}
    <table>
      <thead><tr><th>Departamento</th><th>Municipio</th>
        <th style="text-align:right">N° CEs</th>
        <th style="text-align:right">Capacidad (kWp)</th>
        <th style="text-align:right">Inversión estimada</th></tr></thead>
      <tbody>{muni_rows_f}</tbody>
    </table>""" if muni_rows_f else ""

    # ── CURVA S — filtrar y agregar igual que el dashboard ──
    seg_data_raw = seg.get("data", [])
    seg_data = [
        r for r in seg_data_raw
        if (_f_region    == "TODOS" or r.get("region")    == _f_region)
        and (_f_contrato  == "TODOS" or r.get("contrato")  == _f_contrato)
        and (_f_comunidad == "TODOS" or r.get("comunidad") == _f_comunidad)
    ]
    line_b64 = ""
    seg_kpis_html = ""
    if seg_data:
        # Replicar algoritmo exacto del dashboard:
        # 1) Agrupar por contrato+comunidad
        # 2) Forward-fill monotónico (valor acumulado no retrocede)
        # 3) Promediar solo series con dato en cada fecha (excluir null)
        all_dates = sorted({r["fecha"] for r in seg_data if r.get("fecha")})
        date_idx = {d: i for i, d in enumerate(all_dates)}
        n_dates = len(all_dates)

        by_key: dict = {}
        usuarios_set: dict = {}
        potencia_set: dict = {}
        for r in seg_data:
            k = f"{r.get('contrato','')}\x00{r.get('comunidad','')}"
            if k not in by_key:
                by_key[k] = {"real": [None]*n_dates, "prog": [None]*n_dates}
            if r.get("fecha") in date_idx:
                i = date_idx[r["fecha"]]
                by_key[k]["prog"][i] = r.get("programadoAcum")
                by_key[k]["real"][i] = r.get("realAcum")
            c_key = r.get("comunidad", "")
            if c_key:
                usuarios_set[c_key] = max(usuarios_set.get(c_key, 0), r.get("usuarios") or 0)
                potencia_set[c_key] = max(potencia_set.get(c_key, 0.0), float(r.get("potencia") or 0.0))

        # Monotonic forward-fill per series
        for e in by_key.values():
            lr = lp = None
            for i in range(n_dates):
                rv, pv = e["real"][i], e["prog"][i]
                if rv is not None:
                    lr = rv if lr is None else max(lr, rv)
                    e["real"][i] = lr
                elif lr is not None:
                    e["real"][i] = lr
                if pv is not None:
                    lp = pv if lp is None else max(lp, pv)
                    e["prog"][i] = lp
                elif lp is not None:
                    e["prog"][i] = lp

        # Average per date only over non-null series
        contracts = list(by_key.values())
        agg_seg = []
        for i, fecha in enumerate(all_dates):
            prog_vals = [c["prog"][i] for c in contracts if c["prog"][i] is not None]
            real_vals = [c["real"][i] for c in contracts if c["real"][i] is not None]
            if prog_vals or real_vals:
                agg_seg.append({
                    "fecha": fecha[:7],
                    "programadoAcum": round(sum(prog_vals)/len(prog_vals), 2) if prog_vals else 0,
                    "realAcum":       round(sum(real_vals)/len(real_vals), 2) if real_vals else 0,
                })
        line_b64 = line_chart(
            agg_seg, "fecha", ["programadoAcum", "realAcum"],
            "AVANCE DE OBRA — SEGUIMIENTO ACUMULADO (PROMEDIO)",
            {"programadoAcum": "Avance Programado Acumulado", "realAcum": "Avance Real Acumulado"},
            ["#06B6D4", "#F59E0B"],
        )
        total_u = sum(usuarios_set.values())
        total_p = sum(potencia_set.values())
        seg_kpis_html = f"""
        <div class="kpi-grid" style="margin-bottom:8px">
          {_kpi("Número de Usuarios", _fmt_num(total_u), "", "#F59E0B")}
          {_kpi("Potencia Total", _fmt_num(total_p, 1), "kWp", "#06B6D4")}
          {_kpi("Contratos", _fmt_num(len(set(r.get('contrato','') for r in seg_data if r.get('contrato')))))}
          {_kpi("Comunidades", _fmt_num(len(usuarios_set)))}
        </div>"""

    cap_curva_s = captures.get("curva_s")

    body = kpis + fases_html
    if map_b64:
        body += _section("CES — MAPA DE UBICACIÓN")
        body += _chart(map_b64)
    # Fila: barras por departamento (screenshot o Plotly) + inversión por departamento
    if cap_barras_dept or bar_ces_plot or bar_inv:
        body += '<div class="chart-row">'
        if cap_barras_dept:
            body += _chart(cap_barras_dept)
        elif bar_ces_plot:
            body += _chart(bar_ces_plot)
        if bar_inv:
            body += _chart(bar_inv)
        body += '</div>'
    body += dept_table + muni_table_f
    # Curva S: screenshot del frontend (incluye título y KPIs) o Plotly con KPIs
    if cap_curva_s:
        body += _chart(cap_curva_s)
    elif line_b64:
        body += _section("AVANCE DE OBRA — SEGUIMIENTO ACUMULADO")
        body += seg_kpis_html
        body += _chart(line_b64)

    return _full_html("Fenoge 1.0, 1.1", body, str(mapa.get("ultima_actualizacion", "")))


# ── Comunidades ───────────────────────────────────────────────────────────────

async def _build_comunidades(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import geo_scatter, bar_chart, pie_chart
    captures = captures or {}
    params = params or {}

    data = await _fetch("/v1/comunidades/mapa", params=params)

    impl   = data.get("implementadas") or 0
    avg_c  = data.get("avgCapacidad") or 0
    avg_u  = data.get("avgUsuarios") or 0
    avg_b  = data.get("avgBeneficiarios") or 0
    avg_i  = data.get("avgInversion") or 0

    # ── 5 KPIs ──
    stats_fechas = data.get("statsFechas") or {}
    kpis = f"""
    {_section("INDICADORES GENERALES")}
    <div class="kpi-grid-3">
      {_kpi("CEs Implementadas", _fmt_num(impl), "", "#F59E0B")}
      {_kpi("Inversión Estimada", _fmt_cop(data.get("inversionEstimada")), "",
            "", f"promedio: {_fmt_cop(avg_i)} / CE")}
      {_kpi("Capacidad Instalada", _fmt_num(data.get("capacidadKwp"),1), "kWp",
            "", f"promedio: {avg_c:.0f} kWp")}
      {_kpi("Usuarios Equiv.", f"{_fmt_num(round(data.get('usuariosEquiv') or 0))} mil", "",
            "", f"promedio: {avg_u:.0f}")}
      {_kpi("Beneficiarios", f"{_fmt_num(round(data.get('beneficiariosEquiv') or 0))} mil", "",
            "", f"promedio: {avg_b:.0f}")}
    </div>
    <p class="meta" style="margin-bottom:8px">
      {_fmt_num(stats_fechas.get("con_operacion"))} CEs con fecha de operación ·
      {_fmt_num(stats_fechas.get("con_registro"))} con fecha de registro
    </p>"""

    # ── MAPA — screenshot Leaflet del frontend (más fiel) o Plotly Scattergeo ──
    puntos = data.get("puntos", [])
    map_b64 = captures.get("mapa") or (
        geo_scatter(puntos, color_key="estado_actual", title="CES — Mapa de Ubicación") if puntos else ""
    )

    # ── 3 CHARTS: Por Estado, Por Tipo, Por Fuente ──
    # Preferimos screenshots del frontend; si fallan usamos Plotly.
    cap_est = captures.get("bar_estado")
    cap_tipo = captures.get("bar_tipo")
    cap_fuente = captures.get("bar_fuente")

    por_estado = data.get("porEstado", [])
    bar_est_plot = bar_chart(
        [r["estado"] for r in por_estado],
        [r["count"] for r in por_estado],
        "CES POR ESTADO", "#F59E0B", horizontal=True,
    ) if por_estado else ""

    por_tipo = data.get("porTipoCE", [])[:10]
    bar_tipo_plot = bar_chart(
        [r["tipo"] for r in por_tipo],
        [r["count"] for r in por_tipo],
        "CES POR TIPO DE CE", "#06B6D4", horizontal=True,
    ) if por_tipo else ""

    por_fuente_raw = sorted(
        data.get("porFuenteEnergia", []),
        key=lambda r: r["count"], reverse=True,
    )[:10]
    bar_fuente_plot = bar_chart(
        [r["fuente"] for r in por_fuente_raw],
        [r["count"] for r in por_fuente_raw],
        "CES POR TIPO DE ENERGÍA (Top 10)", "#8B5CF6", horizontal=True,
    ) if por_fuente_raw else ""

    def _chart_block(capture, plotly, title):
        if capture:
            return _chart(capture)
        if plotly:
            return _section(title) + _chart(plotly)
        return ""

    charts_3col = (
        _chart_block(cap_est, bar_est_plot, "CES POR ESTADO")
        + _chart_block(cap_tipo, bar_tipo_plot, "CES POR TIPO DE CE")
        + _chart_block(cap_fuente, bar_fuente_plot, "CES POR TIPO DE ENERGÍA")
    )
    if cap_est or cap_tipo or cap_fuente:
        charts_3col = _section("DISTRIBUCIÓN DE CEs") + charts_3col

    # ── TABLA DEPARTAMENTOS ──
    por_dept = sorted(data.get("porDepartamento", []), key=lambda r: r["count"], reverse=True)
    dept_rows = "".join(
        f"<tr><td>{r['departamento']}</td>"
        f"<td style='text-align:right;color:#92400E'>{_fmt_num(r['count'])}</td>"
        f"<td style='text-align:right;color:#0E7490'>{_fmt_num(r.get('capacidad',0),1)} kWp</td>"
        f"<td style='text-align:right;color:#6D28D9'>{_fmt_cop(r.get('inversion',0))}</td></tr>"
        for r in por_dept
    )
    dept_table = f"""
    {_section("DETALLE POR DEPARTAMENTO")}
    <table>
      <thead><tr><th>Departamento</th><th style="text-align:right">N° CEs</th>
        <th style="text-align:right">Capacidad (kWp)</th>
        <th style="text-align:right">Inversión estimada</th></tr></thead>
      <tbody>{dept_rows}</tbody>
    </table>""" if dept_rows else ""

    # ── TABLA MUNICIPIOS (top 30 por N° CEs) ──
    por_muni_raw: dict = data.get("porMunicipio", {})
    all_munis = []
    for dept, munis in por_muni_raw.items():
        for m in munis:
            all_munis.append({**m, "departamento": dept})
    all_munis.sort(key=lambda r: r.get("count", 0), reverse=True)
    muni_rows = "".join(
        f"<tr><td>{r['departamento']}</td><td>{r.get('municipio','')}</td>"
        f"<td style='text-align:right;color:#F59E0B'>{_fmt_num(r.get('count',0))}</td>"
        f"<td style='text-align:right;color:#06B6D4'>{_fmt_num(r.get('capacidad',0),1)} kWp</td>"
        f"<td style='text-align:right;color:#8B5CF6'>{_fmt_cop(r.get('inversion',0))}</td></tr>"
        for r in all_munis[:30]
    )
    muni_table = f"""
    {_section("DETALLE POR MUNICIPIO (Top 30)")}
    <table>
      <thead><tr><th>Departamento</th><th>Municipio</th>
        <th style="text-align:right">N° CEs</th>
        <th style="text-align:right">Capacidad (kWp)</th>
        <th style="text-align:right">Inversión estimada</th></tr></thead>
      <tbody>{muni_rows}</tbody>
    </table>""" if muni_rows else ""

    body = kpis
    if map_b64:
        body += _section("CES — MAPA DE UBICACIÓN")
        body += f'<div class="mapa-pdf-wrap">{_chart(map_b64)}</div>'
    body += charts_3col
    body += dept_table + muni_table

    return _full_html("Comunidades Energéticas", body, str(data.get("ultima_actualizacion", "")))


# ── Subsidios ─────────────────────────────────────────────────────────────────

async def _build_subsidios(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import grouped_bar_chart, stacked_bar_chart, combo_bar_line_chart
    captures = captures or {}
    params = params or {}

    kpis_data = await _fetch("/v1/subsidios/kpis")
    hist_data = await _fetch("/v1/subsidios/deficit-historico")

    _f_anio = params.get("anio", "Todas")
    hist_rows_all = hist_data.get("data", [])

    # Determinar el año de referencia para KPIs (igual que el dashboard: default al más reciente)
    if _f_anio and _f_anio not in ("Todas", "all", ""):
        try:
            _kpi_anio = int(_f_anio)
        except ValueError:
            _kpi_anio = None
    else:
        anios_disponibles = sorted({r.get("anio") for r in hist_rows_all if r.get("anio")})
        _kpi_anio = anios_disponibles[-1] if anios_disponibles else None
    _kpi_anio_label = str(_kpi_anio) if _kpi_anio else "Todas"

    # hist_rows: todos los años para las gráficas históricas
    hist_rows = hist_rows_all
    # hist_rows_kpi: solo el año de referencia para el KPI bar superior
    hist_rows_kpi = [r for r in hist_rows_all if r.get("anio") == _kpi_anio] if _kpi_anio else hist_rows_all

    a2025 = kpis_data.get("anio2025", {})
    a2026 = kpis_data.get("anio2026", {})

    # ── KPI BAR (deficit-historico del año de referencia) ──
    sum_sub  = sum(r.get("subsidios") or 0 for r in hist_rows_kpi)
    sum_con  = sum(r.get("contribuciones") or 0 for r in hist_rows_kpi)
    sum_def  = sum(r.get("deficit_anual") or 0 for r in hist_rows_kpi)
    sum_apr  = sum(r.get("apropiacion_pgn") or 0 for r in hist_rows_kpi)
    deficit_ac = sum(r.get("deficit_acumulado") or 0 for r in hist_rows_kpi)

    kpi_bar = f"""
    <div class="kpi-bar">
      <div class="kpi-bar-cell">
        <div class="kpi-bar-label">Vigencia</div>
        <div class="kpi-bar-val" style="font-size:11px;padding-top:4px">{_kpi_anio_label}</div>
      </div>
      <div class="kpi-bar-cell">
        <div class="kpi-bar-val">{_fmt_cop(sum_def)}</div>
        <div class="kpi-bar-label">Necesidad Presupuestal</div>
      </div>
      <div class="kpi-bar-cell">
        <div class="kpi-bar-val">{_fmt_cop(sum_apr)}</div>
        <div class="kpi-bar-label">Apropiación PGN</div>
      </div>
      <div class="kpi-bar-cell">
        <div class="kpi-bar-val">{_fmt_cop(deficit_ac)}</div>
        <div class="kpi-bar-label">Déficit Acumulado</div>
      </div>
      <div class="kpi-bar-cell">
        <div class="kpi-bar-val">{_fmt_cop(sum_sub)}</div>
        <div class="kpi-bar-label">Subsidios Agregados</div>
      </div>
      <div class="kpi-bar-cell">
        <div class="kpi-bar-val">{_fmt_cop(sum_con)}</div>
        <div class="kpi-bar-label">Contribuciones Agregados</div>
      </div>
    </div>"""

    # ── KPIs ANUALES (2025/2026) ──
    kpis_anuales = f"""
    <div class="kpi-grid">
      {_kpi("Resoluciones 2025", _fmt_num(a2025.get("resoluciones")))}
      {_kpi("Valor Asignado 2025", _fmt_cop(a2025.get("valorAsignado")))}
      {_kpi("Pagado 2025", _fmt_cop(a2025.get("pagado")), "", "#10B981")}
      {_kpi("Pendiente 2025", _fmt_cop(a2025.get("pendiente")), "", "#F59E0B")}
      {_kpi("Resoluciones 2026", _fmt_num(a2026.get("resoluciones")))}
      {_kpi("Valor Asignado 2026", _fmt_cop(a2026.get("valorAsignado")))}
      {_kpi("Pagado 2026", _fmt_cop(a2026.get("pagado")), "", "#10B981")}
      {_kpi("Déficit Acumulado", _fmt_cop(deficit_ac), "", "#EF4444")}
    </div>"""

    # ── CHART 1: Subsidios + Contribuciones grouped bar ──
    bar1_b64 = captures.get("grafico_subsidios_contribuciones")
    if not bar1_b64 and hist_rows:
        years = sorted({r["anio"] for r in hist_rows if r.get("anio")})
        bar1_b64 = grouped_bar_chart(
            [str(y) for y in years],
            {
                "Suma de Subsidios (SIN+ZNI)": [
                    (next((r for r in hist_rows if r["anio"] == y), {}).get("subsidios") or 0) / 1e6
                    for y in years
                ],
                "Suma de Contribuciones": [
                    (next((r for r in hist_rows if r["anio"] == y), {}).get("contribuciones") or 0) / 1e6
                    for y in years
                ],
            },
            "SUBSIDIOS + CONTRIBUCIONES (millones COP)",
            colors=["#F59E0B", "#D97706"],
        )

    # ── CHART 2: Déficit acumulado bar + Déficit año line + Apropiación PGN line ──
    bar2_b64 = captures.get("grafico_deficit_apropiacion")
    if not bar2_b64 and hist_rows:
        years = sorted({r["anio"] for r in hist_rows if r.get("anio")})
        bar2_b64 = combo_bar_line_chart(
            [str(y) for y in years],
            {
                "Suma de Déficit acumulado": [
                    (next((r for r in hist_rows if r["anio"] == y), {}).get("deficit_acumulado") or 0) / 1e6
                    for y in years
                ],
            },
            {
                "Suma de Déficit Año": [
                    (next((r for r in hist_rows if r["anio"] == y), {}).get("deficit_anual") or 0) / 1e6
                    for y in years
                ],
                "Suma de Apropiación PGN": [
                    (next((r for r in hist_rows if r["anio"] == y), {}).get("apropiacion_pgn") or 0) / 1e6
                    for y in years
                ],
            },
            "DÉFICIT ACUMULADO + APROPIACIÓN PGN (millones COP)",
            bar_colors=["#F59E0B"],
            line_colors=["#EF4444", "#0D9488"],
        )

    # ── CHART 3: Apropiación PGN + A-1 stacked ──
    # A-1 = déficit acumulado del año anterior (como muestra el dashboard)
    bar3_b64 = captures.get("grafico_apropiacion_a1")
    if not bar3_b64 and hist_rows:
        years = sorted({r["anio"] for r in hist_rows if r.get("anio")})
        rows_by_year = {r["anio"]: r for r in hist_rows}
        bar3_b64 = stacked_bar_chart(
            [str(y) for y in years],
            {
                "Suma de Apropiación PGN": [
                    (rows_by_year.get(y, {}).get("apropiacion_pgn") or 0) / 1e6
                    for y in years
                ],
                "Suma de A-1 (déf. acum. año anterior)": [
                    (rows_by_year.get(y - 1, {}).get("deficit_acumulado") or 0) / 1e6
                    for y in years
                ],
            },
            "APROPIACIÓN PGN + A-1 (millones COP)",
            colors=["#F59E0B", "#D97706"],
        )

    # Textos explicativos del tablero
    texto1 = """
    <div style="background:#FFFBEB;border-radius:8px;padding:12px 16px;margin:12px 0;font-size:10px;color:#1E293B;line-height:1.7;border-left:3px solid #F59E0B">
      Los subsidios de energía eléctrica se pagan principalmente con las contribuciones de los usuarios
      de los estratos 5 y 6, usuarios comerciales e industriales. Desde 2002, los subsidios han sido
      superiores a las contribuciones, constituyendo así la
      <strong style="color:#92400E">Necesidad presupuestal de la vigencia</strong> para cada año.
      (<strong>Necesidad de la vigencia</strong> = Subsidios − Contribuciones).
    </div>"""
    texto2 = """
    <div style="background:#FFF7ED;border-radius:8px;padding:12px 16px;margin:12px 0;font-size:10px;color:#1E293B;line-height:1.7;border-left:3px solid #F97316">
      <p style="margin:0 0 8px">
        La necesidad de la vigencia usualmente es cubierta con recursos del Presupuesto General de la Nación.
        Lo que no es cubierto por estos, deriva en el
        <strong>Déficit de la Vigencia</strong>.
        (Déficit de la vigencia = Recursos PGN − Déficit de la vigencia)
      </p>
      <p style="margin:0 0 8px">
        Desde el 2014 se ha venido presentando déficit en las vigencias, por lo que los saldos pendientes
        se trasladan al año siguiente para su pago. Este evento repetitivo se conoce como el
        <strong style="color:#C2410C">déficit acumulado</strong>.
        (Déficit acumulado<sub>a</sub> = Déficit de la vigencia<sub>a</sub> + Déficit de la vigencia<sub>a-1</sub>)
      </p>
      <p style="margin:0">
        Con los recursos apropiados se pagan en primera medida saldos pendientes de la vigencia anterior
        (Déficit acumulado) y su diferencia en la anualidad en curso. Para 2025, se tiene proyectado pagar
        valores pendientes de 2024 por alrededor de 1,7 o 1,8 billones y 1,36 para trimestres de 2025.
      </p>
    </div>"""

    body = (
        _section("HISTÓRICO DÉFICIT DE SUBSIDIOS DE ENERGÍA ELÉCTRICA — FSSRI")
        + kpi_bar
        + kpis_anuales
    )
    # Fila compacta: barras de subsidios/contribuciones + apropiación/A-1
    if bar1_b64 or bar3_b64:
        body += '<div class="chart-row">'
        if bar1_b64:
            body += _chart(bar1_b64)
        if bar3_b64:
            body += _chart(bar3_b64)
        body += '</div>'
    body += texto1
    # Gráfico combinado (líneas + barras) más alto para aprovechar el ancho landscape
    if bar2_b64:
        body += f'<div class="chart-tall">{_chart(bar2_b64)}</div>'
    body += texto2

    return _full_html(
        "Histórico Déficit de Subsidios de Energía Eléctrica — FSSRI",
        body,
        str(hist_data.get("ultima_actualizacion") or kpis_data.get("ultima_actualizacion", "")),
    )


# ── Entry point ───────────────────────────────────────────────────────────────


_NEXTJS_BASE = "http://localhost:3001"


async def _fetch_nextjs(path: str, params: dict | None = None) -> Any:
    """Call Next.js internal API (follows redirects, adds trailing slash)."""
    url = f"{_NEXTJS_BASE}{path}"
    if not url.endswith("/"):
        url += "/"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, params=params or {})
        r.raise_for_status()
        return r.json()


# ── Colombia Solar ────────────────────────────────────────────────────────────

async def _build_colombia_solar(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import bar_chart, grouped_bar_chart
    captures = captures or {}
    params = params or {}

    # Split comma-separated filter values into lists for multi-value params
    _multi_keys = ["programa", "departamento", "mes", "tipo", "contratista"]
    api_params: dict[str, str | list[str]] = {}
    for k, v in params.items():
        if k in _multi_keys and "," in v:
            vals = [x.strip() for x in v.split(",") if x.strip()]
            api_params[k] = vals if len(vals) > 1 else vals[0]
        else:
            api_params[k] = v

    # For eficiencia-programa, exclude "programa" (not supported by that endpoint)
    ep_params = {k: v for k, v in api_params.items() if k != "programa"}

    kpis_raw  = await _fetch_nextjs("/api/kpis", params=api_params)
    mensual   = await _fetch_nextjs("/api/chart-mensual", params=api_params)
    efic_prog = await _fetch_nextjs("/api/eficiencia-programa", params=ep_params)
    tabla_raw = await _fetch_nextjs("/api/tabla", params={**api_params, "page": "1", "limit": "10000"})
    or_raw    = await _fetch_nextjs("/api/tabla-or-inicial", params={"limit": "10000"})

    kd = kpis_raw.get("data", {})
    plan_u  = float(kd.get("planeado_usuarios") or 0)
    ejec_u  = float(kd.get("ejecutado_usuarios") or 0)
    kwp_p   = float(kd.get("kwp_planeado") or 0)
    kwp_e   = float(kd.get("kwp_ejecutado") or 0)
    efic    = float(kd.get("eficiencia_pct") or 0)

    kpis = f"""
    {_section("INDICADORES GENERALES")}
    <div class="kpi-grid">
      {_kpi("Usuarios Planeados",  _fmt_num(plan_u), "", "#E8A838")}
      {_kpi("Usuarios Ejecutados", _fmt_num(ejec_u), "", "#34D399")}
      {_kpi("kWp Planeado",        _fmt_num(kwp_p, 1), "kWp", "#FB923C")}
      {_kpi("kWp Ejecutado",       _fmt_num(kwp_e, 1), "kWp", "#60A5FA")}
    </div>"""

    gauge_html = f"""
    {_section("EFICIENCIA GENERAL")}
    <div class="chart-row">
      <div class="gauge-pdf-wrap">{_gauge_pdf(efic, "Eficiencia General", "#E8A838")}</div>
      <div class="chart-wrap" style="display:flex;align-items:center;">
        <div>
          {_kpi("Avance Usuarios", _pct(ejec_u / plan_u * 100 if plan_u else 0), "", "#34D399")}
          {_kpi("Avance kWp",      _pct(kwp_e / kwp_p * 100 if kwp_p else 0), "", "#60A5FA")}
        </div>
      </div>
    </div>"""

    # Gráfico mensual (planeado vs ejecutado usuarios)
    meses_data = mensual.get("data", [])
    bar_mensual = captures.get("bar_mensual") or (
        grouped_bar_chart(
            [r["mes"] for r in meses_data],
            {
                "Planeado":  [float(r.get("planeado") or 0) for r in meses_data],
                "Ejecutado": [float(r.get("ejecutado") or 0) for r in meses_data],
            },
            "USUARIOS POR MES — PLANEADO VS EJECUTADO",
            colors=["#FBBF24", "#34D399"],
        ) if meses_data else ""
    )

    # Gráfico eficiencia por programa
    eprog_data = efic_prog.get("data", [])
    bar_efic = captures.get("bar_eficiencia") or (
        grouped_bar_chart(
            [r["programa"] for r in eprog_data],
            {
                "Planeado":  [float(r.get("planeado") or 0) for r in eprog_data],
                "Ejecutado": [float(r.get("ejecutado") or 0) for r in eprog_data],
            },
            "AVANCE POR PROGRAMA",
            horizontal=True,
            colors=["#FBBF24", "#34D399"],
        ) if eprog_data else ""
    )

    # Tabla de eficiencia por programa
    ep_rows = "".join(
        f"<tr><td>{r['programa']}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('planeado') or 0))}</td>"
        f"<td style='text-align:right;color:#34D399'>{_fmt_num(float(r.get('ejecutado') or 0))}</td>"
        f"<td style='text-align:right;color:#F59E0B'>{float(r.get('eficiencia_pct') or 0):.1f}%</td></tr>"
        for r in eprog_data
    )
    ep_table = f"""
    <div style="break-inside:avoid;page-break-inside:avoid;">
    {_section("DETALLE POR PROGRAMA")}
    <table>
      <thead><tr><th>Programa</th><th style="text-align:right">Planeado</th>
        <th style="text-align:right">Ejecutado</th><th style="text-align:right">Eficiencia</th>
      </tr></thead>
      <tbody>{ep_rows}</tbody>
    </table>
    </div>""" if ep_rows else ""

    # ── Curvas S — screenshots del frontend (mismo origen que el tablero) ──
    curvas_cs_html = ""
    try:
        _cs_params_solar: dict = {}
        if params.get("programa"):
            _cs_params_solar["programa"] = params["programa"]
        cs_raw = await _fetch_nextjs("/api/colombia-solar/curva-s", params=_cs_params_solar or None)
        categorias = cs_raw.get("categorias", [])
        if categorias:
            _solar_projs = categorias[0].get("proyectos") or []
            total_u_cs  = sum(p.get("usuarios") or 0 for p in _solar_projs)
            total_p_cs  = sum(p.get("potencia") or 0 for p in _solar_projs)
            curvas_kpis = f"""
            <div class="kpi-grid" style="margin-bottom:8px">
              {_kpi("Número de Usuarios",       _fmt_num(total_u_cs),       "",    "#E8A838")}
              {_kpi("Potencia Total Instalada", _fmt_num(total_p_cs, dec=3), "MWp", "#60A5FA")}
            </div>"""
            _solar_imgs = [
                captures.get("curva_obras_civiles"),
                captures.get("curva_usuarios"),
                captures.get("curva_potencia"),
                captures.get("curva_internas"),
            ]
            if any(_solar_imgs):
                _row1 = "".join(_chart(img) for img in _solar_imgs[:2] if img)
                _row2 = "".join(_chart(img) for img in _solar_imgs[2:] if img)
                curvas_cs_html = (
                    f'{_section("CURVAS S — AVANCE DEL PROGRAMA")}'
                    + curvas_kpis
                    + (f'<div class="chart-row">{_row1}</div>' if _row1 else "")
                    + (f'<div class="chart-row">{_row2}</div>' if _row2 else "")
                )
    except Exception as exc:
        logger.warning("[PDF colombia-solar] Curvas S error: %s", exc)

    # ── Tabla detalle ────────────────────────────────────────────────────
    tabla_data = [r for r in tabla_raw.get("data", []) if r.get("programa") is not None]
    tabla_totals = tabla_raw.get("totals")
    td_rows = "".join(
        f"<tr>"
        f"<td>{r.get('programa','')}</td>"
        f"<td>{r.get('contratista','')}</td>"
        f"<td>{r.get('departamento','')}</td>"
        f"<td>{r.get('municipio','')}</td>"
        f"<td>{r.get('tipo_solucion','')}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('inversion') or 0), 1)}</td>"
        f"<td>{r.get('mes','')}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('planeado_usuarios') or 0))}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('ejecutado_usuarios') or 0))}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('kwp_planeado') or 0), 1)}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('kwp_ejecutado') or 0), 1)}</td>"
        f"</tr>"
        for r in tabla_data
    )
    td_footer = ""
    if tabla_totals:
        td_footer = (
            f"<tr class='tr-total' style='border-top:2px solid #E8A838'>"
            f"<td colspan='5'>TOTALES</td>"
            f"<td style='text-align:right'>{_fmt_num(float(tabla_totals.get('inversion') or 0), 1)}</td>"
            f"<td></td>"
            f"<td style='text-align:right'>{_fmt_num(float(tabla_totals.get('planeado_usuarios') or 0))}</td>"
            f"<td style='text-align:right'>{_fmt_num(float(tabla_totals.get('ejecutado_usuarios') or 0))}</td>"
            f"<td style='text-align:right'>{_fmt_num(float(tabla_totals.get('kwp_planeado') or 0), 1)}</td>"
            f"<td style='text-align:right'>{_fmt_num(float(tabla_totals.get('kwp_ejecutado') or 0), 1)}</td>"
            f"</tr>"
        )
    tabla_html = f"""
    {_section("DETALLE DE IMPLEMENTACIÓN")}
    <table style="font-size:6.5pt;">
      <thead><tr>
        <th>Programa</th><th>Contratista</th><th>Departamento</th><th>Municipio</th>
        <th>Tipo Solución</th><th style="text-align:right">Inversión</th><th>Mes</th>
        <th style="text-align:right">Planeado</th><th style="text-align:right">Ejecutado</th>
        <th style="text-align:right">kWp Plan</th><th style="text-align:right">kWp Ejec</th>
      </tr></thead>
      <tbody>{td_rows}{td_footer}</tbody>
    </table>""" if tabla_data else ""

    body = kpis + gauge_html
    if bar_mensual and bar_efic:
        body += f'<div class="chart-row">{_chart(bar_mensual, "chart-img-short")}{_chart(bar_efic, "chart-img-short")}</div>'
    else:
        if bar_mensual:
            body += _chart(bar_mensual, "chart-img-short")
        if bar_efic:
            body += _chart(bar_efic, "chart-img-short")
    # Tabla OR Inicial
    or_data = or_raw.get("data", []) if isinstance(or_raw, dict) else []
    or_totals = or_raw.get("totals") if isinstance(or_raw, dict) else None
    or_rows_html = "".join(
        f"<tr><td style='text-align:right'>{r.get('n','')}</td>"
        f"<td>{r.get('departamento','')}</td>"
        f"<td>{r.get('municipio','')}</td>"
        f"<td style='text-align:right'>{_fmt_cop(float(r.get('valor') or 0))}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('n_ce') or 0))}</td>"
        f"<td style='text-align:right'>{_fmt_num(float(r.get('usuarios') or 0))}</td>"
        f"<td style='text-align:right'>{r.get('potencia_mwp','')}</td>"
        f"<td>{r.get('or_generador','')}</td>"
        f"<td>{r.get('tipo_de_proyecto','')}</td>"
        f"<td>{r.get('zona','')}</td></tr>"
        for r in or_data
    )
    or_footer = ""
    if or_totals:
        or_footer = (
            f"<tr class='tr-total'>"
            f"<td colspan='3'>TOTAL</td>"
            f"<td style='text-align:right'>{_fmt_cop(float(or_totals.get('total_valor') or 0))}</td>"
            f"<td style='text-align:right'>{_fmt_num(float(or_totals.get('total_n_ce') or 0))}</td>"
            f"<td style='text-align:right'>{_fmt_num(float(or_totals.get('total_usuarios') or 0))}</td>"
            f"<td style='text-align:right'>{or_totals.get('total_potencia_mwp','')}</td>"
            f"<td colspan='3'></td></tr>"
        )
    or_table = f"""
    {_section("OPERADORES DE RED INICIAL")}
    <table style="font-size:6.5pt;">
      <thead><tr>
        <th style="text-align:right">N°</th><th>Departamento</th><th>Municipio</th>
        <th style="text-align:right">Valor</th><th style="text-align:right">N° CE</th>
        <th style="text-align:right">Usuarios</th><th style="text-align:right">Potencia (mWp)</th>
        <th>OR / Generador</th><th>Tipo</th><th>Zona</th>
      </tr></thead>
      <tbody>{or_rows_html}{or_footer}</tbody>
    </table>""" if or_rows_html else ""

    body += ep_table + curvas_cs_html + tabla_html + or_table

    return _full_html("Colombia Solar", body, str(kd.get("ultima_actualizacion", "")))


# ── Energía (SIN) ─────────────────────────────────────────────────────────────

# Coordenadas lat/lng de embalses Colombia
_EMBALSE_COORDS: dict[str, tuple[float, float]] = {
    "ITUANGO":         (7.5319,  -76.1986), "TRONERAS":        (7.2333,  -75.4000),
    "CALIMA1":         (3.9000,  -76.6000), "MIRAFLORES":      (6.3333,  -74.5500),
    "PLAYAS":          (6.0000,  -74.5000), "TOPOCORO":        (6.4500,  -73.5000),
    "RIOGRANDE2":      (6.5500,  -75.5000), "BETANIA":         (2.8167,  -75.2833),
    "PENOL":           (6.3167,  -74.8000), "SAN LORENZO":     (6.8333,  -75.0000),
    "AMANI":           (5.3167,  -75.6000), "MUNA":            (6.5333,  -73.0333),
    "URRA1":           (8.0333,  -76.0000), "PRADO":           (3.8333,  -75.0000),
    "SALVAJINA":       (3.5000,  -76.5000), "PUNCHINA":        (5.1333,  -75.6000),
    "PORCE II":        (6.5500,  -75.3167), "PORCE III":       (6.5200,  -75.3000),
    "AGREGADO BOGOTA": (4.6500,  -74.0833), "GUAVIO":          (4.8167,  -73.5000),
    "EL QUIMBO":       (2.4500,  -75.7500), "ESMERALDA":       (5.5000,  -72.5000),
    "CHUZA":           (4.7500,  -73.6500), "ALTOANCHICAYA":   (3.5333,  -76.6000),
}

# Mapeo embalse → región XM (para stacked area chart)
_EMBALSE_REGION_XM: dict[str, str] = {
    "PENOL": "Antioquia", "RIOGRANDE2": "Antioquia", "PORCE II": "Antioquia",
    "PORCE III": "Antioquia", "MIRAFLORES": "Antioquia", "PLAYAS": "Antioquia",
    "TRONERAS": "Antioquia", "PUNCHINA": "Antioquia", "ITUANGO": "Antioquia",
    "AGREGADO BOGOTA": "Centro", "CHUZA": "Centro", "GUAVIO": "Centro",
    "MUNA": "Centro", "SAN CARLOS": "Centro", "BETANIA": "Centro",
    "EL QUIMBO": "Centro", "PRADO": "Centro", "AMANI": "Centro",
    "ESMERALDA": "Centro", "SAN LORENZO": "Centro",
    "CALIMA1": "Valle", "ALTOANCHICAYA": "Valle", "SALVAJINA": "Valle", "FLORIDA II": "Valle",
    "URRA1": "Caribe",
    "TOPOCORO": "Oriente", "CHIVOR": "Oriente", "SOGAMOSO": "Oriente", "BATA": "Oriente",
}
_REGION_ORDER_XM = ["Antioquia", "Centro", "Oriente", "Valle", "Caribe"]
_REGION_COLORS_XM = {
    "Antioquia": "#9B8FC7", "Centro": "#C8C8C8",
    "Oriente": "#B8D4E8", "Valle": "#7EC8D0", "Caribe": "#8FA84A",
}

# Mapeo embalse → departamento (para tabla detalle)
_EMBALSE_DEPTO: dict[str, str] = {
    "ITUANGO": "Antioquia", "TRONERAS": "Antioquia", "CALIMA1": "Valle del Cauca",
    "MIRAFLORES": "Antioquia", "PLAYAS": "Antioquia", "TOPOCORO": "Santander",
    "RIOGRANDE2": "Antioquia", "BETANIA": "Huila", "PENOL": "Antioquia",
    "SAN LORENZO": "Antioquia", "AMANI": "Caldas", "MUNA": "Santander",
    "URRA1": "Córdoba", "PRADO": "Tolima", "SALVAJINA": "Valle del Cauca",
    "PUNCHINA": "Caldas", "PORCE II": "Antioquia", "PORCE III": "Antioquia",
    "AGREGADO BOGOTA": "Cundinamarca", "GUAVIO": "Cundinamarca",
    "EL QUIMBO": "Huila", "ESMERALDA": "Boyacá",
    "CHUZA": "Boyacá", "ALTOANCHICAYA": "Valle del Cauca",
}

# Mapeo río → departamento (para aportes por departamento)
_RIO_DEPTO: dict[str, str] = {
    "ITUANGO": "Antioquia", "ESCUELA DE MINAS": "Antioquia", "A. SAN LORENZO": "Antioquia",
    "NARE CP": "Antioquia", "NARE": "Antioquia", "GRANDE": "Antioquia",
    "CARLOS LLERAS": "Antioquia", "GUATAPE": "Antioquia", "PORCE2 CP": "Antioquia",
    "SAN CARLOS": "Antioquia", "GUADALUPE": "Antioquia", "PORCE III": "Antioquia",
    "CONCEPCION": "Antioquia", "SAN MIGUEL": "Antioquia", "TENCHE": "Antioquia",
    "DESV. EEPPM (NEC,PAJ,DOL)": "Antioquia", "QUEBRADONA": "Antioquia", "ESTRELLA": "Antioquia",
    "CAUCA SALVAJINA": "Valle del Cauca", "ALTOANCHICAYA": "Valle del Cauca",
    "CALIMA": "Valle del Cauca", "DIGUA": "Valle del Cauca",
    "CHINCHINA": "Caldas", "MIEL I": "Caldas", "SAN EUGENIO": "Caldas",
    "CAMPOALEGRE": "Caldas", "DESV. GUARINO": "Caldas", "DESV. MANSO": "Caldas",
    "BOGOTA N.R.": "Cundinamarca", "CUCUANA": "Cundinamarca",
    "SAN FRANCISCO": "Cundinamarca", "DESV. SAN MARCOS": "Cundinamarca",
    "GUAVIO": "Cundinamarca", "CHUZA": "Cundinamarca",
    "SOGAMOSO": "Boyacá", "BATA": "Boyacá", "DESV. BATATAS": "Boyacá",
    "DESV. CHIVOR": "Boyacá", "BLANCO": "Boyacá",
    "EL QUIMBO": "Huila", "BETANIA CP": "Tolima", "PRADO": "Tolima",
    "AMOYA": "Tolima", "SINU URRA": "Córdoba",
}


def _embalse_color(pct: float) -> str:
    if pct < 20: return "#EF4444"
    if pct < 30: return "#F97316"
    if pct < 40: return "#F59E0B"
    if pct < 60: return "#06B6D4"
    return "#22C55E"


def _embalse_label(pct: float) -> str:
    if pct < 20: return "Crítico"
    if pct < 30: return "Delicado"
    if pct < 40: return "Alerta"
    if pct < 60: return "Estable"
    return "Normal"


async def _build_energia(captures: dict[str, str] | None = None, params: dict | None = None) -> str:
    snap = await _fetch("/v1/sector/snapshot")
    dash = await _fetch("/v1/energia/dashboard")

    gen_gwh    = snap.get("generacionGwh") or 0
    precio     = snap.get("precioBolsa") or 0
    pct_emb    = snap.get("pctEmbalses") or 0
    emb_gwh    = snap.get("embalseGwh") or 0
    estado_sin = snap.get("estadoSin") or "–"
    color_sin  = snap.get("colorSin") or "#F59E0B"
    aportes    = snap.get("aportesHidricos") or {}
    ap_pct     = aportes.get("pct") or 0
    tendencias = snap.get("tendencias") or {}

    def _trend_badge(t, color=None):
        if not t:
            return ""
        label = (t.get("label") or "").upper()
        if color is None:
            if label == "ALTA":
                col = "#22C55E"
            elif label == "BAJA":
                col = "#EF4444"
            elif label == "ESTABLE":
                col = "#64748B"
            else:
                return ""
        else:
            col = color
        cambio = t.get("cambio7d")
        sig = "+" if cambio and cambio > 0 else ""
        cambio_txt = f"{sig}{cambio:.1f}%" if cambio is not None else label
        return f'<span style="display:inline-block;background:{col}15;color:{col};font-size:7px;font-weight:700;padding:1px 5px;border-radius:8px;border:1px solid {col}30;white-space:nowrap">{label} {cambio_txt}</span>'

    def _kpi_icon(label, value, unit, color, sub, icon_svg, trend=None):
        badge = _trend_badge(trend, color=color)
        sub_html = f'<div style="font-size:7px;color:#64748B;margin-top:2px">{sub}</div>' if sub else ""
        return f"""
        <div class="card-pdf" style="padding:8px 10px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">
            <span style="font-size:7px;color:#64748B;text-transform:uppercase;letter-spacing:0.03em;font-weight:700">{label}</span>
            <span style="color:{color}">{icon_svg}</span>
          </div>
          <div style="display:flex;align-items:baseline;gap:3px;flex-wrap:wrap">
            <span style="font-size:16px;font-weight:800;color:{color}">{value}</span>
            <span style="font-size:8px;color:#64748B">{unit}</span>
            {badge}
          </div>
          {sub_html}
        </div>"""

    icon_zap = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>'
    icon_trend = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 6l-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/></svg>'
    icon_drop = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>'
    icon_alert = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    icon_waves = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.6 2 5.5 2 2.8 0 2.8-2 5.5-2 1.3 0 1.9.5 2.5 1M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.6 2 5.5 2 2.8 0 2.8-2 5.5-2 1.3 0 1.9.5 2.5 1M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.6 2 5.5 2 2.8 0 2.8-2 5.5-2 1.3 0 1.9.5 2.5 1"/></svg>'

    gen_color = "#F59E0B"
    t_gen = tendencias.get("generacion")
    if t_gen and t_gen.get("label") not in (None, "S/D"):
        gen_color = {"ALTA": "#22C55E", "BAJA": "#EF4444", "ESTABLE": "#64748B"}.get(t_gen.get("label"), "#F59E0B")

    precio_color = "#F59E0B"
    t_precio = tendencias.get("precio")
    if t_precio and t_precio.get("label") not in (None, "S/D"):
        precio_color = {"ALTA": "#EF4444", "BAJA": "#22C55E", "ESTABLE": "#64748B"}.get(t_precio.get("label"), "#F59E0B")

    aportes_color = "#22C55E" if ap_pct >= 100 else ("#06B6D4" if ap_pct >= 80 else "#EF4444")
    t_aportes = tendencias.get("aportes")
    if t_aportes and t_aportes.get("label") not in (None, "S/D"):
        aportes_color = {"ALTA": "#22C55E", "BAJA": "#EF4444", "ESTABLE": "#64748B"}.get(t_aportes.get("label"), aportes_color)

    fecha_gen = snap.get("fechaGeneracion") or "últimas 24h"
    fecha_precio = snap.get("fechaPrecio") or "Promedio diario"
    fecha_emb = snap.get("fechaEmbalse") or "promedio"
    fecha_ap = snap.get("fechaAportes") or ""

    ap_actual = aportes.get("actualGwh") or 0
    ap_hist = aportes.get("historicoGwh") or 0
    ap_delta = ap_pct - 100

    kpis = f"""
    {_section("INDICADORES CLAVE — SIN")}
    <div class="card-grid-5" style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:10px">
      {_kpi_icon("Generación Total", _fmt_num(gen_gwh, 1), "GWh", gen_color, f"Generación nacional · {fecha_gen}", icon_zap, t_gen)}
      {_kpi_icon("Precio de Bolsa", f"${_fmt_num(precio, 2)}", "COP/kWh", precio_color, f"XM · {fecha_precio}", icon_trend, t_precio)}
      {_kpi_icon("% Embalses Nacional", _fmt_num(pct_emb, 2), "%", "#3B82F6", f"Volumen útil · {fecha_emb}", icon_drop, tendencias.get("embalses"))}
      {_kpi_icon("Estado SIN", estado_sin, "", color_sin if color_sin.startswith('#') else "#F59E0B", f"Embalses · {fecha_emb}", icon_alert)}
      {_kpi_icon("Aportes Hídricos", _fmt_num(ap_pct, 1), "%", aportes_color, f"{ap_actual:.1f} / {ap_hist:.1f} GWh hist. · {fecha_ap}", icon_waves, t_aportes)}
    </div>"""

    # ── Capturas del frontend ──
    cap_mapa   = (captures or {}).get("mapa", "")
    cap_pie    = (captures or {}).get("generacion_fuente", "")
    cap_precio = (captures or {}).get("precio_bolsa", "")
    cap_capac  = (captures or {}).get("capacidad_embalses", "")

    body = kpis

    # Fila 1: Mapa (2/3) + Pie generación (1/3)
    if cap_mapa and cap_pie:
        body += _section("ESTADO DE EMBALSES Y GENERACIÓN")
        body += f'<div class="chart-row-2-1">{_chart(cap_mapa)}{_chart(cap_pie)}</div>'
    elif cap_mapa:
        body += _section("ESTADO DE EMBALSES POR DEPARTAMENTO")
        body += _chart(cap_mapa)
    elif cap_pie:
        body += _section("GENERACIÓN POR FUENTE")
        body += _chart(cap_pie)

    # Fila 2: Precio de bolsa (1/2) + Capacidad embalses (1/2)
    if cap_precio and cap_capac:
        body += f'<div class="chart-row">{_chart(cap_precio)}{_chart(cap_capac)}</div>'
    else:
        if cap_precio:
            body += _section("PRECIO DE BOLSA · HISTÓRICO")
            body += _chart(cap_precio)
        if cap_capac:
            body += _section("CAPACIDAD DE EMBALSES")
            body += _chart(cap_capac)

    # ── Tabla detalle de embalses ─────────────────────────────────────────
    emb_det = dash.get("embalses", {}).get("detalle", [])
    emb_rows = ""
    for r in sorted(emb_det, key=lambda x: float(x.get("porcentaje") or 0), reverse=True):
        pct_emb_r = float(r.get("porcentaje") or 0)
        col_emb   = _embalse_color(pct_emb_r)
        nombre    = r.get("nombre") or r.get("codigo") or ""
        depto_emb = _EMBALSE_DEPTO.get(nombre.upper().strip(), "—")
        emb_rows += (
            f"<tr><td><span style='display:inline-block;width:8px;height:8px;"
            f"border-radius:50%;background:{col_emb};margin-right:5px'></span>{nombre}</td>"
            f"<td style='color:#64748B;font-size:8px'>{depto_emb}</td>"
            f"<td style='text-align:right;color:{col_emb};font-weight:700'>{pct_emb_r:.1f}%</td>"
            f"<td style='text-align:right'>{_fmt_num(r.get('capacidadGwh') or 0, 1)} GWh</td>"
            f"<td>{_pb(pct_emb_r, col_emb)}</td></tr>"
        )
    if emb_rows:
        body += f"""
        {_section("DETALLE DE EMBALSES")}
        <table>
          <thead><tr><th>Embalse</th><th>Departamento</th>
            <th style="text-align:right">% Volumen</th>
            <th style="text-align:right">Capacidad</th><th>Nivel</th></tr></thead>
          <tbody>{emb_rows}</tbody>
        </table>"""

    # ── Aportes por río ─────────────────────────────────────────────
    rios = dash.get("aportesRios", [])
    rios_rows = ""
    if rios:
        for rio in sorted(rios, key=lambda r: r.get("actualGwh") or 0, reverse=True)[:15]:
            pct_rio = rio.get("porcentaje") or 0
            rios_rows += (
                f"<tr><td>{rio.get('nombre','')}</td>"
                f"<td style='text-align:right'>{_fmt_num(rio.get('actualGwh') or 0, 1)} GWh</td>"
                f"<td style='text-align:right;color:#64748B'>{_fmt_num(rio.get('historicoGwh') or 0, 1)} GWh</td>"
                f"<td style='text-align:right;color:{'#10B981' if pct_rio>=80 else '#EF4444'}'>{pct_rio:.0f}%</td></tr>"
            )
    if rios_rows:
        body += f"""
        {_section("APORTES HÍDRICOS POR RÍO")}
        <table>
          <thead><tr><th>Río / Cuenca</th><th style="text-align:right">Actual</th>
            <th style="text-align:right">Histórico</th><th style="text-align:right">%</th></tr></thead>
          <tbody>{rios_rows}</tbody>
        </table>"""

    return _full_html("Gestión del Sector (SIN)", body, str(snap.get("ultimaActualizacion", "")))


# ── Pagos ─────────────────────────────────────────────────────────────────────

async def _build_pagos(params: dict | None = None, captures: dict | None = None) -> str:
    params = params or {}
    captures = captures or {}

    # Collect ALL filter params and pass them through to the Next.js API
    # The param names used by the frontend match what pagos-detalle expects
    _pagos_params: dict = {}
    # Pass through every param that has a non-empty, non-"all" value
    for k, v in params.items():
        if v and v not in ("", "all", "TODOS"):
            # Convert comma-separated values to list for multi-value params
            if "," in v:
                vals = [x.strip() for x in v.split(",") if x.strip()]
                _pagos_params[k] = vals if len(vals) > 1 else vals[0]
            else:
                _pagos_params[k] = v

    data = await _fetch_nextjs("/api/subsidios/pagos-detalle",
                               params=_pagos_params if _pagos_params else None)

    kpis_d   = data.get("kpis", {})
    v_asig   = kpis_d.get("valorAsignado") or 0
    v_pag    = kpis_d.get("valorPagado") or 0
    v_pend   = kpis_d.get("valorPendiente") or 0
    total_r  = kpis_d.get("totalResoluciones") or 0
    pend_r   = kpis_d.get("resolucionesPendientes") or 0
    pct_pag  = kpis_d.get("pctPagado") or 0

    # Banner de filtros activos
    _pagos_filtro_labels = {
        "prestador": "Prestador",
        "anioPago": "Año Vigencia",
        "anioExp": "Año Expedición",
        "estadoPago": "Estado",
        "resolucion": "Resolución",
        "trimestre": "Trimestre",
        "area": "Área",
        "fondo": "Fondo",
        "departamento": "Departamento",
    }
    _filtros_parts = []
    for k, v in params.items():
        if v and v not in ("", "all", "TODOS"):
            label = _pagos_filtro_labels.get(k, k)
            _filtros_parts.append(f"{label}: {v}")
    _pagos_filtros = " · ".join(_filtros_parts)
    _pagos_banner = (
        f'<div style="background:#DCFCE7;border-left:3px solid #22C55E;padding:6px 10px;'
        f'font-size:9px;color:#14532D;margin-bottom:8px">'
        f'Filtros aplicados: <strong style="color:#166534">{_pagos_filtros}</strong></div>'
        if _pagos_filtros else ""
    )

    kpis = f"""
    {_pagos_banner}
    {_section("INDICADORES GENERALES")}
    <div class="kpi-grid">
      {_kpi("Valor Comprometido", _fmt_cop(v_asig), "", "#F59E0B")}
      {_kpi("Valor Pagado",       _fmt_cop(v_pag),  "", "#22C55E")}
      {_kpi("Valor Pendiente",    _fmt_cop(v_pend), "", "#EF4444")}
      {_kpi("% Pagado",           _pct(pct_pag),    "", "#F59E0B")}
    </div>
    <div class="kpi-grid">
      {_kpi("Total Resoluciones",     _fmt_num(total_r))}
      {_kpi("Resoluciones Pendientes", _fmt_num(pend_r), "", "#EF4444")}
    </div>"""

    gauge_html = _gauge_pdf(pct_pag, "% Pagado", "#22C55E")

    # Tabla de pagos por trimestre (nativa — evita Plotly/Kaleido)
    trimestres = data.get("trimestres", [])
    trim_rows = "".join(
        f"<tr><td>{r.get('periodo','')}</td>"
        f"<td style='text-align:right;color:#22C55E'>{_fmt_cop(r.get('pagado') or 0)}</td>"
        f"<td style='text-align:right;color:#EF4444'>{_fmt_cop(r.get('pendiente') or 0)}</td></tr>"
        for r in trimestres[-20:]
    )
    trim_table = f"""
    {_section("PAGOS POR TRIMESTRE")}
    <table>
      <thead><tr>
        <th>Período</th>
        <th style="text-align:right">Pagado</th>
        <th style="text-align:right">Pendiente</th>
      </tr></thead>
      <tbody>{trim_rows}</tbody>
    </table>""" if trim_rows else ""

    # Tabla resoluciones
    resoluciones = data.get("resoluciones", [])[:30]
    res_rows = "".join(
        f"<tr><td>{r.get('noResolucion','')}</td>"
        f"<td style='text-align:right'>{r.get('anio','')}</td>"
        f"<td style='text-align:right'>{_fmt_cop(r.get('valorAsignado') or 0)}</td>"
        f"<td style='text-align:right;color:#22C55E'>{_fmt_cop(r.get('valorPagado') or 0)}</td>"
        f"<td style='text-align:right;color:#EF4444'>{_fmt_cop(r.get('saldoPendiente') or 0)}</td></tr>"
        for r in resoluciones
    )
    res_table = f"""
    {_section("RESOLUCIONES")}
    <table>
      <thead><tr><th>N° Resolución</th><th style="text-align:right">Año</th>
        <th style="text-align:right">Comprometido</th>
        <th style="text-align:right">Pagado</th>
        <th style="text-align:right">Pendiente</th></tr></thead>
      <tbody>{res_rows}</tbody>
    </table>""" if res_rows else ""

    # Tabla prestadores con saldo pendiente (nativa — evita Plotly/Kaleido)
    prest = data.get("prestadoresPendientes", [])[:15]
    prest_rows = "".join(
        f"<tr><td>{r.get('nombre','')}</td>"
        f"<td style='text-align:right;color:#EF4444'>{_fmt_cop(r.get('saldoPendiente') or 0)}</td></tr>"
        for r in prest
    )
    prest_table = f"""
    {_section("PRESTADORES CON SALDO PENDIENTE")}
    <table>
      <thead><tr>
        <th>Prestador</th>
        <th style="text-align:right">Saldo Pendiente</th>
      </tr></thead>
      <tbody>{prest_rows}</tbody>
    </table>""" if prest_rows else ""

    # Gráficos: screenshot del frontend (preferido) o tabla nativa como fallback
    trim_img = captures.get("bar_trimestral")
    trim_content = (
        f'{_section("PAGOS POR TRIMESTRE")}{_chart(trim_img, "chart-full")}'
        if trim_img else trim_table
    )
    prest_img = captures.get("bar_prestadores")
    prest_content = (
        f'{_section("PRESTADORES CON SALDO PENDIENTE")}{_chart(prest_img, "chart-full")}'
        if prest_img else prest_table
    )

    body = kpis
    # Layout 2/3 + 1/3 igual al frontend: gráfico trimestres + gauge
    body += f"""
    <div style="display:flex;gap:6mm;align-items:flex-start;margin-bottom:6mm">
      <div style="flex:2 1 0;min-width:0">{trim_content}</div>
      <div style="flex:1 1 0;min-width:0;text-align:center">{gauge_html}</div>
    </div>"""
    body += res_table
    body += prest_content

    return _full_html("Detalle de Pagos — Subsidios", body,
                      str(data.get("fechaCorte", "")))


# ── Validaciones ──────────────────────────────────────────────────────────────

async def _build_validaciones(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import stacked_bar_chart
    captures = captures or {}
    params = params or {}

    data = await _fetch("/v1/subsidios/validaciones", params=params)

    resumen    = data.get("resumen", {})
    total_prest = data.get("totalPrestadores") or 0
    ts          = data.get("ultimaActualizacion") or ""

    ESTADOS = ["a. Otros", "b. VI", "c. VI SP", "d. VP", "e. VF"]
    LABELS  = {"a. Otros": "Otros", "b. VI": "VI", "c. VI SP": "VI SP",
               "d. VP": "VP", "e. VF": "VF"}
    COLORS  = {"a. Otros": "#94A3B8", "b. VI": "#B45309", "c. VI SP": "#78350F",
               "d. VP": "#F59E0B", "e. VF": "#E8A838"}

    total_cuentas = sum(resumen.get(e, 0) for e in ESTADOS)

    # Etiqueta de la fecha de actualización filtrada
    _month_names = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio",
                    "Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    _fa = params.get("fechaActualizacion", "")
    _fecha_label = ""
    if _fa and len(_fa) >= 7:
        try:
            _fa_y = int(_fa[:4])
            _fa_m = int(_fa[5:7])
            _fecha_label = f"{_month_names[_fa_m - 1]} {_fa_y}"
        except (ValueError, IndexError):
            _fecha_label = _fa
    _fecha_chip = (
        f'<p style="margin:0 0 10px;font-size:11px;color:#64748B;">'
        f'Fecha de actualización: <strong style="color:#E8A838;">{_fecha_label}</strong></p>'
        if _fecha_label else ""
    )

    kpis = f"""
    {_section("RELACIÓN DE CUENTAS — VALIDACIONES")}
    {_fecha_chip}
    <div class="kpi-grid">
      {_kpi("Validación Final (VF)", _fmt_num(resumen.get("e. VF", 0)), "", "#E8A838")}
      {_kpi("Validación Pendiente (VP)", _fmt_num(resumen.get("d. VP", 0)), "", "#F59E0B")}
      {_kpi("Val. Inicial Saldo (VI SP)", _fmt_num(resumen.get("c. VI SP", 0)), "", "#B45309")}
      {_kpi("Validación Inicial (VI)", _fmt_num(resumen.get("b. VI", 0)), "", "#78350F")}
    </div>
    <div class="kpi-grid">
      {_kpi("Total Cuentas", _fmt_num(total_cuentas), "", "#F59E0B")}
      {_kpi("Total Prestadores", _fmt_num(total_prest))}
    </div>"""

    # Stacked bars por área (SIN y ZNI por separado) con granularidad trimestral
    # Dashboard excluye "a. Otros"
    ESTADOS_VALIDOS = ["b. VI", "c. VI SP", "d. VP", "e. VF"]
    serie = data.get("serie", [])
    from collections import defaultdict

    def _build_trim_chart(area: str) -> str:
        by_trim: dict = defaultdict(lambda: {e: 0 for e in ESTADOS_VALIDOS})
        for row in serie:
            if row.get("area") != area:
                continue
            estado = row.get("estado") or ""
            if estado not in ESTADOS_VALIDOS:
                continue
            label = f"{row.get('anio')} T{row.get('trimestre')}"
            by_trim[label][estado] += row.get("conteo") or 0
        trims = sorted(by_trim.keys())
        if not trims:
            return ""
        return stacked_bar_chart(
            trims,
            {LABELS.get(e, e): [by_trim[t].get(e, 0) for t in trims] for e in ESTADOS_VALIDOS},
            f"CUENTAS POR TRIMESTRE — {area}",
            colors=[COLORS[e] for e in ESTADOS_VALIDOS],
        )

    bar_sin = captures.get("bar_sin") or _build_trim_chart("SIN")
    bar_zni = captures.get("bar_zni") or _build_trim_chart("ZNI")

    # Tabla resumen por estado
    summary_rows = ""
    for e in ESTADOS:
        cnt = resumen.get(e, 0)
        if not cnt:
            continue
        color_dot = COLORS.get(e, "#aaa")
        label_e = LABELS.get(e, e)
        pct_e = cnt / total_cuentas * 100 if total_cuentas else 0
        summary_rows += (
            f"<tr><td><span style='display:inline-block;width:10px;height:10px;"
            f"border-radius:2px;background:{color_dot};margin-right:6px'></span>{label_e}</td>"
            f"<td style='text-align:right;font-weight:700'>{_fmt_num(cnt)}</td>"
            f"<td style='text-align:right;color:#64748B'>{pct_e:.1f}%</td></tr>"
        )
    sum_table = f"""
    {_section("RESUMEN POR ESTADO")}
    <table>
      <thead><tr><th>Estado</th><th style="text-align:right">Cuentas</th>
        <th style="text-align:right">%</th></tr></thead>
      <tbody>{summary_rows}</tbody>
    </table>""" if summary_rows else ""

    body = kpis + sum_table
    if bar_sin and bar_zni:
        body += f'<div class="chart-row">{_chart(bar_sin, "chart-img-short")}{_chart(bar_zni, "chart-img-short")}</div>'
    else:
        if bar_sin:
            body += _chart(bar_sin, "chart-img-short")
        if bar_zni:
            body += _chart(bar_zni, "chart-img-short")

    return _full_html("Validaciones de Cuentas — Subsidios", body, ts)


# ── Predicciones SIN ─────────────────────────────────────────────────────────

async def _build_predicciones(captures: dict | None = None, params: dict | None = None) -> str:
    from domain.services.tablero_charts import line_chart
    captures = captures or {}

    data = await _fetch_nextjs("/api/predicciones")

    emb      = data.get("embalses", {})
    oni_d    = data.get("oni", {})
    metricas = data.get("metricas", [])
    generado = data.get("generado_en") or ""

    emb_actual = float((emb.get("actual") or {}).get("valor") or 0)
    emb_pico_v = float((emb.get("pico") or {}).get("valor") or 0)
    emb_pico_f = (emb.get("pico") or {}).get("fecha") or "–"
    emb_pico_d = (emb.get("pico") or {}).get("dias_desde_hoy") or 0
    mape       = float(emb.get("mape") or 0) * 100
    confianza  = float(emb.get("confianza") or 0) * 100
    mape_riguroso = bool(emb.get("mape_es_riguroso"))
    cobertura_ci  = emb.get("cobertura_ci")
    backtest_info = emb.get("backtest") or {}
    # Fase 41 (2026-08-30): el error real varía según el año de corte usado
    # para entrenar (verificado: 2022->22.6%, 2024->9.3%) — cuando hay más
    # de un año evaluado, se comunica el rango en vez de un solo número.
    mape_rango_min = emb.get("mape_rango_min")
    mape_rango_max = emb.get("mape_rango_max")
    mape_anios_evaluados = emb.get("mape_anios_evaluados") or []
    hay_rango_real = (
        mape_rango_min is not None and mape_rango_max is not None
        and float(mape_rango_max) > float(mape_rango_min)
    )
    mape_rango_texto = (
        f"{float(mape_rango_min)*100:.1f}%-{float(mape_rango_max)*100:.1f}%"
        if hay_rango_real else ""
    )
    mape_anios_texto = " y ".join(str(a) for a in mape_anios_evaluados)
    modelo     = emb.get("modelo") or "–"
    oni_val    = oni_d.get("actual")
    oni_estado = oni_d.get("estado") or "–"
    pdo_fase   = (oni_d.get("pdo") or {}).get("fase") or "–"
    pdo_val    = (oni_d.get("pdo") or {}).get("actual")
    soi_val    = (oni_d.get("soi") or {}).get("actual")
    gmst_val   = (oni_d.get("gmst") or {}).get("actual")
    oni_fc     = oni_d.get("forecast", [])  # needed by diagnostico block before redefinition

    kpis = f"""
    {_section("ESTADO Y PREDICCIÓN — EMBALSES SIN")}
    <div class="kpi-grid">
      {_kpi("Nivel Actual", f"{emb_actual:.1f}", "%", "#3B82F6")}
      {_kpi("Pico Proyectado", f"{emb_pico_v:.1f}",
            f"% — {str(emb_pico_f)[:10]} ({emb_pico_d}d)", "#22C55E")}
      {_kpi("Precisión Modelo", f"{100-mape:.1f}" if not hay_rango_real else "—",
            (f"% MAPE {mape_rango_texto} — rango histórico validado" if hay_rango_real
             else f"% (MAPE={mape:.2f}%{' — validación rigurosa' if mape_riguroso else ' — prueba interna'})"), "#F59E0B")}
      {_kpi("Cobertura del intervalo", f"{(cobertura_ci or 0)*100:.0f}" if cobertura_ci is not None else "–",
            "%", "#A78BFA")}
    </div>
    {_section("VARIABLES CLIMÁTICAS")}
    <div class="kpi-grid">
      {_kpi("ONI", f"{oni_val:.2f}" if oni_val is not None else "–",
            f"({oni_estado})",
            "#EF4444" if float(oni_val or 0) > 0 else "#3B82F6")}
      {_kpi("PDO", f"{pdo_val:.2f}" if pdo_val is not None else "–",
            f"({pdo_fase})", "#F59E0B")}
      {_kpi("SOI", f"{soi_val:.2f}" if soi_val is not None else "–", "", "#0D9488")}
      {_kpi("GMST", f"{gmst_val:.2f}" if gmst_val is not None else "–", "°C",
            "#EF4444")}
    </div>"""

    # ── DIAGNÓSTICO NARRATIVO (replica DiagnosticoNarrativo del dashboard) ──
    diagnostico_html = ""
    try:
        _oni_v = float(oni_val or 0)
        _gmst_v = float(gmst_val or 0)
        _soi_v  = float(soi_val  or 0)
        _pdo_v  = float(pdo_val  or 0)

        def _oni_color(v: float) -> str:
            return "#EF4444" if v >= 1.5 else "#F97316" if v >= 0.5 else "#38BDF8" if v <= -0.5 else "#94A3B8"
        def _oni_label(v: float) -> str:
            return "Muy Fuerte" if v >= 1.5 else "Fuerte" if v >= 1.0 else "Moderado" if v >= 0.5 else "Débil o neutro"
        def _soi_label(v: float) -> str:
            if v < -1.0: return "El Niño atm."
            if v > 1.0:  return "La Niña atm."
            if v < -0.5: return "El Niño leve atm."
            if v > 0.5:  return "La Niña leve atm."
            return "Neutro atm."

        _oni_col   = _oni_color(_oni_v)
        _oni_lbl   = _oni_label(_oni_v)
        _soi_lbl   = _soi_label(_soi_v)
        _riesgo    = ("buenas reservas hídricas" if emb_pico_v >= 75
                      else "reservas moderadas" if emb_pico_v >= 60
                      else "reservas limitadas")
        _onilag    = oni_fc[0] if oni_fc else None
        _onilag_v  = float(_onilag["valor"]) if _onilag else 0.0
        _onilag_col = _oni_color(_onilag_v)
        _maxfc     = max(oni_fc, key=lambda x: float(x["valor"])) if oni_fc else None

        # Primer punto con valor >= 80 (meta operativa)
        _pred_all_pts = emb.get("prediccion", [])
        _th80 = next((p for p in _pred_all_pts if float(p.get("valor") or 0) >= 80), None)
        _fecha_meta80 = _th80["fecha"][:10] if _th80 else None
        _dias_meta80  = None
        if _th80:
            from datetime import date as _date
            _d = _date.fromisoformat(_th80["fecha"][:10])
            _dias_meta80 = (_d - _date.today()).days

        # Ventana de riesgo: valle post-pico ±45 días
        _pico_date_str = emb_pico_f[:10] if emb_pico_f and len(str(emb_pico_f)) >= 10 else None
        _risk_text = "el segundo semestre"
        if _pico_date_str and _pred_all_pts:
            from datetime import date as _date, timedelta as _td
            _pico_d = _date.fromisoformat(_pico_date_str)
            post_peak = [p for p in _pred_all_pts if _date.fromisoformat(p["fecha"][:10]) > _pico_d]
            if post_peak:
                _valle = min(post_peak, key=lambda p: float(p.get("valor") or 100))
                _vt = _date.fromisoformat(_valle["fecha"][:10])
                _months_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
                def _fmt_my(d: _date) -> str:
                    return f"{_months_es[d.month-1]} de {d.year}"
                _risk_text = f"{_fmt_my(_vt - _td(days=45))} y {_fmt_my(_vt + _td(days=45))}"

        _card = lambda lbl, val, tag, col, note="": f"""
          <div style="background:#F8FAFC;border-radius:8px;padding:10px 12px;border:1px solid #E2E8F0">
            <div style="font-size:8px;color:#64748B;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">{lbl}</div>
            <div style="font-size:16px;font-weight:700;color:{col}">{val}</div>
            <div style="margin-top:4px;display:inline-block;font-size:8px;font-weight:600;padding:2px 6px;border-radius:4px;background:{col}22;color:{col}">{tag}</div>
            {f'<div style="font-size:8px;color:#64748B;margin-top:4px">{note}</div>' if note else ''}
          </div>"""

        _kpi_cards = f"""
          {_card("ONI · Temperatura Pacífico",
                 f"{'+' if _oni_v > 0 else ''}{_oni_v:.2f}°C",
                 f"El Niño {_oni_lbl}", _oni_col,
                 f"Fuente: NOAA CPC")}
          {_card("ONI rezagado · Efecto en ríos",
                 f"{'+' if _onilag_v > 0 else ''}{_onilag_v:.2f}°C",
                 _onilag["fecha"][:10] if _onilag else "–", _onilag_col,
                 f"Proyección: {_onilag['fecha'][:7] if _onilag else '–'}")}
          {_card("PDO · Ciclo oceánico largo plazo",
                 f"{'+' if _pdo_v > 0 else ''}{_pdo_v:.2f}",
                 pdo_fase or "–", "#A78BFA",
                 "Fuente: NOAA PSL")}
          {_card("SOI · Presión atmosférica",
                 f"{'+' if _soi_v > 0 else ''}{_soi_v:.2f}",
                 _soi_lbl, "#2DD4BF",
                 "Fuente: NOAA CPC")}
          {_card("GMST · Temp. media global",
                 f"+{_gmst_v:.2f}°C",
                 "Récord instrumental", "#F87171",
                 "Fuente: NASA GISTEMP v4")}"""

        _meta80_text = ""
        if _fecha_meta80 and _dias_meta80 is not None:
            _meta80_text = (f" La proyección supera por primera vez la "
                            f"<strong style='color:#22C55E'>meta del 80%</strong> el "
                            f"<strong style='color:#22C55E'>{_fecha_meta80}</strong> "
                            f"(en {_dias_meta80} días).")

        _maxfc_text = ""
        if _maxfc:
            _maxfc_text = (f", con pronóstico de la NOAA hasta "
                           f"<strong style='color:#F97316'>+{float(_maxfc['valor']):.1f}°C</strong>"
                           f" hacia {str(_maxfc['fecha'])[:7]}")

        _resumen = f"""Hoy los embalses del SIN están al
          <strong style="color:#1E293B">{emb_actual:.1f}%</strong> de su capacidad útil —
          <strong style="color:#0F172A">{_riesgo}</strong>.{_meta80_text}
          El modelo proyecta un pico de
          <strong style="color:#D97706">{emb_pico_v:.1f}%</strong> el
          <strong style="color:#D97706">{str(emb_pico_f)[:10]}</strong> (en {emb_pico_d} días), tras lo cual
          la señal de El Niño activo
          <strong style="color:{_oni_col}">(ONI {'+' if _oni_v>0 else ''}{_oni_v:.2f}°C — {_oni_lbl})</strong>
          y el calentamiento global
          <strong style="color:#DC2626">(+{_gmst_v:.2f}°C)</strong>
          activarán un descenso sostenido:
          <strong style="color:#DC2626">la ventana de mayor riesgo energético se ubica entre {_risk_text}</strong>.
          Pronóstico basado principalmente en el índice ONI (NOAA), con cinco señales
          climáticas adicionales (NASA, XM) como contexto complementario. {
            (f"Validado entrenando el modelo con distintos años de corte ({mape_anios_texto}): el error real "
             f"observado varió entre <strong style='color:#16A34A'>{mape_rango_texto}</strong> según el año — "
             f"no es una cifra fija (ver detalle).")
            if hay_rango_real else
            (("Validado comparando el modelo contra " + str(backtest_info.get('n_dias_test', 'cientos de'))
              + " días reales ya ocurridos (entrenado solo con datos anteriores a ese período): error real del "
              if mape_riguroso else "En pruebas internas el modelo tuvo un error promedio del ")
             + f'<strong style="color:#16A34A">{mape:.2f}%</strong> (ver detalle).')
          }"""

        _detalle = f"""Para proyectar el nivel de los embalses del Sistema Interconectado Nacional, se combinan
        dos métodos de predicción entrenados sobre <strong>26 años de datos históricos</strong>.
        El primero, <strong>Prophet</strong> (Meta), reconoce automáticamente los dos ciclos lluviosos anuales
        de la cordillera andina colombiana y se ajusta con seis señales climáticas e hidrológicas. El segundo,
        <strong>SARIMAX</strong>, es más simple: incorpora directamente en su estructura solo el índice
        oceánico ONI (sin las otras cinco señales). Los dos resultados se combinan ponderando más al que
        haya sido históricamente más preciso.
        {(f'La precisión reportada ({mape_rango_texto}) viene de correr esta misma validación rigurosa con '
          f'más de un año de corte ({mape_anios_texto}): se entrenó el modelo solo con datos hasta finales de '
          f'cada año (sin dejarle ver lo que pasó después) y se compararon sus pronósticos contra los días '
          f'reales que efectivamente ocurrieron después. El resultado varió bastante según el año — '
          f'<strong>{mape_rango_texto}</strong> de error real— lo que indica que la precisión depende de '
          f'qué tan parecidas fueron las condiciones climáticas del período entrenado a las del período '
          f'validado, no de una capacidad fija del modelo. En el seguimiento semana a semana de pronósticos '
          f'ya publicados el error también ha rondado el 7% en promedio, con picos puntuales de hasta 30%.'
          if hay_rango_real else
          f'La precisión reportada ({mape:.2f}%) viene de una validación rigurosa: se entrenó el modelo solo '
          f'con datos hasta finales de {backtest_info.get("anio_corte", "—")} (sin dejarle ver lo que pasó '
          f'después) y se compararon sus pronósticos contra los <strong>{backtest_info.get("n_dias_test", "—")} '
          f'días reales</strong> que efectivamente ocurrieron después — un período que incluye El Niño activo '
          f'y transiciones climáticas reales, no solo condiciones estables. En el seguimiento semana a semana '
          f'de pronósticos ya publicados el error también ha rondado el 7% en promedio, con picos puntuales de '
          f'hasta 30%.'
          if mape_riguroso else
          f'En una prueba interna sobre <strong>180 días históricos</strong>, el sistema registró un error '
          f'medio absoluto del <strong>{mape:.2f}%</strong>.')}<br><br>
        El ONI registra <strong style="color:{_oni_col}">{'+' if _oni_v>0 else ''}{_oni_v:.2f}°C (El Niño {_oni_lbl})</strong>{_maxfc_text}
        — es la única señal con un pronóstico real hacia adelante; las demás se mantienen en su valor
        actual o se asumen en condición normal para las fechas futuras.
        El PDO (<strong style="color:#A78BFA">{'+' if _pdo_v > 0 else ''}{_pdo_v:.2f}, {pdo_fase}</strong>)
        {'amplifica' if (pdo_fase or '').endswith('+') else 'atenúa'} el episodio en curso.
        El SOI registra <strong style="color:#2DD4BF">{'+' if _soi_v > 0 else ''}{_soi_v:.2f} ({_soi_lbl})</strong>.
        La anomalía GMST es <strong style="color:#F87171">+{_gmst_v:.2f}°C</strong> —el valor más alto del
        registro instrumental—, parte del trasfondo de un planeta más caliente que puede intensificar
        el impacto regional de El Niño."""

        diagnostico_html = f"""
        <div style="border:1px solid #E8A838;border-radius:10px;background:#FFFBEB;padding:16px;margin-bottom:16px">
          <div style="font-size:10px;font-weight:700;color:#92400E;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px">
            Diagnóstico Climático · Análisis del sistema de predicción
          </div>
          <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px">
            {_kpi_cards}
          </div>
          <div style="font-size:10px;color:#1E293B;line-height:1.8;margin-bottom:10px">
            {_resumen}
          </div>
          <div style="font-size:9.5px;color:#475569;line-height:1.7;border-top:1px solid #E2E8F0;padding-top:10px">
            {_detalle}
          </div>
        </div>"""
    except Exception as _exc:
        logger.warning("[PDF predicciones] DiagnosticoNarrativo error: %s", _exc)

    # Tabla métricas
    m_rows = ""
    for m in metricas:
        tend = m.get("tendencia") or ""
        tend_color = "#22C55E" if tend == "baja" else "#EF4444" if tend == "alta" else "#F59E0B"
        m_rows += (
            f"<tr><td><strong>{m.get('nombre','')}</strong></td>"
            f"<td style='text-align:right'>"
            f"{_fmt_num(float(m.get('actual') or 0), 2)} {m.get('unidad','')}</td>"
            f"<td style='text-align:right;color:{tend_color}'>"
            f"{_fmt_num(float(m.get('prediccion_7d') or 0), 2)} {m.get('unidad','')}</td>"
            f"<td style='text-align:right;color:#64748B'>"
            f"{float(m.get('mape') or 0)*100:.2f}%</td>"
            f"<td style='text-align:right;color:{tend_color}'>{tend}</td></tr>"
        )
    m_table = f"""
    {_section("MÉTRICAS Y PREDICCIONES A 7 DÍAS")}
    <table>
      <thead><tr><th>Métrica</th><th style="text-align:right">Actual</th>
        <th style="text-align:right">Pred. 7d</th>
        <th style="text-align:right">MAPE</th>
        <th style="text-align:right">Tendencia</th></tr></thead>
      <tbody>{m_rows}</tbody>
    </table>
    <p style="font-size:8px;color:#64748B;margin-top:4px">Modelo: {modelo}</p>""" if m_rows else ""

    # Curva de predicción de embalses (próximos 60 días)
    pred_pts = emb.get("prediccion", [])[:60]
    emb_chart = captures.get("curva_embalses") or ""
    if not emb_chart and pred_pts:
        series = [{"fecha": p["fecha"], "pred": p.get("valor"),
                   "inf": p.get("lower"), "sup": p.get("upper")}
                  for p in pred_pts]
        emb_chart = line_chart(
            series, "fecha", ["pred", "inf", "sup"],
            "PREDICCIÓN NIVEL EMBALSES — 60 DÍAS",
            {"pred": "Proyectado", "inf": "Límite inf.", "sup": "Límite sup."},
            ["#3B82F6", "#94A3B8", "#94A3B8"],
        )

    # ONI forecast grid (tabla + chart)
    oni_fc = oni_d.get("forecast", [])
    oni_chart = captures.get("pronostico_oni") or ""
    oni_table = ""
    if oni_fc:
        if not oni_chart:
            oni_series = [{"fecha": p["fecha"], "oni": p["valor"]} for p in oni_fc]
            oni_chart = line_chart(
                oni_series, "fecha", ["oni"],
                "PRONÓSTICO ONI",
                {"oni": "ONI"},
                ["#EF4444"],
            )
        oni_rows = ""
        for p in oni_fc:
            v = p.get("valor") or 0
            color_oni = "#EF4444" if v > 0.5 else "#3B82F6" if v < -0.5 else "#94A3B8"
            oni_rows += (
                f"<tr><td>{str(p.get('fecha',''))[:10]}</td>"
                f"<td style='text-align:right;color:{color_oni};font-weight:700'>{v:.2f}</td>"
                f"<td style='color:{color_oni}'>"
                f"{'El Niño' if v>0.5 else 'La Niña' if v<-0.5 else 'Neutral'}</td></tr>"
            )
        oni_table = f"""
        {_section("PRONÓSTICO ONI — DETALLE")}
        <table>
          <thead><tr><th>Fecha</th><th style="text-align:right">ONI</th>
            <th>Condición</th></tr></thead>
          <tbody>{oni_rows}</tbody>
        </table>"""

    # Tabla detalle diaria de predicción de embalses (primeros 60 días)
    all_pred_pts = emb.get("prediccion", [])
    pred_table = ""
    if all_pred_pts:
        # Obtener valores ONI/PDO/SOI/GMST del punto de predicción si están disponibles
        pred_rows = ""
        for pt in all_pred_pts[:60]:
            fecha = str(pt.get("fecha", ""))[:10]
            valor = pt.get("valor")
            lower = pt.get("lower")
            upper = pt.get("upper")
            oni_pt = pt.get("oni")
            pdo_pt = pt.get("pdo")
            soi_pt = pt.get("soi")
            gmst_pt = pt.get("gmst")
            pred_rows += (
                f"<tr>"
                f"<td>{fecha}</td>"
                f"<td style='text-align:right;color:#3B82F6'>{f'{valor:.1f}%' if valor is not None else '–'}</td>"
                f"<td style='text-align:right;color:#64748B'>{f'{lower:.1f}' if lower is not None else '–'}</td>"
                f"<td style='text-align:right;color:#64748B'>{f'{upper:.1f}' if upper is not None else '–'}</td>"
                f"<td style='text-align:right;color:#EF4444'>{f'{oni_pt:.2f}' if oni_pt is not None else '–'}</td>"
                f"<td style='text-align:right'>{f'{pdo_pt:.2f}' if pdo_pt is not None else '–'}</td>"
                f"<td style='text-align:right'>{f'{soi_pt:.2f}' if soi_pt is not None else '–'}</td>"
                f"<td style='text-align:right'>{f'{gmst_pt:.2f}' if gmst_pt is not None else '–'}</td>"
                f"</tr>"
            )
        pred_table = f"""
        {_section("DETALLE DIARIO DE PREDICCIÓN — 60 DÍAS")}
        <table>
          <thead><tr>
            <th>Fecha</th>
            <th style="text-align:right">Embalse %</th>
            <th style="text-align:right">IC Inf.</th>
            <th style="text-align:right">IC Sup.</th>
            <th style="text-align:right">ONI</th>
            <th style="text-align:right">PDO</th>
            <th style="text-align:right">SOI</th>
            <th style="text-align:right">GMST</th>
          </tr></thead>
          <tbody>{pred_rows}</tbody>
        </table>"""

    body = kpis + diagnostico_html + m_table
    if emb_chart:
        body += _section("CURVA DE PREDICCIÓN — EMBALSES") + _chart(emb_chart)
    body += pred_table
    if oni_chart:
        body += _section("PRONÓSTICO ONI") + _chart(oni_chart)
    body += oni_table

    return _full_html("Predicciones SIN", body, str(generado)[:19])


async def generate_tablero_pdf(tablero: str, params: dict | None = None) -> bytes:
    """
    Genera PDF para un tablero.
    params: filtros activos pasados desde el frontend (ej. region, anio, contrato).
    """
    params = params or {}
    logger.info("[PDF] Generating for tablero=%s params=%s", tablero, params)

    # Intentar capturas del frontend (best-effort, no bloquea si falla)
    captures: dict[str, str] = {}
    try:
        from domain.services.portal_capture_service import capture_tablero
        captures = await capture_tablero(tablero, dpr=4, params=params)
        if captures:
            logger.info("[PDF] Got captures for %s: %s", tablero, list(captures.keys()))
    except Exception as exc:
        logger.warning("[PDF] Playwright capture failed for %s (%s) — using Plotly only", tablero, exc)

    # Construir HTML con capturas y filtros
    if tablero == "supervision":
        html = await _build_supervision(captures=captures, params=params)
    elif tablero == "presupuesto":
        html = await _build_presupuesto(captures=captures, params=params)
    elif tablero == "contratos-or":
        html = await _build_contratos_or(captures=captures, params=params)
    elif tablero == "fenoge":
        html = await _build_fenoge(captures=captures, params=params)
    elif tablero == "comunidades":
        html = await _build_comunidades(captures=captures, params=params)
    elif tablero == "subsidios":
        html = await _build_subsidios(captures=captures, params=params)
    elif tablero == "colombia-solar":
        html = await _build_colombia_solar(captures=captures, params=params)
    elif tablero == "energia":
        html = await _build_energia(captures=captures, params=params)
    elif tablero == "pagos":
        html = await _build_pagos(params=params, captures=captures)
    elif tablero == "validaciones":
        html = await _build_validaciones(captures=captures, params=params)
    elif tablero == "predicciones":
        html = await _build_predicciones(captures=captures, params=params)
    else:
        logger.warning("[PDF] No builder for tablero=%s", tablero)
        html = _full_html(
            f"Tablero: {tablero.title()}",
            f'<p style="padding:20px;color:var(--gray);">El informe PDF para '
            f'<strong>{tablero}</strong> estará disponible próximamente.</p>',
        )

    pdf = _to_pdf(html)
    logger.info("[PDF] Done: %d bytes for tablero=%s (captures=%s)", len(pdf), tablero, list(captures.keys()))
    return pdf
