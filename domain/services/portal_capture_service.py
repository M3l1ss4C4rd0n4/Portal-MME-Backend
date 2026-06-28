"""
Captura selectiva de componentes del frontend React para los PDFs de tableros.
Abre UNA sesión de browser por tablero y captura todos los elementos necesarios.
Solo se captura lo que Plotly no puede replicar fielmente:
  - SankeyFlow (componente custom, único en Supervisión)
  - Mapas Leaflet (Fenoge, Comunidades)
  - Gauges/donuts/barras/líneas de Nivo y componentes custom
"""
import base64
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

CHROME_PATH = "/home/admonctrlxm/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
CHROME_FALLBACK = "/tmp/chrome-linux64/chrome"
FRONTEND_URL = "http://localhost:3001"
ELEMENT_WAIT_MS = 1500
MIN_PNG_BYTES = 2000

_CHROME_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process",
]

_PREPARE_JS = r"""
() => {
    // Forzar modo claro
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
    try { localStorage.setItem('theme', 'light'); } catch(e) {}

    // Ocultar nav/header y controles de UI
    document.querySelectorAll('nav, header').forEach(el => el.style.display = 'none');

    // Ocultar botones de acción por texto
    document.querySelectorAll('button').forEach(btn => {
        const t = (btn.textContent || '').trim().toLowerCase();
        const a = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (['pdf','excel','exportar excel','limpiar','restablecer','generando','✕',
             'resumen','ejecutivo','informe','empalme','chatbot','cerrar']
            .some(k => t.includes(k) || a.includes(k))) {
            btn.style.display = 'none';
        }
    });

    // Ocultar sliders de año
    document.querySelectorAll('input[type="range"]').forEach(el => el.style.display = 'none');
    document.querySelectorAll('div').forEach(el => {
        if (el.textContent && el.textContent.includes('PERÍODO') &&
            el.classList && Array.from(el.classList).some(c => c.includes('px-1'))) {
            el.style.display = 'none';
        }
    });

    // Ocultar selects (por ejemplo año en subsidios) y sus labels
    document.querySelectorAll('select').forEach(el => {
        const wrap = el.closest('div');
        if (wrap) wrap.style.display = 'none';
        else el.style.display = 'none';
    });

    // Ocultar labels de departamento en mapas Leaflet
    document.querySelectorAll('.dept-label-icon, .dept-label-text').forEach(el => el.style.display = 'none');

    // Ocultar controles Leaflet (zoom, etc.)
    document.querySelectorAll('.leaflet-control-container').forEach(el => el.style.display = 'none');

    // Ocultar overlays fijos/sticky (excepto Leaflet)
    document.querySelectorAll('*').forEach(el => {
        try {
            const pos = window.getComputedStyle(el).position;
            if ((pos === 'fixed' || pos === 'sticky') && !el.closest('.leaflet-container'))
                el.style.display = 'none';
        } catch(e) {}
    });

    // Desactivar animaciones y transiciones
    const style = document.createElement('style');
    style.textContent = `
      *, *::before, *::after {
        animation-duration: 0.001s !important;
        animation-delay: 0s !important;
        transition-duration: 0.001s !important;
        transition-delay: 0s !important;
        animation-fill-mode: forwards !important;
      }
      .pdf-capture-mode * {
        animation: none !important;
        transition: none !important;
      }`;
    document.head.appendChild(style);
    document.body.classList.add('pdf-capture-mode');

    // Forzar visibilidad de elementos con opacity:0 inicial (framer-motion)
    document.querySelectorAll('div[style]').forEach(el => {
        const s = el.getAttribute('style') || '';
        if (s.includes('opacity: 0') || s.includes('opacity:0')) {
            el.style.setProperty('opacity', '1', 'important');
            el.style.setProperty('transform', 'none', 'important');
        }
    });

    // Asegurar que elementos con transform de framer-motion sean visibles
    document.querySelectorAll('[style*="transform"]').forEach(el => {
        const s = el.getAttribute('style') || '';
        if (s.includes('opacity: 0') || s.includes('opacity:0')) {
            el.style.setProperty('opacity', '1', 'important');
            el.style.setProperty('transform', 'none', 'important');
        }
    });
}
"""

# JS para encontrar el .rounded-2xl o .rounded-xl ancestro que contiene un título
_FIND_CARD_JS = r"""
(title) => {
    const needle = title.toUpperCase();
    const allText = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6, span, div, p, label'));
    // Ignorar nodos contenedores gigantes cuyo texto sea mucho mayor que el título buscado
    const matches = allText.filter(s => {
        const t = s.textContent.trim().toUpperCase();
        return t.includes(needle) && t.length <= needle.length * 4 + 40;
    });
    if (matches.length === 0) return null;
    let best = null;
    let bestArea = Infinity;
    for (const node of matches) {
        let el = node;
        let depth = 0;
        while (el && el !== document.body && depth < 25) {
            const cls = Array.from(el.classList || []).join(' ');
            const rect = el.getBoundingClientRect();
            if ((cls.includes('rounded-2xl') || cls.includes('rounded-xl')) && rect.width > 50 && rect.height > 50) {
                const area = rect.width * rect.height;
                // Elegir el card más pequeño que contenga el título (evita secciones enormes)
                if (area > 2000 && area < bestArea) { bestArea = area; best = el; }
                break;
            }
            el = el.parentElement;
            depth++;
        }
    }
    return best;
}
"""


def _chrome_executable() -> str:
    if os.path.exists(CHROME_PATH):
        return CHROME_PATH
    if os.path.exists(CHROME_FALLBACK):
        return CHROME_FALLBACK
    raise FileNotFoundError(f"Chrome no encontrado en {CHROME_PATH} ni {CHROME_FALLBACK}")


def _png_to_b64(png: bytes | None) -> str:
    if not png or len(png) < MIN_PNG_BYTES:
        return ""
    return base64.b64encode(png).decode()


# ── Qué capturar por tablero ──────────────────────────────────────────────────
# - title: busca .rounded-2xl/.rounded-xl que contenga este texto (insensible)
# - selector: usa CSS selector directo (para Leaflet)
_SPECS: dict[str, list[dict]] = {
    "supervision": [
        {"name": "sankey", "title": "FLUJO DE CONTRATOS — FONDO"},
        {"name": "line_avance", "title": "EVOLUCIÓN DEL AVANCE DE OBRA PROMEDIO"},
        {"name": "pie_fondo", "selector": "#pie-contratos-fondo"},
    ],
    "presupuesto": [
        {"name": "bar_comparativo", "title": "Comparativo por Proyecto (%)"},
    ],
    "contratos-or": [
        {"name": "bar_avance_proyecto",  "title": "AVANCE POR PROYECTO (%)"},
        {"name": "curva_obras_civiles",  "selector": "#curva-s-obrasCiviles"},
        {"name": "curva_usuarios",       "selector": "#curva-s-usuarios"},
        {"name": "curva_potencia",       "selector": "#curva-s-potencia"},
        {"name": "curva_internas",       "selector": "#curva-s-internas"},
    ],
    "fenoge": [
        {"name": "mapa", "selector": ".leaflet-container"},
        {"name": "barras_departamento", "title": "CES POR DEPARTAMENTO"},
        {"name": "curva_s", "title": "AVANCE DE OBRA — SEGUIMIENTO ACUMULADO"},
    ],
    "comunidades": [
        {"name": "mapa", "selector": ".leaflet-container"},
        {"name": "bar_estado", "title": "CES POR ESTADO"},
        {"name": "bar_tipo", "title": "CES POR TIPO"},
        {"name": "bar_fuente", "title": "CES POR FUENTE"},
    ],
    "subsidios": [
        {"name": "grafico_subsidios_contribuciones", "title": "Suma de Subsidios (SIN+ZNI) y Suma de Contribuciones por Año"},
        {"name": "grafico_deficit_apropiacion", "title": "Suma de Déficit acumulado, Suma de Apropiación PGN y Suma de Déficit Año por Año"},
        {"name": "grafico_apropiacion_a1", "title": "Suma de Apropiación PGN y Suma de A-1 por Año"},
    ],
    "energia": [
        {"name": "mapa", "title": "Estado de Embalses por Departamento"},
        {"name": "generacion_fuente", "title": "Generación por Fuente"},
        {"name": "precio_bolsa", "title": "Precio de Bolsa · Histórico"},
        {"name": "capacidad_embalses", "title": "Capacidad de Embalses"},
    ],
    "colombia-solar": [
        {"name": "bar_mensual",         "title": "Planeado vs Ejecutado · Usuarios por Mes"},
        {"name": "bar_eficiencia",      "title": "Eficiencia por Programa"},
        {"name": "curva_obras_civiles", "selector": "#curva-s-obrasCiviles"},
        {"name": "curva_usuarios",      "selector": "#curva-s-usuarios"},
        {"name": "curva_potencia",      "selector": "#curva-s-potencia"},
        {"name": "curva_internas",      "selector": "#curva-s-internas"},
    ],
    "pagos": [
        {"name": "bar_trimestral", "title": "Valores pagados y pendientes por trimestre"},
        {"name": "bar_prestadores", "title": "Prestadores de servicio pendiente de pago"},
    ],
    "validaciones": [
        {"name": "bar_sin", "title": "SIN — Sistema Interconectado Nacional"},
        {"name": "bar_zni", "title": "ZNI — Zonas No Interconectadas"},
    ],
    "predicciones": [
        {"name": "curva_embalses", "title": "Proyección de Embalses"},
        {"name": "pronostico_oni", "title": "Pronóstico ONI (NOAA)"},
    ],
}

# Tableros cuya URL real no sigue el patrón /dashboards/{tablero}
_TABLERO_URLS: dict[str, str] = {
    "predicciones": f"{FRONTEND_URL}/energia/predicciones",
    "pagos": f"{FRONTEND_URL}/pagos",
}

# Timeout networkidle por tablero. Páginas con conexiones persistentes nunca
# alcanzan networkidle — reducir timeout evita esperas de 30 s innecesarias.
_NETWORKIDLE_TIMEOUT: dict[str, int] = {
    "pagos": 6000,
    "predicciones": 6000,
}


async def capture_tablero(
    tablero: str,
    dpr: int = 4,
    viewport_width: int = 1440,
    params: dict | None = None,
) -> dict[str, str]:
    """
    Abre UNA sesión de browser, carga el tablero y captura todos los
    elementos necesarios. Retorna dict {name: base64_png}.
    params: filtros activos que se agregan como query string a la URL.
    """
    specs = _SPECS.get(tablero, [])
    if not specs:
        return {}

    from playwright.async_api import async_playwright

    from urllib.parse import urlencode

    base_url = _TABLERO_URLS.get(tablero, f"{FRONTEND_URL}/dashboards/{tablero}")
    if params:
        qs = urlencode(
            {k: v for k, v in params.items() if v and v != "TODOS" and v != "all"},
        )
        if qs:
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}{qs}"
        else:
            url = base_url
    else:
        url = base_url

    logger.info("[Capture] tablero=%s url=%s dpr=%d params=%s", tablero, url, dpr, params)

    result: dict[str, str] = {}

    try:
        async with async_playwright() as p:
            exe = _chrome_executable()
            browser = await p.chromium.launch(
                executable_path=exe,
                headless=True,
                args=_CHROME_ARGS,
            )
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": 900},
                color_scheme="light",
                device_scale_factor=dpr,
            )
            page = await context.new_page()

            await page.goto(url, wait_until="load", timeout=15000)
            # 1) Esperar a que React se hidrate y las APIs respondan.
            # Algunas páginas nunca alcanzan networkidle por conexiones persistentes;
            # para esas se usa un timeout reducido + wait fijo de fallback.
            ni_timeout = _NETWORKIDLE_TIMEOUT.get(tablero, 30000)
            try:
                await page.wait_for_load_state("networkidle", timeout=ni_timeout)
            except Exception:
                logger.warning("[Capture] networkidle no alcanzado para %s — continuando con wait fijo", tablero)
                await page.wait_for_timeout(3000)
            # 2) Tiempo extra para que React re-renderice con los datos recibidos
            await page.wait_for_timeout(2000)
            # 3) Preparar página para captura (ocultar UI, desactivar animaciones)
            await page.evaluate(_PREPARE_JS)
            await page.wait_for_timeout(800)

            for spec in specs:
                name = spec["name"]
                try:
                    if "title" in spec:
                        el_handle = await page.evaluate_handle(_FIND_CARD_JS, spec["title"])
                        is_null = await el_handle.evaluate("el => el === null || el === undefined")
                        if is_null:
                            logger.warning("[Capture] Card no encontrada: %s", spec["title"])
                            continue
                        # Scroll para activar IntersectionObserver / lazy-render
                        await el_handle.evaluate(
                            "e => { e.scrollIntoView({behavior:'instant',block:'center'}); "
                            "window.dispatchEvent(new Event('resize')); }"
                        )
                        await page.wait_for_timeout(ELEMENT_WAIT_MS)
                        bbox = await el_handle.bounding_box()
                        if not bbox or bbox["width"] < 5 or bbox["height"] < 5:
                            logger.warning("[Capture] Bbox inválido para: %s", spec["title"])
                            continue
                        png = await el_handle.screenshot(type="png")

                    else:
                        el = await page.query_selector(spec["selector"])
                        if el is None:
                            logger.warning("[Capture] Selector no encontrado: %s", spec["selector"])
                            continue
                        await el.evaluate(
                            "e => { e.scrollIntoView({behavior:'instant',block:'center'}); "
                            "window.dispatchEvent(new Event('resize')); }"
                        )
                        await page.wait_for_timeout(ELEMENT_WAIT_MS)
                        png = await el.screenshot(type="png")

                    b64 = _png_to_b64(png)
                    if b64:
                        result[name] = b64
                        logger.info("[Capture] OK %s.%s: %d bytes", tablero, name, len(png))
                    else:
                        logger.warning("[Capture] Imagen vacía o demasiado pequeña: %s.%s", tablero, name)

                except Exception as exc:
                    logger.warning("[Capture] Error en %s.%s: %s", tablero, name, exc)

            await browser.close()

    except Exception as exc:
        logger.exception("[Capture] Error de sesión para %s: %s", tablero, exc)

    return result
