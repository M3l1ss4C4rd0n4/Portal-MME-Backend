"""
Componente Chart Card y Table Card estilo Tabler/Power BI.

Uso:
    from interface.components.chart_card import crear_chart_card, crear_table_card, crear_page_header

    # Chart card con dcc.Graph dentro
    card = crear_chart_card(
        titulo="Generación por Fuente",
        graph_id="graph-gen-fuente",
        height=280,
        subtitulo="Últimos 30 días"
    )

    # Table card wrapper para dash_table.DataTable
    table = crear_table_card(
        titulo="Detalle Horario",
        table_component=my_datatable,
    )

    # Page header
    header = crear_page_header(
        titulo="Transmisión",
        icono="fas fa-bolt",
        breadcrumb="Inicio / Transmisión",
        fecha="18 de febrero de 2026"
    )
"""
from dash import html, dcc


def crear_chart_card(
    titulo: str,
    graph_id: str,
    height: int = 280,
    subtitulo: str | None = None,
    extra_header: object = None,
    loading: bool = True,
    className: str = "",
):
    """
    Wrapper para dcc.Graph con estilo Tabler.

    Args:
        titulo: Título del chart card
        graph_id: ID para el dcc.Graph
        height: Altura del gráfico en px
        subtitulo: Texto secundario en el header
        extra_header: Componente adicional (ej: dropdown de filtro) a la derecha del header
        loading: Envolver en dcc.Loading
        className: Clases CSS adicionales

    Returns:
        html.Div con clase .t-chart-card
    """
    # Header
    header_left = [html.H3(titulo, className="t-chart-title")]
    if subtitulo:
        header_left.append(html.P(subtitulo, className="t-chart-subtitle"))

    header_children = [html.Div(header_left)]
    if extra_header:
        header_children.append(extra_header)

    header = html.Div(header_children, className="t-chart-header")

    # Body con dcc.Graph
    graph = dcc.Graph(
        id=graph_id,
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
        style={"height": f"{height}px"},
    )

    if loading:
        body_content = dcc.Loading(graph, type="dot", color="#3b82f6")
    else:
        body_content = graph

    body = html.Div(body_content, className="t-chart-body")

    cls = f"t-chart-card t-fade-in {className}".strip()
    return html.Div([header, body], className=cls)


def crear_chart_card_custom(
    titulo: str,
    children,
    subtitulo: str | None = None,
    extra_header: object = None,
    className: str = "",
):
    """
    Chart card con contenido arbitrario (no dcc.Graph).

    Args:
        titulo: Título del card
        children: Contenido libre del body
        subtitulo: Texto secundario
        extra_header: Componente a la derecha del header
        className: Clases CSS adicionales

    Returns:
        html.Div con clase .t-chart-card
    """
    header_left = [html.H3(titulo, className="t-chart-title")]
    if subtitulo:
        header_left.append(html.P(subtitulo, className="t-chart-subtitle"))

    header_children = [html.Div(header_left)]
    if extra_header:
        header_children.append(extra_header)

    header = html.Div(header_children, className="t-chart-header")
    body = html.Div(children, className="t-chart-body")

    cls = f"t-chart-card t-fade-in {className}".strip()
    return html.Div([header, body], className=cls)


def crear_table_card(
    titulo: str,
    table_component,
    subtitulo: str | None = None,
    extra_header: object = None,
    className: str = "",
):
    """
    Wrapper para DataTable con estilo Tabler.

    Args:
        titulo: Título de la tabla
        table_component: dash_table.DataTable u otro componente tabla
        subtitulo: Texto secundario
        extra_header: Componente a la derecha del header
        className: Clases CSS adicionales

    Returns:
        html.Div con clase .t-table-card
    """
    header_left = [html.H3(titulo, className="t-chart-title")]
    if subtitulo:
        header_left.append(html.P(subtitulo, className="t-chart-subtitle"))

    header_children = [html.Div(header_left)]
    if extra_header:
        header_children.append(extra_header)

    header = html.Div(header_children, className="t-chart-header")
    body = html.Div(table_component, className="t-chart-body")

    cls = f"t-table-card t-fade-in {className}".strip()
    return html.Div([header, body], className=cls)


def crear_page_header(
    titulo: str,
    icono: str = "fas fa-chart-bar",
    breadcrumb: str | None = None,
    fecha: str | None = None,
):
    """
    Header de página estilo Tabler.

    Args:
        titulo: Nombre de la página
        icono: Clase FontAwesome
        breadcrumb: Texto de breadcrumb (ej: "Inicio / Transmisión")
        fecha: Fecha de actualización

    Returns:
        html.Div con clase .t-page-header
    """
    left = [
        html.H1([html.I(className=f"{icono} me-2"), titulo]),
    ]
    if breadcrumb:
        left.append(html.Div(breadcrumb, className="t-breadcrumb"))

    right_children = []
    if fecha:
        right_children.append(
            html.Span(
                [html.I(className="fas fa-calendar-alt me-1"), fecha],
                className="t-badge-date",
            )
        )

    return html.Div(
        [html.Div(left), html.Div(right_children)],
        className="t-page-header",
    )


def crear_filter_bar(*children):
    """
    Barra de filtros horizontal compacta.

    Args:
        *children: Componentes de filtro (labels, dropdowns, date pickers, botones)

    Returns:
        html.Div con clase .t-filter-bar
    """
    return html.Div(list(children), className="t-filter-bar")
