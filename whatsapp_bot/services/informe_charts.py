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
URL_GENERACION = f"{PORTAL_URL}/generacion/fuentes"
URL_EMBALSES = f"{PORTAL_URL}/generacion/hidraulica/hidrologia"
URL_PRECIOS = f"{PORTAL_URL}/comercializacion"
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
                    text=f'📊 Portal Energético MME  •  {URL_GENERACION}',
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
            f"🔗 Más detalle en {URL_GENERACION}"
        )
        return filepath, caption, fecha_str

    except Exception as e:
        logger.error(f"Error generando pie chart de generación: {e}", exc_info=True)
        return None, "", ""


# ═══════════════════════════════════════════════════════════
# 2. MAPA — Nivel de embalses por región hidrológica
# ═══════════════════════════════════════════════════════════

def _clasificar_riesgo_embalse(participacion: float, volumen_pct: float) -> str:
    """
    Replica la lógica exacta del semáforo del dashboard
    (generacion_hidraulica_hidrologia.py → clasificar_riesgo_embalse).

    Matriz 2D: participación (importancia estratégica) × volumen útil (%).

    Returns: '🔴' | '🟡' | '🟢'
    """
    if participacion >= 15:
        if volumen_pct < 30:
            return '🔴'
        elif volumen_pct < 70:
            return '🟡'
        else:
            return '🟢'
    elif participacion >= 10:
        if volumen_pct < 20:
            return '🔴'
        elif volumen_pct < 60:
            return '🟡'
        else:
            return '🟢'
    elif participacion >= 5:
        if volumen_pct < 15:
            return '🔴'
        elif volumen_pct < 50:
            return '🟡'
        else:
            return '🟢'
    else:  # participación < 5%
        if volumen_pct < 25:
            return '🟡'
        else:
            return '🟢'


_RIESGO_COLOR = {'🔴': '#dc3545', '🟡': '#ffc107', '🟢': '#28a745'}
_RIESGO_ORDEN = {'🔴': 3, '🟡': 2, '🟢': 1}
_RIESGO_LABEL = {'🔴': 'Alto', '🟡': 'Medio', '🟢': 'Bajo'}


def generate_embalses_map() -> Tuple[Optional[str], str, str]:
    """
    Mapa de Colombia con puntos por región mostrando nivel de embalses.

    Semáforo = misma lógica del dashboard (matriz participación × volumen).
    Color de región = peor riesgo entre sus embalses (conservador).

    Returns: (filepath | None, caption, fecha_str)
    """
    try:
        db = _get_db()

        # Buscar la fecha más reciente con datos COMPLETOS (n_vol/n_cap >= 80%)
        df_fecha = db.query_df("""
            SELECT fecha,
                   COUNT(DISTINCT CASE WHEN metrica='VoluUtilDiarEner' THEN recurso END) as n_vol,
                   COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END) as n_cap
            FROM metrics
            WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner')
              AND entidad = 'Embalse'
              AND fecha >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY fecha
            HAVING COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END) > 0
               AND COUNT(DISTINCT CASE WHEN metrica='VoluUtilDiarEner' THEN recurso END)::float
                 / COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END) >= 0.80
            ORDER BY fecha DESC
            LIMIT 1
        """)

        if df_fecha.empty:
            logger.warning("generate_embalses_map: no hay fecha con datos completos en últimos 7 días")
            return None, "", ""

        fecha_completa = df_fecha.iloc[0]['fecha']

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
              AND v.fecha = %s
            ORDER BY volumen DESC
        """, (fecha_completa,))

        if df.empty:
            logger.warning("generate_embalses_map: sin datos de embalses")
            return None, "", ""

        # Fecha
        fecha = fecha_completa
        fecha_str = (
            fecha.strftime('%d/%m/%Y')
            if hasattr(fecha, 'strftime')
            else str(fecha)[:10]
        )

        # Participación nacional por embalse (capacidad / total nacional)
        cap_total_nacional = float(df['capacidad'].sum())
        df['participacion'] = (df['capacidad'] / cap_total_nacional * 100) if cap_total_nacional > 0 else 0

        # Clasificar riesgo por embalse (lógica dashboard)
        df['riesgo'] = df.apply(
            lambda r: _clasificar_riesgo_embalse(r['participacion'], r['pct']),
            axis=1
        )

        # Asignar región
        df['region'] = df['recurso'].map(EMBALSE_REGION).fillna('OTRO')

        # Agregar por región — color = peor riesgo de la región
        regions = {}
        for region, grp in df.groupby('region'):
            if region == 'OTRO' or region not in REGIONES_COORDENADAS:
                continue
            total_vol = float(grp['volumen'].sum())
            total_cap = float(grp['capacidad'].sum())
            overall_pct = (total_vol / total_cap * 100) if total_cap > 0 else 0
            n = len(grp)

            # Riesgo máximo entre embalses de la región (como el dashboard)
            riesgo_max = max(grp['riesgo'], key=lambda r: _RIESGO_ORDEN[r])
            color = _RIESGO_COLOR[riesgo_max]

            coord = REGIONES_COORDENADAS[region]
            regions[region] = {
                'nombre': coord['nombre'],
                'lat': coord['lat'],
                'lon': coord['lon'],
                'pct': overall_pct,
                'n': n,
                'color': color,
                'riesgo': riesgo_max,
                'riesgo_label': _RIESGO_LABEL[riesgo_max],
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
                name=f"{data['riesgo']} {data['nombre']} ({data['pct']:.0f}%) — Riesgo {data['riesgo_label']}",
                hovertext=(
                    f"<b>{data['nombre']}</b><br>"
                    f"Nivel: {data['pct']:.1f}%<br>"
                    f"Riesgo: {data['riesgo']} {data['riesgo_label']}<br>"
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
                    text=(
                        '🔴 Alto  |  🟡 Medio  |  🟢 Bajo'
                        '  (participación × volumen)   •   '
                        f'{URL_EMBALSES}'
                    ),
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
            f"🔗 Más detalle en {URL_EMBALSES}"
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
                    text=f'📊 Portal Energético MME  •  {URL_PRECIOS}',
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
            f"🔗 Más detalle en {URL_PRECIOS}"
        )
        return filepath, caption, fecha_str

    except Exception as e:
        logger.error(f"Error generando gráfico de precios: {e}", exc_info=True)
        return None, "", ""


# ═══════════════════════════════════════════════════════════
# Nuevas funciones para diseño XM (usando matplotlib)
# ═══════════════════════════════════════════════════════════

# Importaciones para las nuevas funciones
import matplotlib
matplotlib.use('Agg')  # Backend no-interactivo
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def generate_demand_chart() -> Tuple[Optional[str], str, str]:
    """
    Gráfico de líneas con evolución de la demanda (últimos 30 días).
    Muestra 3 líneas: Demanda Real, Regulada y No Regulada.
    
    Returns
    -------
    (filepath, caption, fecha_str)
    """
    try:
        from infrastructure.database.connection import get_connection
        
        with get_connection() as conn:
            # Usar MAX por día (valor máximo horario) y filtrar días incompletos
            df = pd.read_sql("""
                WITH daily_max AS (
                    SELECT 
                        fecha,
                        MAX(CASE WHEN metrica = 'DemaReal' THEN valor_gwh END) as demanda_real,
                        MAX(CASE WHEN metrica = 'DemaRealReg' THEN valor_gwh END) as demanda_reg,
                        MAX(CASE WHEN metrica = 'DemaRealNoReg' THEN valor_gwh END) as demanda_no_reg
                    FROM metrics 
                    WHERE metrica IN ('DemaReal', 'DemaRealReg', 'DemaRealNoReg')
                      AND fecha >= CURRENT_DATE - INTERVAL '45 days'
                    GROUP BY fecha
                ),
                -- Calcular promedio de los últimos 10 días para detectar incompletos
                stats AS (
                    SELECT AVG(demanda_real) as avg_real
                    FROM daily_max
                    WHERE fecha >= CURRENT_DATE - INTERVAL '15 days'
                      AND fecha < CURRENT_DATE - INTERVAL '2 days'
                )
                SELECT d.*
                FROM daily_max d, stats s
                WHERE d.demanda_real >= s.avg_real * 0.4  -- Filtrar días con < 40% del promedio
                  AND d.demanda_real IS NOT NULL
                ORDER BY d.fecha
                LIMIT 30
            """, conn)
        
        if df.empty or len(df) < 5:
            logger.warning("generate_demand_chart: sin datos suficientes de demanda")
            return None, "", ""
        
        ultima_fecha = df['fecha'].max()
        logger.info(f"[CHARTS] Demanda: {len(df)} días, último completo: {ultima_fecha}")
        
        fig, ax = plt.subplots(figsize=(8, 4.5))
        
        # 3 líneas horizontales como en el modelo XM
        ax.plot(df['fecha'], df['demanda_real'], 
                color='#2c3e50', linewidth=2.5, label='Demanda Real', marker='o', markersize=3)
        ax.plot(df['fecha'], df['demanda_reg'], 
                color='#16a085', linewidth=2, label='Demanda Regulada', marker='s', markersize=3)
        ax.plot(df['fecha'], df['demanda_no_reg'], 
                color='#52c4b0', linewidth=2, label='Demanda No Regulada', marker='^', markersize=3)
        
        ax.set_ylabel('GWh', fontsize=9, color='#666')
        ax.set_xlabel('Fecha', fontsize=9, color='#666')
        
        # Formato eje X
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        plt.xticks(rotation=45, ha='right', fontsize=7)
        
        # Leyenda arriba
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), 
                  ncol=3, frameon=False, fontsize=8)
        
        ax.grid(True, alpha=0.3, linestyle='-')
        ax.set_axisbelow(True)
        
        # Límites
        ax.set_ylim(bottom=0)
        
        # Formato spines
        for spine in ['top', 'right']:
            ax.spines[spine].set_visible(False)
        
        plt.tight_layout()
        
        filepath = str(CHARTS_DIR / f'demanda_evol_{date.today().isoformat()}.png')
        fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        caption = f"Evolución Demanda — Últimos 30 días"
        fecha_str = ultima_fecha.strftime('%Y-%m-%d') if hasattr(ultima_fecha, 'strftime') else str(ultima_fecha)
        
        logger.info(f"[CHARTS] Demanda chart guardado: {filepath}")
        return filepath, caption, fecha_str
        
    except Exception as e:
        logger.error(f"Error generando gráfico de demanda: {e}", exc_info=True)
        return None, "", ""


def generate_price_multi_chart() -> Tuple[Optional[str], str, str]:
    """
    Gráfico de líneas con 3 precios: Escasez, Máximo Oferta, PPP.
    Réplica del modelo XM.
    
    Returns
    -------
    (filepath, caption, fecha_str)
    """
    try:
        from infrastructure.database.connection import get_connection
        
        with get_connection() as conn:
            # Query para obtener los 3 precios (últimos 30 días completos)
            df = pd.read_sql("""
                WITH daily_prices AS (
                    SELECT 
                        fecha,
                        MAX(CASE WHEN metrica = 'PrecEsca' THEN valor_gwh END) as precio_escasez,
                        MAX(CASE WHEN metrica = 'MaxPrecOferNal' THEN valor_gwh END) as precio_max,
                        MAX(CASE WHEN metrica = 'PPPrecBolsNaci' THEN valor_gwh END) as ppp_bolsa,
                        MAX(CASE WHEN metrica = 'PrecBolsNaci' THEN valor_gwh END) as precio_bolsa
                    FROM metrics 
                    WHERE metrica IN ('PrecEsca', 'MaxPrecOferNal', 'PPPrecBolsNaci', 'PrecBolsNaci')
                      AND fecha >= CURRENT_DATE - INTERVAL '45 days'
                    GROUP BY fecha
                    HAVING COUNT(DISTINCT metrica) >= 2  -- Al menos 2 métricas por día
                )
                SELECT * FROM daily_prices
                ORDER BY fecha
                LIMIT 30
            """, conn)
        
        if df.empty or len(df) < 5:
            logger.warning("generate_price_multi_chart: sin datos suficientes de precios")
            return None, "", ""
        
        ultima_fecha = df['fecha'].max()
        logger.info(f"[CHARTS] Precios multi: {len(df)} días, último: {ultima_fecha}")
        
        fig, ax = plt.subplots(figsize=(8, 4.5))
        
        # 3 líneas: Escasez (naranja), Máximo (azul), PPP (verde)
        if df['precio_escasez'].notna().any():
            ax.plot(df['fecha'], df['precio_escasez'], 
                    color='#e67e22', linewidth=2.5, label='Precio de escasez ($/kWh)', marker='o', markersize=3)
        
        if df['precio_max'].notna().any():
            ax.plot(df['fecha'], df['precio_max'], 
                    color='#3498db', linewidth=2, label='Precio Máximo Diario ($/kWh)', marker='s', markersize=3)
        
        if df['ppp_bolsa'].notna().any():
            ax.plot(df['fecha'], df['ppp_bolsa'], 
                    color='#27ae60', linewidth=2, label='PPP Diario ($/kWh)', marker='^', markersize=3)
        elif df['precio_bolsa'].notna().any():
            # Fallback a PrecBolsNaci si no hay PPP
            ax.plot(df['fecha'], df['precio_bolsa'], 
                    color='#27ae60', linewidth=2, label='Precio Promedio Diario ($/kWh)', marker='^', markersize=3)
        
        ax.set_ylabel('COP/kWh', fontsize=9, color='#666')
        ax.set_xlabel('Fecha', fontsize=9, color='#666')
        
        # Formato eje X
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        plt.xticks(rotation=45, ha='right', fontsize=7)
        
        # Leyenda arriba como en el modelo XM
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.18), 
                  ncol=3, frameon=False, fontsize=8)
        
        ax.grid(True, alpha=0.3, linestyle='-')
        ax.set_axisbelow(True)
        
        # Formato spines
        for spine in ['top', 'right']:
            ax.spines[spine].set_visible(False)
        
        plt.tight_layout()
        
        filepath = str(CHARTS_DIR / f'precio_multi_{date.today().isoformat()}.png')
        fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        caption = f"Evolución Precios — Últimos 30 días"
        fecha_str = ultima_fecha.strftime('%Y-%m-%d') if hasattr(ultima_fecha, 'strftime') else str(ultima_fecha)
        
        logger.info(f"[CHARTS] Precio multi chart guardado: {filepath}")
        return filepath, caption, fecha_str
        
    except Exception as e:
        logger.error(f"Error generando gráfico multi-precio: {e}", exc_info=True)
        return None, "", ""


# ═══════════════════════════════════════════════════════════
# 6. APORTES HÍDRICOS — Volumen Útil con referencias históricas
# ═══════════════════════════════════════════════════════════

def generate_aportes_hidricos_chart() -> Tuple[Optional[str], str, str]:
    """
    Gráfico de líneas con evolución del volumen útil de embalses (últimos 90 días).
    Muestra 3 líneas: 
      - Volumen Útil diario (2026 - actual)
      - Referencia (2025) - mismas fechas año anterior
      - Referencia (2024) - dos años atrás
    
    Replica el estilo XM con 3 tonos de verde.
    
    Returns
    -------
    (filepath, caption, fecha_str)
    """
    try:
        from infrastructure.database.connection import get_connection
        
        with get_connection() as conn:
            # Consulta para obtener las 3 líneas de volumen útil
            df = pd.read_sql("""
                WITH fechas_actuales AS (
                    SELECT DISTINCT fecha
                    FROM metrics
                    WHERE metrica = 'PorcVoluUtilDiar'
                      AND fecha >= CURRENT_DATE - INTERVAL '90 days'
                      AND fecha <= CURRENT_DATE
                ),
                actual_2026 AS (
                    SELECT fecha, AVG(valor_gwh) * 100 as porcentaje
                    FROM metrics
                    WHERE metrica = 'PorcVoluUtilDiar'
                      AND fecha >= CURRENT_DATE - INTERVAL '90 days'
                    GROUP BY fecha
                ),
                referencia_2025 AS (
                    SELECT 
                        f.fecha,
                        AVG(m.valor_gwh) * 100 as porcentaje
                    FROM fechas_actuales f
                    JOIN metrics m ON m.fecha = f.fecha - INTERVAL '1 year'
                      AND m.metrica = 'PorcVoluUtilDiar'
                    GROUP BY f.fecha
                ),
                referencia_2024 AS (
                    SELECT 
                        f.fecha,
                        AVG(m.valor_gwh) * 100 as porcentaje
                    FROM fechas_actuales f
                    JOIN metrics m ON m.fecha = f.fecha - INTERVAL '2 years'
                      AND m.metrica = 'PorcVoluUtilDiar'
                    GROUP BY f.fecha
                )
                SELECT 
                    a.fecha,
                    a.porcentaje as volumen_util_2026,
                    r25.porcentaje as ref_2025,
                    r24.porcentaje as ref_2024
                FROM actual_2026 a
                LEFT JOIN referencia_2025 r25 ON r25.fecha = a.fecha
                LEFT JOIN referencia_2024 r24 ON r24.fecha = a.fecha
                ORDER BY a.fecha
            """, conn)
            
            if df.empty:
                logger.warning("[CHARTS] Sin datos de volumen útil")
                return None, "", ""
            
            df['fecha'] = pd.to_datetime(df['fecha'])
            ultima_fecha = df['fecha'].max()
            fecha_str = ultima_fecha.strftime('%d/%m/%Y')
            
            # Datos actuales para el resumen
            ultimo_valor = df.iloc[-1]['volumen_util_2026']
            ref_2025_val = df.iloc[-1]['ref_2025'] if pd.notna(df.iloc[-1]['ref_2025']) else None
            ref_2024_val = df.iloc[-1]['ref_2024'] if pd.notna(df.iloc[-1]['ref_2024']) else None
            
            # Crear figura matplotlib estilo XM
            fig, ax = plt.subplots(figsize=(10, 5.5))
            
            # Colores distintivos: Actual (verde claro), 2025 (verde), 2024 (azul vibrante)
            color_actual = '#90EE90'      # Verde muy claro
            color_2025 = '#2E8B57'        # Verde medio
            color_2024 = '#2196F3'        # Azul vibrante (más distinguible)
            
            # Trazar las 3 líneas
            ax.plot(df['fecha'], df['volumen_util_2026'], 
                   label='Volumen Útil diario', 
                   color=color_actual, linewidth=2, alpha=0.9)
            
            if df['ref_2025'].notna().any():
                ax.plot(df['fecha'], df['ref_2025'], 
                       label='Referencia (2025)', 
                       color=color_2025, linewidth=2, linestyle='-')
            
            if df['ref_2024'].notna().any():
                ax.plot(df['fecha'], df['ref_2024'], 
                       label='Referencia (2024)', 
                       color=color_2024, linewidth=2, linestyle='-')
            
            # Líneas de referencia horizontales
            ax.axhline(y=80, color='#ddd', linestyle='--', linewidth=0.8, alpha=0.7)
            ax.axhline(y=60, color='#ddd', linestyle='--', linewidth=0.8, alpha=0.7)
            ax.axhline(y=40, color='#ddd', linestyle='--', linewidth=0.8, alpha=0.7)
            ax.axhline(y=20, color='#ddd', linestyle='--', linewidth=0.8, alpha=0.7)
            
            # Configuración de ejes
            ax.set_ylim(0, 100)
            ax.set_ylabel('Porcentaje (%)', fontsize=10, color='#666')
            ax.set_xlabel('')
            
            # Formato eje X
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=10))
            plt.xticks(rotation=45, ha='right', fontsize=8)
            
            # Leyenda arriba
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), 
                     ncol=3, frameon=False, fontsize=9)
            
            # Grid sutil
            ax.grid(True, alpha=0.3, linestyle='-', axis='y')
            ax.set_axisbelow(True)
            
            # Formato spines
            for spine in ['top', 'right']:
                ax.spines[spine].set_visible(False)
            
            plt.tight_layout()
            
            filepath = str(CHARTS_DIR / f'aportes_hidricos_{date.today().isoformat()}.png')
            fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            
            caption = f"Evolución Volumen Útil — Comparativo histórico"
            
            logger.info(f"[CHARTS] Aportes hídricos chart guardado: {filepath}")
            return filepath, caption, fecha_str
            
    except Exception as e:
        logger.error(f"Error generando gráfico de aportes hídricos: {e}", exc_info=True)
        return None, "", ""


# ═══════════════════════════════════════════════════════════
# Generador combinado
# ═══════════════════════════════════════════════════════════

def generate_all_informe_charts() -> dict:
    """
    Genera todos los gráficos del informe ejecutivo.

    Returns
    -------
    dict  con claves 'generacion', 'embalses', 'precios', 'demanda', 'precio_multi', 'aportes_hidricos'.
    Cada valor es (filepath | None, caption, fecha_str).
    """
    results = {}
    for key, fn in [
        ('generacion', generate_generation_pie),
        ('embalses', generate_embalses_map),
        ('precios', generate_price_chart),
        ('demanda', generate_demand_chart),
        ('precio_multi', generate_price_multi_chart),
        ('aportes_hidricos', generate_aportes_hidricos_chart),
    ]:
        try:
            results[key] = fn()
        except Exception as e:
            logger.error(f"Error en chart '{key}': {e}")
            results[key] = (None, '', '')
    return results
