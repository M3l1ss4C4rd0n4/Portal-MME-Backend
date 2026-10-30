"""Render del Informe Semanal de Dirección de Energía.

Un solo generador para los dos destinos:

* `interactivo=True`  → HTML oscuro con tema conmutable, navegación por sección,
  filtro de "solo lo que cambió" y tooltips. Los colores salen como `var(--x)`
  para que el conmutador de tema repinte también las gráficas.
* `interactivo=False` → HTML claro, sin JavaScript y con colores literales, que
  es lo que WeasyPrint necesita para imprimir el PDF.

El texto nunca se pinta del color de la serie: los valores y etiquetas van en
tinta primaria/secundaria y es la marca de color contigua la que lleva la identidad.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from domain.services.informe_de_modelo import Informe, Kpi, Seccion, Serie
from domain.services.informe_de_svg import (
    Barra,
    barra_apilada,
    barras_horizontales,
    leyenda,
    medidor,
)

_E = html.escape

# Rampas validadas con scripts/validate_palette.js de la habilidad dataviz.
_RAMPAS = {
    "claro": {
        "azul": ("#1e3a8a", "#1d4ed8", "#3b82f6", "#60a5fa"),
        "oro": ("#78350f", "#b45309", "#d97706", "#f59e0b"),
    },
    "oscuro": {
        "azul": ("#1e40af", "#2563eb", "#3b82f6", "#60a5fa"),
        "oro": ("#b45309", "#d97706", "#f59e0b", "#fbbf24"),
    },
}
_ESTADOS = {"bien": "#10B981", "alerta": "#F59E0B", "critico": "#EF4444", "neutro": "#64748B"}


@dataclass(frozen=True)
class Paleta:
    """Traduce el ROL de un punto a un color concreto.

    En modo interactivo devuelve `var(--serie-...)`, que los navegadores
    resuelven también dentro de atributos de presentación de un SVG en línea;
    así el conmutador de tema repinta las gráficas sin regenerarlas. Para el PDF
    devuelve el hex literal, porque WeasyPrint no resuelve variables CSS.
    """

    modo: str
    usar_variables: bool

    def color(self, rol: str, rampa: str) -> str:
        if rol in _ESTADOS:
            return f"var(--estado-{rol})" if self.usar_variables else _ESTADOS[rol]
        indice = int(rol.rsplit("-", 1)[-1]) if rol.startswith("paso-") else 0
        indice = max(0, min(3, indice))
        if self.usar_variables:
            return f"var(--{rampa}-{indice})"
        return _RAMPAS[self.modo][rampa][indice]

    # Tintas del SVG. En interactivo salen como var() para que el conmutador de
    # tema las repinte; impresas salen literales porque WeasyPrint no resuelve
    # var() dentro de un SVG y lo que no resuelve lo pinta de negro.
    @property
    def pista(self) -> str:
        return "var(--pista)" if self.usar_variables else "#E6EBF2"

    @property
    def tinta(self) -> str:
        return "var(--tinta)" if self.usar_variables else "#0C1726"

    @property
    def tinta_suave(self) -> str:
        return "var(--tinta-3)" if self.usar_variables else "#7C8798"

    @property
    def tinta_media(self) -> str:
        return "var(--tinta-2)" if self.usar_variables else "#47536B"


# ── Formato de números (estilo colombiano: miles con punto, decimal con coma) ──

def _es(valor: float, decimales: int) -> str:
    return f"{valor:,.{decimales}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def formatear(valor: float | None, formato: str, unidad: str = "") -> str:
    if valor is None:
        return "N/D"
    if formato == "pct":
        # Cerca de los extremos el último decimal ES el dato: 99,87% dice que
        # algo quedó sin pagar y 99,9% lo esconde; 4,37% de avance es otra cosa
        # que 4,4%. En el rango medio un decimal basta y se lee mejor.
        # Esta regla debe coincidir con la de _pct en informe_de_recoleccion,
        # o la tarjeta y su medidor mostrarían la misma cifra con distinta cara.
        decimales = 2 if (abs(valor) < 10 or abs(valor) >= 99) else 1
        return f"{_es(valor, decimales)}%"
    if formato == "cop_corto":
        a = abs(valor)
        if a >= 1e12:
            return f"${_es(valor / 1e12, 2)} bill."
        if a >= 1e9:
            return f"${_es(valor / 1e9, 1)} mil M"
        if a >= 1e6:
            return f"${_es(valor / 1e6, 0)} M"
        return f"${_es(valor, 0)}"
    if formato == "cop":
        return f"${_es(valor, 0)}"
    if formato == "num1":
        return _es(valor, 1) + (f" {unidad}" if unidad else "")
    return _es(valor, 0) + (f" {unidad}" if unidad else "")


def _clase_delta(kpi: Kpi) -> str:
    """Verde/rojo según el SENTIDO del indicador, no según el signo.

    Que el saldo pendiente baje es bueno; que el pagado baje es malo. Pintar
    ambos por el signo del delta diría lo contrario en uno de los dos.
    """
    if kpi.delta is None or abs(kpi.delta) < 1e-9:
        return "delta-igual"
    sube = kpi.delta > 0
    if kpi.sentido == "mas_es_mejor":
        return "delta-bien" if sube else "delta-mal"
    if kpi.sentido == "menos_es_mejor":
        return "delta-mal" if sube else "delta-bien"
    return "delta-neutro"


def ventana_delta(dias: int | None) -> str:
    """Cómo se nombra el periodo contra el que se compara.

    El informe corre los viernes, así que lo normal son 7 días y la frase que
    la gente espera leer es "la semana pasada", no "hace 7 días". Los otros
    casos existen de verdad: si un viernes festivo no corrió la tarea, el
    siguiente compara contra hace 14, y decirlo evita leer dos semanas de
    movimiento como si fuera una.
    """
    if dias is None or dias == 7:
        return "la semana pasada"
    if dias == 1:
        return "ayer"
    if dias % 7 == 0:
        return f"hace {dias // 7} semanas"
    return f"hace {dias} días"


def _chip_delta(kpi: Kpi) -> str:
    if kpi.delta is None:
        return '<span class="delta delta-sin" title="Sin foto anterior para comparar">— sin histórico</span>'
    if abs(kpi.delta) < 1e-9:
        return '<span class="delta delta-igual">= sin cambio</span>'
    flecha = "▲" if kpi.delta > 0 else "▼"
    texto = formatear(abs(kpi.delta), kpi.formato, kpi.unidad)
    ventana = ventana_delta(kpi.dias_delta)
    return (
        f'<span class="delta {_clase_delta(kpi)}" title="Variación frente a {ventana}">'
        f"{flecha} {_E(texto)} <small>vs {ventana}</small></span>"
    )


def _tarjeta_kpi(kpi: Kpi) -> str:
    cambio = "con-cambio" if (kpi.delta is not None and abs(kpi.delta) > 1e-9) else "sin-cambio"
    detalle = f'<div class="kpi-detalle">{_E(kpi.detalle)}</div>' if kpi.detalle else ""
    unidad = f'<span class="kpi-unidad">{_E(kpi.unidad)}</span>' if kpi.unidad else ""
    return f"""
    <article class="kpi {cambio}">
      <h4 class="kpi-etiqueta">{_E(kpi.etiqueta)}</h4>
      <div class="kpi-valor">{_E(formatear(kpi.valor, kpi.formato))}{unidad}</div>
      {_chip_delta(kpi)}
      {detalle}
    </article>"""


def _render_serie(serie: Serie, paleta: Paleta) -> str:
    puntos = tuple(p for p in serie.puntos if p.valor is not None)
    if not puntos:
        return ""

    nota = f'<p class="serie-nota">{_E(serie.nota)}</p>' if serie.nota else ""
    cabecera = f'<h4 class="serie-titulo">{_E(serie.titulo)}</h4>'

    if serie.tipo == "medidores":
        medidores = "".join(
            medidor(
                p.valor,
                p.etiqueta,
                p.valor_texto or formatear(p.valor, "pct"),
                color=paleta.color(p.rol, serie.rampa),
                pista=paleta.pista,
                tinta=paleta.tinta,
                tinta_suave=paleta.tinta_suave,
            )
            for p in puntos
        )
        return (
            f'<div class="serie">{cabecera}'
            f'<div class="medidores" data-n="{len(puntos)}">{medidores}</div>'
            f"{nota}</div>"
        )

    barras = tuple(
        Barra(
            etiqueta=p.etiqueta,
            valor=p.valor,
            color=paleta.color(p.rol, serie.rampa),
            valor_texto=p.valor_texto or formatear(p.valor, "num"),
            nota=p.nota,
        )
        for p in puntos
    )

    if serie.tipo == "apilada":
        cuerpo = barra_apilada(barras) + leyenda(barras)
    else:
        cuerpo = barras_horizontales(
            barras,
            pista=paleta.pista,
            tinta=paleta.tinta,
            tinta_suave=paleta.tinta_media,
        )
    return f'<div class="serie">{cabecera}{cuerpo}{nota}</div>'


def _render_seccion(seccion: Seccion, paleta: Paleta, indice: int) -> str:
    if seccion.error:
        return f"""
  <section class="seccion seccion-caida" id="sec-{seccion.clave}">
    <header class="seccion-cab">
      <h2>{_E(seccion.titulo)}</h2>
    </header>
    <p class="aviso-fallo"><strong>No se pudo evaluar esta sección.</strong>
      La fuente no respondió, así que aquí no hay dato — que no es lo mismo que
      un dato en cero. Detalle técnico: <code>{_E(seccion.error)}</code></p>
  </section>"""

    kpis = "".join(_tarjeta_kpi(k) for k in seccion.kpis)
    n_kpis = len(seccion.kpis)
    series = "".join(_render_serie(s, paleta) for s in seccion.series)
    lectura = f'<p class="lectura">{_E(seccion.lectura)}</p>' if seccion.lectura else ""
    fuentes = ""
    if seccion.tableros:
        chips = "".join(f"<span>{_E(t)}</span>" for t in seccion.tableros)
        plural = "tableros" if len(seccion.tableros) > 1 else "tablero"
        fuentes = f'<div class="fuentes"><em>Resume {len(seccion.tableros)} {plural}:</em>{chips}</div>'

    corte = f'<span class="corte">Corte {_E(seccion.corte)}</span>' if seccion.corte else ""

    return f"""
  <section class="seccion" id="sec-{seccion.clave}" data-seccion="{seccion.clave}">
    <header class="seccion-cab">
      <div class="seccion-num">{indice:02d}</div>
      <div>
        <h2>{_E(seccion.titulo)}</h2>
        <p class="seccion-sub">{_E(seccion.subtitulo)}</p>
      </div>
      {corte}
    </header>
    {lectura}
    <div class="kpi-grid" data-n="{n_kpis}">{kpis}</div>
    <div class="series">{series}</div>
    {fuentes}
  </section>"""


# ── Hoja de estilos ───────────────────────────────────────────────────────────
# Modo CLARO en :root para que el PDF (que no lleva data-theme) imprima en claro.
# El oscuro se declara bajo los dos ámbitos que exige el contrato de temas: la
# media query del sistema, protegida para que un data-theme="light" explícito le
# gane, y el ámbito del conmutador.
_CSS = """
:root{
  color-scheme:light;
  --fondo:#F5F7FB; --superficie:#FFFFFF; --superficie-2:#F1F5F9;
  --borde:#DFE5EF; --borde-suave:#EDF1F7;
  --tinta:#0C1726; --tinta-2:#47536B; --tinta-3:#7C8798;
  --pista:#E6EBF2; --acento:#1d4ed8; --acento-suave:#E8EFFD;
  --azul-0:#1e3a8a; --azul-1:#1d4ed8; --azul-2:#3b82f6; --azul-3:#60a5fa;
  --oro-0:#78350f; --oro-1:#b45309; --oro-2:#d97706; --oro-3:#f59e0b;
  --estado-bien:#047857; --estado-alerta:#B45309; --estado-critico:#B91C1C;
  --estado-neutro:#64748B;
  --sombra:0 1px 2px rgba(12,23,38,.06), 0 8px 24px -12px rgba(12,23,38,.18);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --fondo:#060B14; --superficie:#0F172A; --superficie-2:#132033;
    --borde:#1E2D44; --borde-suave:#182538;
    --tinta:#F1F5F9; --tinta-2:#AAB7C8; --tinta-3:#7D8A9E;
    --pista:#1C2A3F; --acento:#60a5fa; --acento-suave:#13243E;
    --azul-0:#1e40af; --azul-1:#2563eb; --azul-2:#3b82f6; --azul-3:#60a5fa;
    --oro-0:#b45309; --oro-1:#d97706; --oro-2:#f59e0b; --oro-3:#fbbf24;
    --estado-bien:#10B981; --estado-alerta:#F59E0B; --estado-critico:#EF4444;
    --estado-neutro:#94A3B8;
    --sombra:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -14px rgba(0,0,0,.7);
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --fondo:#060B14; --superficie:#0F172A; --superficie-2:#132033;
  --borde:#1E2D44; --borde-suave:#182538;
  --tinta:#F1F5F9; --tinta-2:#AAB7C8; --tinta-3:#7D8A9E;
  --pista:#1C2A3F; --acento:#60a5fa; --acento-suave:#13243E;
  --azul-0:#1e40af; --azul-1:#2563eb; --azul-2:#3b82f6; --azul-3:#60a5fa;
  --oro-0:#b45309; --oro-1:#d97706; --oro-2:#f59e0b; --oro-3:#fbbf24;
  --estado-bien:#10B981; --estado-alerta:#F59E0B; --estado-critico:#EF4444;
  --estado-neutro:#94A3B8;
  --sombra:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -14px rgba(0,0,0,.7);
}

*{box-sizing:border-box;}
html{-webkit-text-size-adjust:100%;}
body{
  margin:0; background:var(--fondo); color:var(--tinta);
  font-family:"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  font-size:15px; line-height:1.5;
  font-variant-numeric:tabular-nums;
}
.envoltura{max-width:1180px; margin:0 auto; padding:0 16px 56px;}

/* ── Cabecera ─────────────────────────────────────────────────────────────── */
.cinta{height:3px; background:linear-gradient(90deg,var(--azul-1),var(--oro-2) 55%,var(--azul-3));}
.cabecera{padding:26px 0 18px; border-bottom:1px solid var(--borde);}
.cabecera-fila{display:flex; flex-wrap:wrap; gap:16px; align-items:flex-end; justify-content:space-between;}
.marca{font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--tinta-3); font-weight:700;}
h1{margin:6px 0 2px; font-size:clamp(23px,4vw,33px); line-height:1.12; letter-spacing:-.02em;}
.sub-cabecera{margin:0; color:var(--tinta-2); font-size:14px;}
.acciones{display:flex; gap:8px; flex-wrap:wrap;}
.boton{
  appearance:none; cursor:pointer; font:inherit; font-size:13px; font-weight:600;
  padding:8px 14px; border-radius:999px; border:1px solid var(--borde);
  background:var(--superficie); color:var(--tinta-2); text-decoration:none;
  display:inline-flex; align-items:center; gap:7px; transition:.16s ease;
}
.boton:hover{border-color:var(--acento); color:var(--acento); transform:translateY(-1px);}
.boton[aria-pressed="true"]{background:var(--acento-suave); border-color:var(--acento); color:var(--acento);}

/* ── Portada: los cuatro titulares ────────────────────────────────────────── */
.portada{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px;
  margin:22px 0 10px;
}
.titular{
  background:var(--superficie); border:1px solid var(--borde); border-radius:14px;
  padding:16px 18px; box-shadow:var(--sombra); position:relative; overflow:hidden;
}
.titular::before{content:""; position:absolute; inset:0 auto 0 0; width:3px; background:var(--azul-2);}
.titular:nth-child(2)::before{background:var(--azul-3);}
.titular:nth-child(3)::before{background:var(--oro-2);}
.titular:nth-child(4)::before{background:var(--oro-3);}
.titular-et{font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--tinta-3); font-weight:700;}
.titular-val{font-size:clamp(21px,3vw,27px); font-weight:800; letter-spacing:-.02em; margin-top:5px;}
.titular-pie{font-size:12px; color:var(--tinta-2); margin-top:3px;}

/* ── Navegación ───────────────────────────────────────────────────────────── */
.nav{
  position:sticky; top:0; z-index:20; display:flex; gap:7px; flex-wrap:wrap;
  padding:11px 0; margin-bottom:6px;
  background:color-mix(in srgb,var(--fondo) 88%,transparent);
  backdrop-filter:blur(10px); border-bottom:1px solid var(--borde-suave);
}
.nav a{
  font-size:13px; font-weight:600; text-decoration:none; color:var(--tinta-2);
  padding:6px 13px; border-radius:999px; border:1px solid transparent; transition:.16s ease;
}
.nav a:hover{background:var(--superficie-2); color:var(--tinta);}
.nav a.activo{background:var(--acento-suave); color:var(--acento); border-color:var(--acento);}

/* ── Secciones ────────────────────────────────────────────────────────────── */
.seccion{
  background:var(--superficie); border:1px solid var(--borde); border-radius:16px;
  padding:22px; margin:16px 0; box-shadow:var(--sombra);
}
.seccion-cab{display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:12px;}
.seccion-num{
  font-size:12px; font-weight:800; color:var(--acento); background:var(--acento-suave);
  border-radius:9px; padding:7px 10px; letter-spacing:.06em;
}
.seccion-cab h2{margin:0; font-size:20px; letter-spacing:-.01em;}
.seccion-sub{margin:1px 0 0; color:var(--tinta-2); font-size:13px;}
.corte{margin-left:auto; font-size:12px; color:var(--tinta-3); white-space:nowrap;}
.lectura{
  margin:0 0 16px; padding:11px 14px; border-left:3px solid var(--acento);
  background:var(--superficie-2); border-radius:0 10px 10px 0;
  font-size:14px; color:var(--tinta-2);
}

/* ── Tarjetas de indicador ────────────────────────────────────────────────── */
.kpi-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(172px,1fr)); gap:10px;}
.kpi{
  background:var(--superficie-2); border:1px solid var(--borde-suave);
  border-radius:12px; padding:13px 14px; transition:.16s ease;
}
.kpi:hover{border-color:var(--acento); transform:translateY(-2px);}
.kpi-etiqueta{
  margin:0; font-size:11px; font-weight:700; letter-spacing:.07em;
  text-transform:uppercase; color:var(--tinta-3);
}
.kpi-valor{font-size:clamp(17px,2.2vw,22px); font-weight:800; letter-spacing:-.025em;
  margin:5px 0 6px; white-space:nowrap; overflow-wrap:normal;}
.kpi-detalle{font-size:11.5px; color:var(--tinta-3); margin-top:5px;}
.kpi-unidad{font-size:.62em; font-weight:700; color:var(--tinta-3); margin-left:3px;}
.delta{display:inline-flex; align-items:center; gap:4px; font-size:11.5px; font-weight:700; border-radius:6px; padding:2px 6px;}
.delta small{font-weight:500; opacity:.78;}
.delta-bien{color:var(--estado-bien); background:color-mix(in srgb,var(--estado-bien) 12%,transparent);}
.delta-mal{color:var(--estado-critico); background:color-mix(in srgb,var(--estado-critico) 12%,transparent);}
.delta-neutro,.delta-igual{color:var(--tinta-3); background:var(--pista);}
.delta-sin{color:var(--tinta-3); background:transparent; padding-left:0; font-weight:500;}

/* ── Gráficas ─────────────────────────────────────────────────────────────── */
.series{display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:20px; margin-top:20px;}
.serie{min-width:0;}
.serie-titulo{
  margin:0 0 10px; font-size:11px; font-weight:700; letter-spacing:.09em;
  text-transform:uppercase; color:var(--tinta-3);
}
.serie-nota{margin:8px 0 0; font-size:11.5px; color:var(--tinta-3); line-height:1.45;}
.medidores{
  display:flex; flex-wrap:wrap; gap:4px 10px;
  justify-content:center; align-items:flex-start; width:100%;
}
/* Los medidores se reparten el ancho de su bloque en vez de amontonarse a la
   izquierda dejando media columna vacía. El tope impide que uno solo se infle
   hasta ocupar la sección entera. */
.medidores .medidor{flex:1 1 0; width:auto; height:auto; min-width:116px; max-width:178px;}
.medidores[data-n="1"] .medidor{max-width:208px;}
.medidores[data-n="2"] .medidor{max-width:216px;}
.medidores[data-n="3"] .medidor{max-width:190px;}
.medidor-valor{font-size:25px; font-weight:800; fill:var(--tinta);}
.medidor-etiqueta{font-size:11px; font-weight:600; fill:var(--tinta-3);}
.barras{overflow:visible;}
.barra-etiqueta{font-size:11.5px; fill:var(--tinta-2);}
.barra-valor{font-size:12px; font-weight:700; fill:var(--tinta);}
.fila-barra:hover .barra-valor{fill:var(--acento);}
.leyenda{display:flex; flex-wrap:wrap; gap:7px 14px; margin-top:11px;}
.chip-leyenda{display:inline-flex; align-items:center; gap:6px; font-size:12px; color:var(--tinta-2);}
.chip-leyenda i{width:10px; height:10px; border-radius:3px; display:inline-block; flex:none;}
.chip-leyenda b{color:var(--tinta); font-weight:700;}

/* ── Procedencia y fallos ─────────────────────────────────────────────────── */
.fuentes{
  margin-top:18px; padding-top:13px; border-top:1px dashed var(--borde);
  display:flex; flex-wrap:wrap; gap:7px; align-items:center;
  font-size:11.5px; color:var(--tinta-3);
}
.fuentes em{font-style:normal; font-weight:600;}
.fuentes span{background:var(--superficie-2); border:1px solid var(--borde-suave); border-radius:999px; padding:3px 9px;}
.seccion-caida{border-color:var(--estado-alerta);}
.aviso-fallo{margin:0; font-size:13.5px; color:var(--tinta-2); line-height:1.55;}
.aviso-fallo code{font-size:11.5px; background:var(--superficie-2); padding:2px 6px; border-radius:5px;}
.pie{margin-top:28px; padding-top:18px; border-top:1px solid var(--borde); font-size:12px; color:var(--tinta-3); line-height:1.65;}

/* Filtro "solo lo que cambió" */
body.solo-cambios .kpi.sin-cambio{display:none;}
body.solo-cambios .series{display:none;}

@media (max-width:640px){
  .seccion{padding:16px;}
  .corte{margin-left:0; width:100%;}
}
@media (prefers-reduced-motion:reduce){*{transition:none !important;}}

/* ── Impresión / PDF ──────────────────────────────────────────────────────── */
@page{size:A4 portrait; margin:12mm 11mm;}
@media print{
  body{background:#fff; font-size:9.5pt;}
  .nav,.acciones{display:none !important;}
  .envoltura{max-width:none; padding:0;}
  /* NO se pone break-inside:avoid en .seccion: una sección que no cabía en lo
     que quedaba de hoja saltaba entera a la siguiente y dejaba media página en
     blanco — por eso la portada se quedaba sola en la primera. Se protegen solo
     las piezas pequeñas, que sí deben viajar completas. */
  .seccion{box-shadow:none; margin:6px 0; padding:11px;}
  .titular,.kpi,.serie,.lectura{break-inside:avoid; page-break-inside:avoid;}
  .seccion-cab{break-inside:avoid; break-after:avoid; page-break-after:avoid;}
  /* La cabecera no merece una hoja entera para ella sola. */
  .cabecera{padding:0 0 9px;}
  h1{margin:3px 0 1px;}
  .portada{margin:11px 0 7px;}
  .pie{margin-top:14px; padding-top:10px;}
  /* WeasyPrint no soporta grid auto-fit: sin esto cada tarjeta ocupa una fila
     entera y el informe pasa de 3 a 9 páginas. */
  .portada,.kpi-grid,.series{display:block; font-size:0;}
  .portada>*,.kpi-grid>*,.series>*{
    display:inline-block; vertical-align:top; font-size:9.5pt;
    box-sizing:border-box;
  }
  .portada>*{width:19.4%; margin:0 .3% 5px;}
  .kpi-grid>*{width:32.6%; margin:0 .3% 5px; padding:9px 10px;}
  /* Con 4 indicadores, tres columnas dejan uno suelto en una fila nueva. */
  .kpi-grid[data-n="4"]>*{width:24.4%;}
  /* Las gráficas van en BLOQUE, no inline-block: como inline formaban una sola
     línea, y una línea no se parte entre páginas, así que las dos saltaban
     juntas a la hoja siguiente dejando media página en blanco. */
  .series{display:block; font-size:9.5pt;}
  .series>*{display:block; width:100%; margin:0 0 9px;}
  /* Solo las barras ocupan todo el ancho. Sin acotar el selector, este
     !important también le ganaba al ancho de los medidores y cada uno se
     inflaba a media hoja: cuatro medidores ocupaban dos páginas enteras. */
  .series svg.barras,.series svg.apilada{width:100% !important; height:auto;}
  /* WeasyPrint no reparte un flex con flex-basis:0; aquí van inline-block con
     ancho porcentual, y el bloque centrado. */
  .medidores{display:block; text-align:center;}
  .medidores .medidor{display:inline-block; vertical-align:top; max-width:none;}
  .medidores[data-n="1"] .medidor{width:26%;}
  .medidores[data-n="2"] .medidor{width:31%;}
  .medidores[data-n="3"] .medidor{width:27%;}
  .medidores[data-n="4"] .medidor{width:22%;}
  .leyenda{display:block;}
  /* En impresión el chip deja de ser flex, así que el gap desaparece y el
     cuadrito queda pegado a la palabra. */
  .chip-leyenda{display:inline-block; margin:0 14px 3px 0;}
  .chip-leyenda i{margin-right:5px; vertical-align:baseline;}
  .kpi-valor{font-size:14pt;}
  .seccion-cab h2{font-size:14pt;}
  .medidor{max-width:150px;}
  h1{font-size:19pt;}
}
"""

_JS = """
(function(){
  var raiz=document.documentElement;
  var btnTema=document.getElementById('btn-tema');
  var btnCambios=document.getElementById('btn-cambios');

  function pintarTema(t){
    raiz.setAttribute('data-theme',t);
    if(btnTema) btnTema.textContent = t==='dark' ? '☀ Modo claro' : '☾ Modo oscuro';
    try{ localStorage.setItem('informe-de-tema',t); }catch(e){}
  }
  try{
    var guardado=localStorage.getItem('informe-de-tema');
    if(guardado) pintarTema(guardado);
  }catch(e){}
  if(btnTema) btnTema.addEventListener('click',function(){
    pintarTema(raiz.getAttribute('data-theme')==='dark'?'light':'dark');
  });

  if(btnCambios) btnCambios.addEventListener('click',function(){
    var on=document.body.classList.toggle('solo-cambios');
    btnCambios.setAttribute('aria-pressed',on?'true':'false');
    btnCambios.textContent = on ? '◉ Viendo solo cambios' : '◎ Solo lo que cambió';
  });

  // Resalta en la navegación la sección que se está leyendo.
  var enlaces=[].slice.call(document.querySelectorAll('.nav a'));
  var secciones=enlaces.map(function(a){return document.querySelector(a.getAttribute('href'));}).filter(Boolean);
  if('IntersectionObserver' in window && secciones.length){
    var obs=new IntersectionObserver(function(entradas){
      entradas.forEach(function(e){
        if(!e.isIntersecting) return;
        enlaces.forEach(function(a){
          a.classList.toggle('activo', a.getAttribute('href')==='#'+e.target.id);
        });
      });
    },{rootMargin:'-20% 0px -70% 0px'});
    secciones.forEach(function(s){obs.observe(s);});
  }
})();
"""


# Indicador que encabeza cada sección en la portada. Se elige a mano porque es
# una decisión editorial — cuál es "el número" de cada tablero —, no algo que
# se pueda deducir de los datos.
_TITULAR = {
    "presupuesto": "apropiacion",
    "supervision": "contratos",
    "subsidios": "saldo_pendiente",
    "comunidades": "ces_implementadas",
}


def _portada(secciones: tuple[Seccion, ...]) -> str:
    tarjetas: list[str] = []
    for seccion in secciones:
        if seccion.error:
            continue
        clave = _TITULAR.get(seccion.clave)
        kpi = next((k for k in seccion.kpis if k.clave == clave), None)
        if kpi is None:
            kpi = seccion.kpis[0] if seccion.kpis else None
        if kpi is None:
            continue
        tarjetas.append(f"""
      <div class="titular">
        <div class="titular-et">{_E(seccion.titulo_corto or seccion.titulo)}</div>
        <div class="titular-val">{_E(formatear(kpi.valor, kpi.formato, kpi.unidad))}</div>
        <div class="titular-pie">{_E(kpi.etiqueta)}{' · ' + _E(kpi.detalle) if kpi.detalle else ''}</div>
      </div>""")
    return f'<div class="portada">{"".join(tarjetas)}</div>' if tarjetas else ""


def _nav(secciones: tuple[Seccion, ...]) -> str:
    enlaces = "".join(
        f'<a href="#sec-{s.clave}">{_E(s.titulo)}</a>' for s in secciones
    )
    return f'<nav class="nav" aria-label="Secciones del informe">{enlaces}</nav>'


def render(informe: Informe, *, interactivo: bool = True) -> str:
    """Documento HTML completo. `interactivo=False` produce el que va al PDF."""
    paleta = Paleta(
        modo="oscuro" if interactivo else "claro",
        usar_variables=interactivo,
    )

    secciones_html = "".join(
        _render_seccion(s, paleta, i) for i, s in enumerate(informe.secciones, start=1)
    )

    n_tableros = sum(len(s.tableros) for s in informe.secciones_ok)
    n_kpis = sum(len(s.kpis) for s in informe.secciones_ok)

    acciones = ""
    script = ""
    tema = ""
    nav = ""
    if interactivo:
        tema = ' data-theme="dark"'
        nav = _nav(informe.secciones)
        acciones = """
        <div class="acciones">
          <button class="boton" id="btn-cambios" type="button" aria-pressed="false">◎ Solo lo que cambió</button>
          <button class="boton" id="btn-tema" type="button">☀ Modo claro</button>
          <a class="boton" href="?formato=pdf">⤓ Descargar PDF</a>
        </div>"""
        script = f"<script>{_JS}</script>"

    fallidas = informe.fallidas
    aviso = ""
    if fallidas:
        nombres = ", ".join(s.titulo for s in fallidas)
        aviso = (
            f'<p class="aviso-fallo" style="margin:14px 0 0">'
            f"<strong>Atención:</strong> {len(fallidas)} sección(es) sin datos esta semana "
            f"({_E(nombres)}). Aparecen marcadas más abajo: no se pudieron evaluar, "
            f"que no es lo mismo que estar en cero.</p>"
        )

    return f"""<!DOCTYPE html>
<html lang="es"{tema}>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Informe Semanal · Dirección de Energía</title>
<meta name="description" content="Indicadores clave de los tableros de Dirección de Energía y Comunidades Energéticas al {_E(informe.fecha)}."/>
<style>{_CSS}</style>
</head>
<body>
<div class="cinta"></div>
<div class="envoltura">
  <header class="cabecera">
    <div class="cabecera-fila">
      <div>
        <div class="marca">Ministerio de Minas y Energía · Dirección de Energía</div>
        <h1>Informe Semanal de Dirección de Energía</h1>
        <p class="sub-cabecera">{_E(informe.fecha)} · {len(informe.secciones_ok)} secciones ·
           {n_tableros} tableros · {n_kpis} indicadores</p>
      </div>
      {acciones}
    </div>
    {aviso}
  </header>
  {_portada(informe.secciones)}
  {nav}
  <main>{secciones_html}</main>
  <footer class="pie">
    <strong>Cómo leer este informe.</strong> Cada sección resume varios tableros del portal
    en sus indicadores decisivos; no reemplaza al tablero, lleva a él. La variación se
    calcula contra la última foto guardada, que normalmente es la del viernes anterior:
    cada indicador dice contra qué periodo se compara. Un indicador sin histórico es uno que se mide por
    primera vez, no uno que no cambió.<br/>
    Generado automáticamente el {_E(informe.generado_en)}. Fuente: los mismos endpoints
    que alimentan los tableros del portal.
  </footer>
</div>
{script}
</body>
</html>"""
