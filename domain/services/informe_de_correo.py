"""Cuerpo del correo y mensaje de Telegram del Informe Semanal.

El HTML interactivo del informe NO sirve como cuerpo de correo: lleva hoja de
estilos aparte, variables CSS, SVG en línea y JavaScript, y los clientes de
correo descartan las tres primeras cosas y nunca ejecutan la cuarta. Lo que
llega aquí es un resumen en tablas con estilos en línea, que es lo único que
Outlook y Gmail renderizan igual; el informe completo va adjunto en PDF.

De este módulo no sale ningún envío: solo texto. Quien envía es
`tasks/informe_de_tasks.py`, para que se vea en un solo sitio qué dispara un
correo de verdad.
"""
from __future__ import annotations

from domain.services.informe_de_modelo import Informe, Kpi, Seccion
from domain.services.informe_de_render import formatear, ventana_delta

import html

_E = html.escape

PORTAL_URL = "https://portaldireccionenergia.minenergia.gov.co/informe-direccion-energia"

# Paleta del correo: literales, no tokens. Un cliente de correo no resuelve
# var(), y lo que no resuelve lo deja sin color o lo pinta de negro.
_TINTA = "#0C1726"
_TINTA_2 = "#47536B"
_TINTA_3 = "#7C8798"
_BORDE = "#E6EBF2"
_FONDO = "#F4F6FA"
_AZUL = "#1d4ed8"
_BIEN = "#047857"
_MAL = "#B91C1C"

# Telegram corta en 4096 caracteres y devuelve 400 si se pasa. Se recorta antes
# de enviar, no después de que la API lo rechace.
LIMITE_TELEGRAM = 3900


def asunto(informe: Informe) -> str:
    return f"Informe Semanal de Dirección de Energía — {informe.fecha}"


# ─────────────────────────── Piezas compartidas ───────────────────────────

def _texto_delta(kpi: Kpi) -> tuple[str, str]:
    """(texto, color) de la variación. Verde/rojo por SENTIDO, no por signo.

    Que el saldo pendiente baje es bueno y que el pagado baje es malo: pintar
    los dos por el signo del delta diría lo contrario en uno de los dos.
    """
    if kpi.delta is None:
        return "sin histórico", _TINTA_3
    if abs(kpi.delta) < 1e-9:
        return "sin cambio", _TINTA_3

    sube = kpi.delta > 0
    flecha = "▲" if sube else "▼"
    magnitud = formatear(abs(kpi.delta), kpi.formato, kpi.unidad)
    texto = f"{flecha} {magnitud} vs {ventana_delta(kpi.dias_delta)}"

    if kpi.sentido == "mas_es_mejor":
        return texto, (_BIEN if sube else _MAL)
    if kpi.sentido == "menos_es_mejor":
        return texto, (_MAL if sube else _BIEN)
    return texto, _TINTA_2


def _resumen_movimiento(informe: Informe) -> str:
    """Cuántos indicadores se movieron. Es lo primero que se pregunta nadie."""
    kpis = [k for s in informe.secciones_ok for k in s.kpis]
    movidos = sum(1 for k in kpis if k.delta is not None and abs(k.delta) > 1e-9)
    sin_historico = sum(1 for k in kpis if k.delta is None)

    if not kpis:
        return "No se pudo leer ningún indicador esta semana."
    if sin_historico == len(kpis):
        return (
            f"{len(kpis)} indicadores medidos por primera vez: "
            "desde la próxima semana cada uno trae su variación."
        )
    if movidos == 0:
        return f"Ninguno de los {len(kpis)} indicadores cambió frente a la semana pasada."
    return (
        f"{movidos} de {len(kpis)} indicadores se movieron frente a la semana pasada."
    )


# ──────────────────────────────── Correo ────────────────────────────────

def _fila_kpi(kpi: Kpi) -> str:
    delta_texto, delta_color = _texto_delta(kpi)
    unidad = f' <span style="font-size:12px;color:{_TINTA_3};">{_E(kpi.unidad)}</span>' if kpi.unidad else ""
    return f"""
          <tr>
            <td style="padding:7px 10px;border-bottom:1px solid {_BORDE};font-size:13px;color:{_TINTA_2};">{_E(kpi.etiqueta)}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {_BORDE};font-size:15px;font-weight:700;color:{_TINTA};text-align:right;white-space:nowrap;">{_E(formatear(kpi.valor, kpi.formato))}{unidad}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {_BORDE};font-size:12px;color:{delta_color};text-align:right;white-space:nowrap;">{_E(delta_texto)}</td>
          </tr>"""


def _bloque_seccion(seccion: Seccion) -> str:
    if seccion.error:
        return f"""
      <tr><td style="padding:12px 0;">
        <div style="border-left:3px solid {_TINTA_3};background:{_FONDO};padding:10px 14px;font-size:13px;color:{_TINTA_2};">
          <strong style="color:{_TINTA};">{_E(seccion.titulo)}</strong> — sin datos esta semana.
          No se pudo evaluar, que no es lo mismo que estar en cero.
        </div>
      </td></tr>"""

    lectura = (
        f'<p style="margin:6px 0 10px;font-size:13px;line-height:1.5;color:{_TINTA_2};">{_E(seccion.lectura)}</p>'
        if seccion.lectura else ""
    )
    return f"""
      <tr><td style="padding:14px 0 4px;">
        <h2 style="margin:0;font-size:16px;color:{_TINTA};">{_E(seccion.titulo)}</h2>
        <div style="font-size:12px;color:{_TINTA_3};margin-top:2px;">{_E(seccion.subtitulo)}</div>
        {lectura}
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
               style="width:100%;border-collapse:collapse;border:1px solid {_BORDE};table-layout:fixed;">
          <tr>
            <td style="width:56%;padding:0;font-size:0;line-height:0;">&nbsp;</td>
            <td style="width:22%;padding:0;font-size:0;line-height:0;">&nbsp;</td>
            <td style="width:22%;padding:0;font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          {''.join(_fila_kpi(k) for k in seccion.kpis)}
        </table>
      </td></tr>"""


def cuerpo_email(informe: Informe) -> str:
    """HTML del correo: tablas y estilos en línea, sin CSS externo ni scripts."""
    n_tableros = sum(len(s.tableros) for s in informe.secciones_ok)
    n_kpis = sum(len(s.kpis) for s in informe.secciones_ok)
    secciones = "".join(_bloque_seccion(s) for s in informe.secciones)

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><title>{_E(asunto(informe))}</title></head>
<body style="margin:0;padding:0;background:{_FONDO};">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:{_FONDO};">
  <tr><td align="center" style="padding:20px 10px;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="640"
           style="max-width:640px;width:100%;background:#FFFFFF;border:1px solid {_BORDE};
                  font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">
      <tr><td style="height:4px;background:{_AZUL};font-size:0;line-height:0;">&nbsp;</td></tr>
      <tr><td style="padding:20px 24px 4px;">
        <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{_TINTA_3};">
          Ministerio de Minas y Energía · Dirección de Energía
        </div>
        <h1 style="margin:6px 0 2px;font-size:21px;color:{_TINTA};">Informe Semanal de Dirección de Energía</h1>
        <div style="font-size:13px;color:{_TINTA_2};">
          {_E(informe.fecha)} · {len(informe.secciones_ok)} secciones · {n_tableros} tableros · {n_kpis} indicadores
        </div>
        <p style="margin:12px 0 0;font-size:14px;line-height:1.5;color:{_TINTA};">
          {_E(_resumen_movimiento(informe))}
        </p>
      </td></tr>
      <tr><td style="padding:0 24px 8px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
          {secciones}
        </table>
      </td></tr>
      <tr><td style="padding:14px 24px 20px;">
        <a href="{PORTAL_URL}" style="display:inline-block;background:{_AZUL};color:#FFFFFF;
           text-decoration:none;padding:10px 18px;font-size:14px;font-weight:600;">
          Abrir el informe en el portal
        </a>
        <p style="margin:14px 0 0;font-size:12px;line-height:1.5;color:{_TINTA_3};">
          El PDF adjunto trae las gráficas y el detalle completo. Cada sección resume varios
          tableros del portal en sus indicadores decisivos; no reemplaza al tablero, lleva a él.
          La variación se calcula contra la foto del viernes anterior, y cada indicador dice
          contra qué periodo se compara.<br/>
          Generado automáticamente el {_E(informe.generado_en)}.
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


# ─────────────────────────────── Telegram ───────────────────────────────

def mensaje_telegram(informe: Informe) -> str:
    """Texto plano. Sin Markdown a propósito.

    Los nombres de los tableros traen guiones bajos, paréntesis y porcentajes,
    y con `parse_mode` activo Telegram devuelve 400 por un asterisco sin pareja
    en vez de mandar el mensaje. El informe legible va en el PDF adjunto.
    """
    lineas = [
        "INFORME SEMANAL DE DIRECCIÓN DE ENERGÍA",
        informe.fecha,
        "",
        _resumen_movimiento(informe),
    ]

    for seccion in informe.secciones:
        lineas.append("")
        if seccion.error:
            lineas.append(f"— {seccion.titulo}: sin datos esta semana.")
            continue
        lineas.append(f"— {seccion.titulo.upper()}")
        for kpi in seccion.kpis:
            delta, _ = _texto_delta(kpi)
            valor = formatear(kpi.valor, kpi.formato, kpi.unidad)
            lineas.append(f"   • {kpi.etiqueta}: {valor}  ({delta})")

    lineas += [
        "",
        "El detalle completo con gráficas va en el PDF adjunto.",
        PORTAL_URL,
    ]

    texto = "\n".join(lineas)
    if len(texto) <= LIMITE_TELEGRAM:
        return texto

    corte = texto[:LIMITE_TELEGRAM].rsplit("\n", 1)[0]
    return f"{corte}\n\n(…) El informe completo va en el PDF adjunto.\n{PORTAL_URL}"
