"""
Informe Charts Generator
Genera gráficos Plotly (PNG) para adjuntar al Informe Ejecutivo de Telegram.

3 Gráficos:
  1. Pie chart — Participación por fuente de generación
  2. Mapa — Nivel de embalses por región hidrológica
  3. Línea — Evolución del Precio de Bolsa Nacional (90 días)

Cada imagen incluye fecha de datos y referencia al portal.
"""
import logging
import sys
from pathlib import Path
from datetime import date
from typing import Optional, Tuple

# ── Path setup ────────────────────────────────────────────
SERVER_DIR = str(Path(__file__).resolve().parent.parent.parent)
if SERVER_DIR not in sys.path:
    sys.path.append(SERVER_DIR)

import plotly.graph_objects as go
import pandas as pd

logger = logging.getLogger(__name__)

PORTAL_URL = "https://portalenergetico.minenergia.gov.co"
CHARTS_DIR = Path(SERVER_DIR) / "data" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Constantes de estilo ──────────────────────────────────

COLORES_FUENTE = {
    'HIDRAULICA': '#1f77b4',
    'TERMICA': '#ff7f0e',
    'SOLAR': '#ffbb33',
    'EOLICA': '#2ca02c',
    'COGENERADOR': '#17becf',
}

NOMBRES_FUENTE = {
    'HIDRAULICA': 'Hidráulica',
    'TERMICA': 'Térmica',
    'SOLAR': 'Solar',
    'EOLICA': 'Eólica',
    'COGENERADOR': 'Cogeneración',
}

# Mapeo embalse → región hidrológica (Colombia)
EMBALSE_REGION = {
    'PENOL': 'ANTIOQUIA',
    'RIOGRANDE2': 'ANTIOQUIA',
    'PORCE II': 'ANTIOQUIA',
    'PORCE III': 'ANTIOQUIA',
    'MIRAFLORES': 'ANTIOQUIA',
    'PLAYAS': 'ANTIOQUIA',
    'TRONERAS': 'ANTIOQUIA',
    'PUNCHINA': 'ANTIOQUIA',
    'ITUANGO': 'ANTIOQUIA',
    'AGREGADO BOGOTA': 'CENTRO',
    'CHUZA': 'CENTRO',
    'GUAVIO': 'CENTRO',
    'MUNA': 'CENTRO',
    'BETANIA': 'HUILA',
    'EL QUIMBO': 'HUILA',
    'CALIMA1': 'VALLE',
    'ALTOANCHICAYA': 'VALLE',
    'SALVAJINA': 'CAUCA',
    'FLORIDA II': 'CAUCA',
    'URRA1': 'CARIBE',
    'PRADO': 'TOLIMA',
    'AMANI': 'CALDAS',
    'ESMERALDA': 'CALDAS',
    'SAN LORENZO': 'CALDAS',
    'TOPOCORO': 'SANTANDER',
}

REGIONES_COORDENADAS = {
    "ANTIOQUIA": {"lat": 6.949, "lon": -75.244, "nombre": "Antioquia"},
    "CENTRO":    {"lat": 4.976, "lon": -74.283, "nombre": "Centro"},
    "VALLE":     {"lat": 3.792, "lon": -76.324, "nombre": "Valle"},
    "CARIBE":    {"lat": 9.774, "lon": -74.202, "nombre": "Caribe"},
    "CALDAS":    {"lat": 5.253, "lon": -75.464, "nombre": "Caldas"},
    "HUILA":     {"lat": 2.503, "lon": -75.338, "nombre": "Huila"},
    "TOLIMA":    {"lat": 3.961, "lon": -75.144, "nombre": "Tolima"},
    "CAUCA":     {"lat": 2.454, "lon": -76.667, "nombre": "Cauca"},
    "SANTANDER": {"lat": 6.635, "lon": -73.342, "nombre": "Santander"},
}


def _get_db():
    """Obtiene db_manager del proyecto principal."""
    from infrastructure.database.manager import db_manager
    return db_manager


# ═══════════════════════════════════════════════════════════
# 1. PIE CHART — Participación por fuente de generación
# ═══════════════════════════════════════════════════════════

def generate_generation_pie() -> Tuple[Optional[str], str, str]:
    """
    Pie chart de generación por tipo de fuente (último día disponible).
    Returns: (filepath | None, caption, fecha_str)
    """
    try:
        db = _get_db()

        df = db.query_df("""
            SELECT c.tipo, SUM(m.valor_gwh) AS total_gwh
            FROM metrics m
            JOIN catalogos c
              ON c.catalogo = 'ListadoRecursos' AND c.codigo = m.recurso
            WHERE m.metrica = 'Gene'
              AND m.entidad = 'Recurso'
              AND m.fecha = (
                  SELECT MAX(fecha) FROM metrics
                  WHERE metrica = 'Gene' AND entidad = 'Recurso'
              )
            GROUP BY c.tipo
            ORDER BY total_gwh DESC
        """)

        if df.empty:
            logger.warning("generate_generation_pie: sin datos de generación")
            return None, "", ""

        # Fecha del dato
        df_date = db.query_df(
            "SELECT MAX(fecha) AS f FROM metrics "
            "WHERE metrica = 'Gene' AND entidad = 'Recurso'"
        )
        fecha = df_date.iloc[0]['f']
        fecha_str = (
            fecha.strftime('%d/%m/%Y')
            if hasattr(fecha, 'strftime')
            else str(fecha)[:10]
        )

        # Nombres legibles y colores
        df['nombre'] = df['tipo'].map(NOMBRES_FUENTE).fillna(df['tipo'])
        colors = [COLORES_FUENTE.get(t, '#666') for t in df['tipo']]
        total = float(df['total_gwh'].sum())

        fig = go.Figure()
        fig.add_trace(go.Pie(
            labels=df['nombre'],
            values=df['total_gwh'],
            hole=0.35,
            marker=dict(
                colors=colors,
                line=dict(color='white', width=2),
            ),
            textinfo='label+percent',
            textfont_size=14,
            hovertemplate=(
                '<b>%{label}</b><br>'
                '%{value:.1f} GWh (%{percent})<extra></extra>'
            ),
        ))

        fig.update_layout(
            title=dict(
                text=f'⚡ Generación por Fuente — {fecha_str}',
                x=0.5, xanchor='center',
                font=dict(size=22, color='#1e293b', family='Arial'),
            ),
            annotations=[
                dict(
                    text=f'{total:.0f}<br>GWh',
                    x=0.5, y=0.5,
                    font_size=16, showarrow=False,
                    font_color='#334155',
                ),
                dict(
                    text=f'📊 Portal Energético MME  •  {PORTAL_URL}',
                    xref='paper', yref='paper',
                    x=0.5, y=-0.12,
                    showarrow=False,
                    font=dict(size=10, color='#94a3b8'),
                    xanchor='center',
                ),
            ],
            template='plotly_white',
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom', y=-0.18,
                xanchor='center', x=0.5,
                font=dict(size=12),
            ),
            height=500, width=700,
            margin=dict(t=70, b=70, l=30, r=30),
            paper_bgcolor='white',
        )

        filepath = str(CHARTS_DIR / f'gen_pie_{date.today().isoformat()}.png')
        fig.write_image(filepath, width=700, height=500, scale=2)
        logger.info(f"✅ Pie chart generado: {filepath}")

        caption = (
            f"⚡ Participación por fuente — {fecha_str}\n"
            f"Total: {total:.1f} GWh\n\n"
            f"🔗 Más detalle en {PORTAL_URL}"
        )
        return filepath, caption, fecha_str

    except Exception as e:
        logger.error(f"Error generando pie chart de generación: {e}", exc_info=True)
        return None, "", ""


# ═══════════════════════════════════════════════════════════
# 2. MAPA — Nivel de embalses por región hidrológica
# ═══════════════════════════════════════════════════════════

def generate_embalses_map() -> Tuple[Optional[str], str, str]:
    """
    Mapa de Colombia con puntos por región mostrando nivel de embalses.
    Color semáforo: 🟢 ≥60% | 🟡 30-60% | 🔴 <30%
    Returns: (filepath | None, caption, fecha_str)
    """
    try:
        db = _get_db()

        df = db.query_df("""
            SELECT
                v.recurso,
                v.valor_gwh   AS volumen,
                c.valor_gwh   AS capacidad,
                CASE WHEN c.valor_gwh > 0
                     THEN (v.valor_gwh / c.valor_gwh * 100)
                     ELSE 0
                END AS pct
            FROM metrics v
            JOIN metrics c
              ON  v.recurso  = c.recurso
              AND v.fecha    = c.fecha
              AND c.metrica  = 'CapaUtilDiarEner'
              AND c.entidad  = 'Embalse'
            WHERE v.metrica = 'VoluUtilDiarEner'
              AND v.entidad = 'Embalse'
              AND v.fecha = (
                  SELECT MAX(fecha) FROM metrics
                  WHERE metrica = 'VoluUtilDiarEner'
                    AND entidad = 'Embalse'
              )
            ORDER BY volumen DESC
        """)

        if df.empty:
            logger.warning("generate_embalses_map: sin datos de embalses")
            return None, "", ""

        # Fecha
        df_date = db.query_df(
            "SELECT MAX(fecha) AS f FROM metrics "
            "WHERE metrica = 'VoluUtilDiarEner' AND entidad = 'Embalse'"
        )
        fecha = df_date.iloc[0]['f']
        fecha_str = (
            fecha.strftime('%d/%m/%Y')
            if hasattr(fecha, 'strftime')
            else str(fecha)[:10]
        )

        # Asignar región
        df['region'] = df['recurso'].map(EMBALSE_REGION).fillna('OTRO')

        # Agregar por región
        regions = {}
        for region, grp in df.groupby('region'):
            if region == 'OTRO' or region not in REGIONES_COORDENADAS:
                continue
            total_vol = float(grp['volumen'].sum())
            total_cap = float(grp['capacidad'].sum())
            overall_pct = (total_vol / total_cap * 100) if total_cap > 0 else 0
            n = len(grp)

            if overall_pct >= 60:
                color = '#28a745'
            elif overall_pct >= 30:
                color = '#ffc107'
            else:
                color = '#dc3545'

            coord = REGIONES_COORDENADAS[region]
            regions[region] = {
                'nombre': coord['nombre'],
                'lat': coord['lat'],
                'lon': coord['lon'],
                'pct': overall_pct,
                'n': n,
                'color': color,
                'vol': total_vol,
                'cap': total_cap,
            }

        if not regions:
            return None, "", ""

        # Crear mapa
        fig = go.Figure()

        for _key, data in regions.items():
            dot_size = min(15 + data['n'] * 5, 45)

            fig.add_trace(go.Scattergeo(
                lon=[data['lon']],
                lat=[data['lat']],
                text=[f"{data['nombre']}<br>{data['pct']:.0f}%"],
                mode='markers+text',
                marker=dict(
                    size=dot_size,
                    color=data['color'],
                    line=dict(width=2, color='white'),
                    symbol='circle',
                    opacity=0.85,
                ),
                textposition='top center',
                textfont=dict(
                    size=11, color='#2c3e50', family='Arial Black',
                ),
                name=f"{data['nombre']} ({data['pct']:.0f}%)",
                hovertext=(
                    f"<b>{data['nombre']}</b><br>"
                    f"Nivel: {data['pct']:.1f}%<br>"
                    f"Embalses: {data['n']}<br>"
                    f"Volumen: {data['vol']:.0f} GWh"
                ),
                hoverinfo='text',
                showlegend=True,
            ))

        fig.update_geos(
            center=dict(lon=-74, lat=4.5),
            projection_type='mercator',
            showcountries=True, countrycolor='lightgray',
            showcoastlines=True, coastlinecolor='gray',
            showland=True, landcolor='#f0f4f8',
            showlakes=True, lakecolor='#dbeafe',
            showrivers=True, rivercolor='#93c5fd',
            lonaxis_range=[-80, -66],
            lataxis_range=[-5, 13],
            bgcolor='#e8f4f8',
        )

        fig.update_layout(
            title=dict(
                text=f'🗺️ Nivel de Embalses por Región — {fecha_str}',
                x=0.5, xanchor='center',
                font=dict(size=20, color='#1e293b'),
            ),
            annotations=[
                dict(
                    text=f'🟢 ≥60%  |  🟡 30-60%  |  🔴 <30%   •   {PORTAL_URL}',
                    xref='paper', yref='paper',
                    x=0.5, y=-0.02,
                    showarrow=False,
                    font=dict(size=10, color='#64748b'),
                    xanchor='center',
                ),
            ],
            height=650, width=700,
            margin=dict(l=0, r=0, t=60, b=30),
            legend=dict(
                title='Regiones',
                orientation='v',
                bgcolor='rgba(255,255,255,0.9)',
                bordercolor='lightgray', borderwidth=1,
                font=dict(size=10),
            ),
            paper_bgcolor='white',
        )

        global_pct = (
            (df['volumen'].sum() / df['capacidad'].sum() * 100)
            if df['capacidad'].sum() > 0 else 0
        )

        filepath = str(CHARTS_DIR / f'embalses_map_{date.today().isoformat()}.png')
        fig.write_image(filepath, width=700, height=650, scale=2)
        logger.info(f"✅ Mapa de embalses generado: {filepath}")

        caption = (
            f"🗺️ Nivel de embalses por región — {fecha_str}\n"
            f"Promedio nacional: {global_pct:.1f}%\n\n"
            f"🔗 Más detalle en {PORTAL_URL}"
        )
        return filepath, caption, fecha_str

    except Exception as e:
        logger.error(f"Error generando mapa de embalses: {e}", exc_info=True)
        return None, "", ""


# ═══════════════════════════════════════════════════════════
# 3. LÍNEA — Evolución de Precio de Bolsa Nacional (90 días)
# ═══════════════════════════════════════════════════════════

def generate_price_chart() -> Tuple[Optional[str], str, str]:
    """
    Gráfico de línea con la evolución del precio de bolsa (últimos 90 días).
    Returns: (filepath | None, caption, fecha_str)
    """
    try:
        db = _get_db()

        df = db.query_df("""
            SELECT fecha, valor_gwh AS precio
            FROM metrics
            WHERE metrica = 'PrecBolsNaci'
              AND entidad  = 'Sistema'
              AND fecha >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY fecha ASC
        """)

        if df.empty:
            logger.warning("generate_price_chart: sin datos de precio")
            return None, "", ""

        df['fecha'] = pd.to_datetime(df['fecha'])
        ultimo_precio = float(df.iloc[-1]['precio'])
        fecha_ultima = df.iloc[-1]['fecha']
        fecha_str = fecha_ultima.strftime('%d/%m/%Y')
        promedio = float(df['precio'].mean())

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df['fecha'],
            y=df['precio'],
            mode='lines+markers',
            name='Precio Bolsa Nacional',
            line=dict(width=2.5, color='#FFB800'),
            marker=dict(size=4, color='#FFB800'),
            fill='tozeroy',
            fillcolor='rgba(255, 184, 0, 0.1)',
        ))

        # Línea de promedio
        fig.add_hline(
            y=promedio,
            line_dash='dash', line_color='#94a3b8', line_width=1,
            annotation_text=f'Promedio: ${promedio:,.0f}',
            annotation_position='top right',
            annotation_font_size=11,
            annotation_font_color='#64748b',
        )

        fig.update_layout(
            title=dict(
                text='💰 Evolución Precio de Bolsa — Últimos 90 días',
                x=0.5, xanchor='center',
                font=dict(size=20, color='#1e293b', family='Arial'),
            ),
            xaxis_title='Fecha',
            yaxis_title='$/kWh',
            annotations=[
                dict(
                    text=f'📊 Portal Energético MME  •  {PORTAL_URL}',
                    xref='paper', yref='paper',
                    x=0.5, y=-0.18,
                    showarrow=False,
                    font=dict(size=10, color='#94a3b8'),
                    xanchor='center',
                ),
            ],
            template='plotly_white',
            hovermode='x unified',
            height=450, width=800,
            margin=dict(l=70, r=30, t=70, b=70),
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(showgrid=True, gridcolor='#f1f5f9'),
            yaxis=dict(showgrid=True, gridcolor='#f1f5f9'),
        )

        filepath = str(CHARTS_DIR / f'precio_evol_{date.today().isoformat()}.png')
        fig.write_image(filepath, width=800, height=450, scale=2)
        logger.info(f"✅ Price chart generado: {filepath}")

        caption = (
            f"💰 Precio de Bolsa Nacional — {fecha_str}\n"
            f"Último: ${ultimo_precio:,.1f} $/kWh  |  "
            f"Promedio 90d: ${promedio:,.1f}\n\n"
            f"🔗 Más detalle en {PORTAL_URL}"
        )
        return filepath, caption, fecha_str

    except Exception as e:
        logger.error(f"Error generando gráfico de precios: {e}", exc_info=True)
        return None, "", ""


# ═══════════════════════════════════════════════════════════
# Generador combinado
# ═══════════════════════════════════════════════════════════

def generate_all_informe_charts() -> dict:
    """
    Genera los 3 gráficos del informe ejecutivo.

    Returns
    -------
    dict  con claves 'generacion', 'embalses', 'precios'.
    Cada valor es (filepath | None, caption, fecha_str).
    """
    results = {}
    for key, fn in [
        ('generacion', generate_generation_pie),
        ('embalses', generate_embalses_map),
        ('precios', generate_price_chart),
    ]:
        try:
            results[key] = fn()
        except Exception as e:
            logger.error(f"Error en chart '{key}': {e}")
            results[key] = (None, '', '')
    return results
