"""
Componente KPI Card compacto estilo Tabler/Power BI.

Uso:
    from interface.components.kpi_card import crear_kpi, crear_kpi_row

    # KPI individual
    kpi = crear_kpi("Reservas Hídricas", "62.45", "%", "fas fa-water", "blue")

    # Fila de KPIs (auto-responsive)
    row = crear_kpi_row([
        {"titulo": "Reservas", "valor": "62.45", "unidad": "%", "icono": "fas fa-water", "color": "green"},
        {"titulo": "Aportes",  "valor": "98.12", "unidad": "%", "icono": "fas fa-tint",  "color": "blue"},
        {"titulo": "Generación", "valor": "215.8", "unidad": "GWh", "icono": "fas fa-bolt", "color": "orange"},
    ])

Colores disponibles: blue, green, orange, red, purple, cyan
"""
from dash import html


def crear_kpi(
    titulo: str,
    valor: str,
    unidad: str = "",
    icono: str = "fas fa-chart-line",
    color: str = "blue",
    variacion: str | None = None,
    variacion_dir: str = "flat",  # "up", "down", "flat"
    subtexto: str | None = None,
    sparkline_id: str | None = None,
):
    """
    Crea un KPI card compacto estilo Tabler.

    Args:
        titulo: Label superior (ej: "Reservas Hídricas")
        valor: Número principal como string (ej: "62.45")
        unidad: Unidad después del número (ej: "%", "GWh", "COP/kWh")
        icono: Clase FontAwesome (ej: "fas fa-water")
        color: blue | green | orange | red | purple | cyan
        variacion: Texto de variación (ej: "+2.3%", "-1.5%")
        variacion_dir: Dirección "up" | "down" | "flat"
        subtexto: Texto pequeño debajo (ej: "Datos del 18 feb")
        sparkline_id: ID para slot de sparkline (dcc.Graph externo)

    Returns:
        html.Div con clase .t-kpi
    """
    # Icono dentro del recuadro coloreado
    icon_box = html.Div(
        html.I(className=icono),
        className=f"t-kpi-icon {color}",
    )

    # Línea de valor + unidad + variación
    value_children = [
        html.Span(valor, className="t-kpi-value"),
    ]
    if unidad:
        value_children.append(html.Span(unidad, className="t-kpi-unit"))
    if variacion:
        arrow = "▲" if variacion_dir == "up" else ("▼" if variacion_dir == "down" else "—")
        value_children.append(
            html.Span(
                f"{arrow} {variacion}",
                className=f"t-kpi-variation {variacion_dir}",
            )
        )

    # Body: label + valor + subtexto
    body_children = [
        html.Div(titulo, className="t-kpi-label"),
        html.Div(value_children),
    ]
    if subtexto:
        body_children.append(html.Div(subtexto, className="t-kpi-footer"))

    body = html.Div(body_children, className="t-kpi-body")

    # Ensamblar
    kpi_children = [icon_box, body]

    # Slot para sparkline
    if sparkline_id:
        kpi_children.append(
            html.Div(id=sparkline_id, className="t-kpi-sparkline")
        )

    return html.Div(kpi_children, className="t-kpi t-fade-in")


def crear_kpi_row(kpis: list[dict], columnas: int | None = None):
    """
    Crea una fila responsive de KPIs.

    Args:
        kpis: Lista de dicts con keys: titulo, valor, unidad, icono, color,
              y opcionalmente: variacion, variacion_dir, subtexto, sparkline_id
        columnas: Forzar número de columnas (2-6). 
                  None = auto según cantidad de KPIs.

    Returns:
        html.Div con CSS grid
    """
    if columnas is None:
        n = len(kpis)
        if n <= 2:
            columnas = 2
        elif n <= 4:
            columnas = n
        elif n <= 6:
            columnas = n
        else:
            columnas = 4  # Wrap after 4

    grid_class = f"t-grid t-grid-{min(columnas, 6)} t-mb-4"

    cards = [crear_kpi(**kpi) for kpi in kpis]

    return html.Div(cards, className=grid_class)
