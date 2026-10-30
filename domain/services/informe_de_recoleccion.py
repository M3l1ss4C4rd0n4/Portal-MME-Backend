"""Recolección de los datos del Informe Semanal de Dirección de Energía.

Regla de oro: este módulo NO consulta la base de datos ni escribe SQL. Reutiliza
los mismos endpoints que ya alimentan cada tablero del portal, vía los helpers
`_fetch` / `_fetch_nextjs` de `portal_report_service`. Si un número sale distinto
aquí y en el tablero, es un bug del endpoint, no de dos fórmulas que divergieron.

Las secciones están UNIFICADAS respecto al menú del portal: los cuatro tableros
de Subsidios devuelven literalmente los mismos totales (verificado 2026-10-28:
valor comprometido, valor pagado, saldo pendiente, % ejecución y nº de
resoluciones coinciden dígito a dígito entre `pagos-detalle` y
`empresas-detalle`, y el "déficit acumulado" del tablero histórico ES el saldo
pendiente). Repetirlos en cuatro bloques sería ruido, no información.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from domain.services.informe_de_modelo import Kpi, Punto, Seccion, Serie

logger = logging.getLogger(__name__)

# Los porcentajes del endpoint de presupuesto vienen como fracción (0.70) y no
# como porcentaje (70.0). Es la misma trampa que ya mordió en el avance físico
# de contratos OR, así que se escala explícitamente y se deja dicho.
_FRACCION_A_PCT = 100.0


def _num(valor: Any) -> float | None:
    """Convierte a float tolerando None, cadenas y vacíos. Nunca lanza."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _div(numerador: float | None, denominador: float | None) -> float | None:
    if numerador is None or not denominador:
        return None
    return numerador / denominador


async def _seguro(
    clave: str,
    titulo: str,
    constructor: Callable[[], Awaitable[Seccion]],
) -> Seccion:
    """Una sección caída no puede tumbar el informe completo."""
    try:
        return await constructor()
    except Exception as exc:  # noqa: BLE001 — se reporta, no se traga
        logger.error("[INFORME DE] Sección '%s' falló: %s", clave, exc, exc_info=True)
        return Seccion(
            clave=clave,
            titulo=titulo,
            subtitulo="",
            corte="",
            kpis=(),
            error=f"{type(exc).__name__}: {exc}",
        )


# ── 1. Presupuesto ────────────────────────────────────────────────────────────

async def _presupuesto() -> Seccion:
    from domain.services.portal_report_service import _fetch

    data = await _fetch("/v1/presupuesto/resumen")
    tot = data.get("totales") or {}

    apropiacion = _num(tot.get("apropiacion"))
    comprometido = _num(tot.get("comprometido"))
    obligado = _num(tot.get("obligados"))
    disponible = _num(tot.get("disponible"))

    pct_comp = _num(tot.get("pct_comprometido"))
    pct_obl = _num(tot.get("pct_obligado"))
    pct_comp = pct_comp * _FRACCION_A_PCT if pct_comp is not None else None
    pct_obl = pct_obl * _FRACCION_A_PCT if pct_obl is not None else None
    pct_disp = _div(disponible, apropiacion)
    pct_disp = pct_disp * _FRACCION_A_PCT if pct_disp is not None else None

    n_proyectos = len(data.get("proyectos") or [])

    lectura = ""
    if pct_comp is not None and pct_obl is not None and disponible is not None:
        brecha = pct_comp - pct_obl
        lectura = (
            f"Del total apropiado hay {_pct(pct_comp)} comprometido y {_pct(pct_obl)} "
            f"obligado: {_miles(brecha, 1)} puntos ya comprometidos que aún no se legalizan. "
            f"Quedan {_cop_corto(disponible)} sin comprometer."
        )

    return Seccion(
        clave="presupuesto",
        titulo="Presupuesto",
        subtitulo="Ejecución presupuestal · Dirección de Energía",
        corte=str(data.get("ultima_actualizacion") or ""),
        tableros=("Presupuesto",),
        series=(
            Serie(
                clave="reparto",
                titulo="Reparto de la apropiación",
                tipo="apilada",
                rampa="azul",
                puntos=(
                    Punto("Obligado", obligado, "paso-0", _cop_corto(obligado)),
                    Punto("Comprometido sin obligar",
                          (comprometido - obligado) if (comprometido is not None and obligado is not None) else None,
                          "paso-2",
                          _cop_corto((comprometido - obligado) if (comprometido is not None and obligado is not None) else None)),
                    Punto("Sin comprometer", disponible, "neutro", _cop_corto(disponible)),
                ),
                nota="Los tres sumados son la apropiación total.",
            ),
            Serie(
                clave="avance",
                titulo="Avance de la ejecución",
                tipo="medidores",
                rampa="azul",
                puntos=(
                    Punto("Comprometido", pct_comp, "paso-3", _pct(pct_comp)),
                    Punto("Obligado", pct_obl, "paso-1", _pct(pct_obl)),
                ),
            ),
        ),
        kpis=(
            Kpi("apropiacion", "Apropiación DEE", apropiacion, "cop_corto",
                detalle=f"{n_proyectos} proyectos"),
            Kpi("pct_comprometido", "Comprometido", pct_comp, "pct",
                sentido="mas_es_mejor",
                detalle=_cop_corto(comprometido) if comprometido else ""),
            Kpi("pct_obligado", "Obligado", pct_obl, "pct",
                sentido="mas_es_mejor",
                detalle=_cop_corto(obligado) if obligado else ""),
            Kpi("disponible", "Sin comprometer", disponible, "cop_corto",
                sentido="menos_es_mejor",
                detalle=f"{_pct(pct_disp)} de la apropiación" if pct_disp is not None else ""),
        ),
        lectura=lectura,
    )


# ── 2. Supervisión ────────────────────────────────────────────────────────────

async def _supervision() -> Seccion:
    from domain.services.portal_report_service import _fetch

    data = await _fetch("/v1/supervision/dashboard")
    fin = data.get("financiero") or {}
    usu = data.get("usuarios") or {}

    avance_fisico = _num(data.get("avanceFisico"))
    avance_fin = _num(data.get("avanceFinanciero"))
    avance_gen = _num(data.get("avanceContrato"))

    lectura = ""
    avances = [
        ("físico", avance_fisico),
        ("financiero", avance_fin),
        ("contractual", avance_gen),
    ]
    medidos = [(n, v) for n, v in avances if v is not None]
    if len(medidos) >= 2:
        menor = min(medidos, key=lambda p: p[1])
        mayor = max(medidos, key=lambda p: p[1])
        if mayor[1] - menor[1] >= 1:
            lectura = (
                f"El avance {menor[0]} ({_pct(menor[1])}) va por detrás del "
                f"{mayor[0]} ({_pct(mayor[1])}): una brecha de "
                f"{_miles(mayor[1] - menor[1], 1)} puntos."
            )

    return Seccion(
        clave="supervision",
        titulo="Supervisión",
        subtitulo="Portafolio de contratos y proyectos",
        corte=str(data.get("ultima_actualizacion") or ""),
        tableros=("Supervisión",),
        series=(
            Serie(
                clave="avances",
                titulo="Avance del portafolio",
                tipo="medidores",
                rampa="azul",
                puntos=(
                    Punto("Avance físico", avance_fisico, "paso-3",
                          _pct(avance_fisico)),
                    Punto("Avance financiero", avance_fin, "paso-2",
                          _pct(avance_fin)),
                    Punto("Avance contractual", avance_gen, "paso-1",
                          _pct(avance_gen)),
                ),
            ),
            Serie(
                clave="ciclo",
                titulo="Contratos por etapa del ciclo",
                tipo="barras",
                rampa="azul",
                puntos=(
                    Punto("En ejecución", _num(data.get("enEjecucion")), "paso-3",
                          _miles(_num(data.get("enEjecucion")))),
                    Punto("En AOM", _num(data.get("enAOM")), "paso-2",
                          _miles(_num(data.get("enAOM")))),
                    Punto("En liquidación", _num(data.get("enLiquidacion")), "paso-1",
                          _miles(_num(data.get("enLiquidacion")))),
                    Punto("Liquidados", _num(data.get("liquidados")), "paso-0",
                          _miles(_num(data.get("liquidados")))),
                    Punto("Pérdida de competencia", _num(data.get("perdidaCompetencia")),
                          "critico", _miles(_num(data.get("perdidaCompetencia"))),
                          nota="Contratos que salieron del ciclo sin liquidar"),
                ),
                nota="Etapas ordenadas del ciclo. La pérdida de competencia no es una etapa: es una salida.",
            ),
        ),
        kpis=(
            Kpi("contratos", "Contratos", _num(data.get("nContratos")), "num",
                detalle=f"{_num(data.get('nProyectos')) or 0:,.0f} proyectos".replace(",", ".")),
            Kpi("en_ejecucion", "En ejecución", _num(data.get("enEjecucion")), "num",
                detalle=f"{_num(data.get('enAOM')) or 0:,.0f} en AOM".replace(",", ".")),
            Kpi("en_liquidacion", "En liquidación", _num(data.get("enLiquidacion")), "num",
                detalle=f"{_num(data.get('liquidados')) or 0:,.0f} ya liquidados".replace(",", ".")),
            Kpi("valor_desembolsado", "Desembolsado", _num(fin.get("valorDesembolsado")),
                "cop_corto", sentido="mas_es_mejor",
                detalle=f"{_pct(_num(fin.get('pctDesembolsado')))} del portafolio"),
            Kpi("valor_portafolio", "Valor del portafolio", _num(fin.get("valorProyecto")),
                "cop_corto",
                detalle=f"{_cop_corto(_num(fin.get('valorPorDesembolsar')))} por desembolsar"),
            Kpi("usuarios_finales", "Usuarios finales", _num(usu.get("finales")), "num",
                sentido="mas_es_mejor"),
        ),
        lectura=lectura,
    )


# ── 3. Subsidios (unifica los 4 tableros del menú) ────────────────────────────

async def _subsidios() -> Seccion:
    from domain.services.portal_report_service import _fetch, _fetch_nextjs

    pagos, empresas, validaciones = await asyncio.gather(
        _fetch_nextjs("/api/subsidios/pagos-detalle"),
        _fetch_nextjs("/api/subsidios/empresas-detalle"),
        _fetch("/v1/subsidios/validaciones"),
        return_exceptions=True,
    )
    pagos = pagos if isinstance(pagos, dict) else {}
    empresas = empresas if isinstance(empresas, dict) else {}
    validaciones = validaciones if isinstance(validaciones, dict) else {}

    kp = pagos.get("kpis") or {}
    ke = empresas.get("kpis") or {}

    comprometido = _num(kp.get("valorAsignado")) or _num(ke.get("valorResolucion"))
    pagado = _num(kp.get("valorPagado")) or _num(ke.get("valorPagado"))
    pendiente = _num(kp.get("valorPendiente")) or _num(ke.get("saldoPendiente"))
    pct_pagado = _num(kp.get("pctPagado")) or _num(ke.get("pctEjecucion"))

    resumen_val = validaciones.get("resumen") or {}
    total_cuentas = sum(_num(v) or 0 for v in resumen_val.values()) or None

    lectura = ""
    if pendiente is not None and pct_pagado is not None:
        lectura = (
            f"La ejecución va en {_pct(pct_pagado, 2)}. El saldo pendiente de "
            f"{_cop_corto(pendiente)} es el mismo número que el tablero histórico "
            f"reporta como déficit acumulado: son el mismo dato visto desde dos tableros."
        )

    return Seccion(
        clave="subsidios",
        titulo="Subsidios",
        subtitulo="FSSRI / FOES · déficit, pagos, validaciones y empresas",
        corte=str(pagos.get("fechaCorte") or empresas.get("corte") or ""),
        tableros=("Déficit histórico", "Detalle de pagos",
                  "Tablero de validaciones", "Detalle Empresas"),
        series=(
            Serie(
                clave="ejecucion",
                titulo="Ejecución de pagos",
                tipo="medidores",
                rampa="oro",
                puntos=(
                    Punto("Ejecución", pct_pagado, "paso-3",
                          _pct(pct_pagado, 2)),
                ),
            ),
            Serie(
                clave="validaciones",
                titulo="Cuentas por estado de validación",
                tipo="barras",
                rampa="oro",
                puntos=(
                    Punto("Validación final (VF)", _num(resumen_val.get("e. VF")), "paso-3",
                          _miles(_num(resumen_val.get("e. VF")))),
                    Punto("Validación pendiente (VP)", _num(resumen_val.get("d. VP")), "paso-2",
                          _miles(_num(resumen_val.get("d. VP")))),
                    Punto("Validación inicial (VI)", _num(resumen_val.get("b. VI")), "paso-1",
                          _miles(_num(resumen_val.get("b. VI")))),
                    Punto("VI saldo pendiente", _num(resumen_val.get("c. VI SP")), "paso-0",
                          _miles(_num(resumen_val.get("c. VI SP")))),
                    Punto("Otros", _num(resumen_val.get("a. Otros")), "neutro",
                          _miles(_num(resumen_val.get("a. Otros")))),
                ),
                nota=(f"{_miles(total_cuentas)} cuentas en total, en estados "
                      "ordenados del trámite de más avanzado a menos."),
            ),
        ),
        kpis=(
            Kpi("valor_comprometido", "Comprometido", comprometido, "cop_corto"),
            Kpi("valor_pagado", "Pagado", pagado, "cop_corto", sentido="mas_es_mejor"),
            Kpi("pct_ejecucion", "Ejecución", pct_pagado, "pct", sentido="mas_es_mejor"),
            Kpi("saldo_pendiente", "Saldo pendiente", pendiente, "cop_corto",
                sentido="menos_es_mejor", detalle="= déficit acumulado"),
            Kpi("empresas", "Empresas", _num(ke.get("totalEmpresas")), "num",
                detalle=f"{_num(validaciones.get('totalPrestadores')) or 0:,.0f} prestadores".replace(",", ".")),
            Kpi("resoluciones_pendientes", "Resol. pendientes",
                _num(kp.get("resolucionesPendientes")), "num",
                sentido="menos_es_mejor",
                detalle=f"de {_num(kp.get('totalResoluciones')) or 0:,.0f}".replace(",", ".")),
        ),
        lectura=lectura,
    )


# ── 4. Comunidades Energéticas (CE_Implementadas + CE_Fenoge) ─────────────────

async def _comunidades() -> Seccion:
    from domain.services.portal_report_service import _fetch

    ce, fenoge = await asyncio.gather(
        _fetch("/v1/comunidades/mapa"),
        _fetch("/v1/fenoge/mapa"),
        return_exceptions=True,
    )
    ce = ce if isinstance(ce, dict) else {}
    fenoge = fenoge if isinstance(fenoge, dict) else {}

    implementadas = _num(ce.get("implementadas"))
    stats = ce.get("statsFechas") or {}
    en_operacion = _num(stats.get("con_operacion"))
    capacidad = _num(ce.get("capacidadKwp"))
    ces_fenoge = _num(fenoge.get("totalCes"))
    kwp_fenoge = _num(fenoge.get("totalKwp"))

    # El menú del portal nombra el tablero "CE_Fenoge 1.0, 1.1": el reparto
    # entre las dos fases es el dato propio de ese tablero, y llega repartido
    # por departamento, así que hay que agregarlo.
    por_fase: dict[str, float] = {}
    for fila in fenoge.get("detalleFase") or []:
        bruto = str(fila.get("faseLabel") or "").strip()
        # La fuente trae un tercer valor, "CE", que no es ninguna de las dos
        # fases que nombra el tablero. Se muestra tal cual pero explicado, en
        # vez de dejar una sigla suelta o, peor, repartirlo entre 1.0 y 1.1.
        etiqueta = "CE sin fase 1.0 ni 1.1" if bruto == "CE" else (bruto or "Sin fase")
        por_fase[etiqueta] = por_fase.get(etiqueta, 0) + (_num(fila.get("count")) or 0)

    lectura = ""
    if implementadas and en_operacion is not None:
        pct_op = _div(en_operacion, implementadas)
        lectura = (
            f"De {_miles(implementadas)} comunidades implementadas, solo "
            f"{_miles(en_operacion)} están en operación "
            f"({_pct(pct_op * 100 if pct_op else 0, 0)}): el resto está registrada "
            f"pero todavía no entrega energía."
        )

    return Seccion(
        clave="comunidades",
        titulo="Comunidades Energéticas",
        titulo_corto="Comunidades",
        subtitulo="Comunidades implementadas y programa Fenoge",
        corte=str(ce.get("ultima_actualizacion") or ""),
        tableros=("CE_Implementadas", "CE_Fenoge 1.0, 1.1"),
        series=(
            Serie(
                clave="estado",
                titulo="Comunidades por estado",
                tipo="barras",
                rampa="azul",
                puntos=tuple(
                    Punto(
                        str(fila.get("estado") or "Sin estado").capitalize(),
                        _num(fila.get("count")),
                        "paso-3" if str(fila.get("estado")).upper().startswith("OPERA") else "paso-1",
                        _miles(_num(fila.get("count"))),
                    )
                    for fila in (ce.get("porEstado") or [])
                ),
                nota="Solo las que están en operación entregan energía hoy.",
            ),
            Serie(
                clave="fenoge_fase",
                titulo="Fenoge — comunidades por fase",
                tipo="barras",
                rampa="oro",
                puntos=tuple(
                    Punto(etiqueta, valor,
                          "paso-3" if "1.1" in etiqueta
                          else ("neutro" if "sin fase" in etiqueta else "paso-1"),
                          _miles(valor))
                    for etiqueta, valor in sorted(por_fase.items())
                ),
                nota=(f"Fenoge aporta {_miles(kwp_fenoge)} kWp de los "
                      f"{_miles(capacidad, 1)} kWp instalados en total."),
            ),
        ),
        kpis=(
            Kpi("ces_implementadas", "CEs implementadas", implementadas, "num",
                sentido="mas_es_mejor"),
            Kpi("ces_en_operacion", "En operación", en_operacion, "num",
                sentido="mas_es_mejor",
                detalle=f"{_miles(_num(stats.get('con_registro')))} con registro"),
            Kpi("inversion", "Inversión estimada", _num(ce.get("inversionEstimada")),
                "cop_corto"),
            Kpi("capacidad_kwp", "Capacidad instalada", capacidad, "num1",
                unidad="kWp", sentido="mas_es_mejor"),
            Kpi("beneficiarios", "Beneficiarios", _num(ce.get("beneficiariosEquiv")), "num",
                sentido="mas_es_mejor",
                detalle=f"{_miles(_num(ce.get('usuariosEquiv')))} usuarios equiv."),
            Kpi("ces_fenoge", "CEs Fenoge", ces_fenoge, "num",
                detalle=f"{_cop_corto(_num(fenoge.get('totalInversion')))} invertidos"),
        ),
        lectura=lectura,
    )


# ── 5. Colombia Solar y Contratos OR (Resumen + CE_Contratos OR) ──────────────

async def _programas() -> Seccion:
    """Los dos tableros que miden EJECUCIÓN de programa, no inventario de CEs.

    Van juntos porque comparten la pregunta: cuánto de lo planeado o contratado
    se ha cumplido. Separarlos repetiría el marco; mezclarlos con las CEs
    implementadas confundiría inventario con avance.
    """
    from domain.services.portal_report_service import _fetch, _fetch_nextjs

    contratos, solar = await asyncio.gather(
        _fetch("/v1/contratos-or/dashboard"),
        _fetch_nextjs("/api/kpis"),
        return_exceptions=True,
    )
    contratos = contratos if isinstance(contratos, dict) else {}
    solar = solar.get("data", {}) if isinstance(solar, dict) else {}

    plan_u = _num(solar.get("planeado_usuarios"))
    ejec_u = _num(solar.get("ejecutado_usuarios"))
    kwp_p = _num(solar.get("kwp_planeado"))
    kwp_e = _num(solar.get("kwp_ejecutado"))
    # Se toma TAL CUAL del endpoint: es el promedio simple del % por fila que
    # publica el tablero, no ejecutado/planeado total. Recalcularla daría 1,6%
    # y contradiría la cifra oficial.
    eficiencia = _num(solar.get("eficiencia_pct"))

    pendiente_u = (plan_u - ejec_u) if (plan_u is not None and ejec_u is not None) else None

    av_fis = _num(contratos.get("avanceFisico"))
    av_fin = _num(contratos.get("avanceFinanciero"))
    av_doc = _num(contratos.get("avanceGeneral"))

    lectura = ""
    medidos = [(n, v) for n, v in
               (("físico", av_fis), ("financiero", av_fin), ("documental", av_doc))
               if v is not None]
    if len(medidos) >= 2:
        menor = min(medidos, key=lambda par: par[1])
        mayor = max(medidos, key=lambda par: par[1])
        lectura = (
            f"En los contratos OR el avance {menor[0]} ({_pct(menor[1])}) va muy por "
            f"detrás del {mayor[0]} ({_pct(mayor[1])}): {_miles(mayor[1] - menor[1], 1)} "
            f"puntos de brecha que pueden retrasar el cierre."
        )

    return Seccion(
        clave="programas",
        titulo="Colombia Solar y Contratos OR",
        titulo_corto="Colombia Solar · OR",
        subtitulo="Avance de los programas frente a lo planeado y lo contratado",
        corte=str(contratos.get("ultima_actualizacion") or ""),
        tableros=("Resumen", "CE_Contratos OR"),
        series=(
            Serie(
                clave="avances",
                titulo="Avance de los programas",
                tipo="medidores",
                rampa="azul",
                puntos=(
                    Punto("Eficiencia Solar", eficiencia, "paso-3", _pct(eficiencia, 2)),
                    Punto("OR · físico", av_fis, "paso-2", _pct(av_fis)),
                    Punto("OR · financiero", av_fin, "paso-1", _pct(av_fin)),
                    Punto("OR · documental", av_doc, "paso-0", _pct(av_doc)),
                ),
                nota=("La eficiencia de Colombia Solar es el promedio simple del % de "
                      "avance por fila, tal como lo publica el tablero."),
            ),
            Serie(
                clave="usuarios_solar",
                titulo="Usuarios de Colombia Solar",
                tipo="apilada",
                rampa="azul",
                puntos=(
                    Punto("Ejecutados", ejec_u, "paso-3", _miles(ejec_u)),
                    Punto("Pendientes", pendiente_u, "neutro", _miles(pendiente_u)),
                ),
                nota=f"Los dos sumados son los {_miles(plan_u)} usuarios planeados.",
            ),
        ),
        kpis=(
            Kpi("solar_usuarios_ejec", "Usuarios ejecutados", ejec_u, "num",
                sentido="mas_es_mejor",
                detalle=f"de {_miles(plan_u)} planeados"),
            Kpi("solar_kwp_ejec", "kWp ejecutados", kwp_e, "num1", unidad="kWp",
                sentido="mas_es_mejor",
                detalle=f"de {_miles(kwp_p, 1)} planeados"),
            Kpi("or_contratos", "Contratos OR", _num(contratos.get("nContratos")), "num"),
            Kpi("or_ces", "CEs contratadas", _num(contratos.get("cesTotal")), "num",
                detalle=f"{_miles(_num(contratos.get('usuariosTotal')))} usuarios"),
            Kpi("or_potencia", "Potencia contratada", _num(contratos.get("potenciaMwpTotal")),
                "num1", unidad="MWp"),
            Kpi("or_valor", "Valor contratado", _num(contratos.get("valorTotal")), "cop_corto",
                detalle=f"{_pct(_num(contratos.get('pctPagosRealizados')))} pagado"),
        ),
        lectura=lectura,
    )


def _miles(valor: float | None, decimales: int = 0) -> str:
    """Entero con punto como separador de miles, al estilo colombiano."""
    if valor is None:
        return "N/D"
    return f"{valor:,.{decimales}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _pct(valor: float | None, decimales: int = 1) -> str:
    """Porcentaje con coma decimal. Todo el informe usa una sola convención:
    mezclar 70,8% en la tarjeta con 70.8% en el medidor se lee como un error."""
    if valor is None:
        return "N/D"
    return _miles(valor, decimales) + "%"


def _cop_corto(valor: float | None) -> str:
    """Formato compacto en pesos para las frases de lectura y los detalles.

    El `.replace(",", ".")` ingenuo que había antes convertía el separador de
    miles en punto pero dejaba el decimal también en punto ("$5.10 billones"),
    que choca con el "5,10" de las tarjetas. _miles hace la permuta completa.
    """
    if valor is None:
        return "N/D"
    absoluto = abs(valor)
    if absoluto >= 1e12:
        return f"${_miles(valor / 1e12, 2)} billones"
    if absoluto >= 1e9:
        return f"${_miles(valor / 1e9, 1)} mil millones"
    if absoluto >= 1e6:
        return f"${_miles(valor / 1e6, 0)} millones"
    return f"${_miles(valor, 0)}"


async def recolectar_secciones() -> tuple[Seccion, ...]:
    """Las 4 secciones en paralelo. Una caída no tumba a las demás."""
    return tuple(
        await asyncio.gather(
            _seguro("presupuesto", "Presupuesto", _presupuesto),
            _seguro("supervision", "Supervisión", _supervision),
            _seguro("subsidios", "Subsidios", _subsidios),
            _seguro("comunidades", "Comunidades Energéticas", _comunidades),
            _seguro("programas", "Colombia Solar y Contratos OR", _programas),
        )
    )
