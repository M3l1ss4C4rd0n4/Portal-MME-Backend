"""
Servicio de dominio — Balance Oferta-Demanda del SIN.

Construido para evaluar con datos la hipótesis (prensa/expertos) de que la
crisis de suministro fue causada por retrasos en proyectos del Plan de
Expansión de la UPME. Combina series oficiales de XM
(sector_energetico.metrics, vía BalanceOfertaDemandaRepository) con datos
curados de proyectos UPME (sector_energetico.upme_proyectos_expansion, vía
UpmeProyectosRepository).

GOBERNANZA DE DATOS (ver core/umbrales_oficiales.py y memoria de proyecto
"solo datos oficiales / no mezclar criterio propio con clasificación
oficial"): el "Margen de Reserva Operativo" calculado aquí NO es un índice
regulado por la CREG — es Disponibilidad Declarada (MW, dato oficial XM)
comparada contra un equivalente de potencia promedio de la Demanda Real
(dato oficial XM). Es distinto de los índices oficiales NE/HSIN/PBP de
core/umbrales_oficiales.py y nunca debe presentarse como si fuera uno de
ellos. Todo consumidor de este servicio debe mostrar la nota metodológica
que se incluye en cada respuesta.
"""

import warnings
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from infrastructure.database.repositories.balance_oferta_demanda_repository import (
    FECHA_INICIO_DEMANDA_CONFIABLE,
    FECHA_INICIO_DISPO_CONFIABLE,
    FECHA_INICIO_ENFICC_CONFIABLE,
    FECHA_INICIO_GENERACION,
    BalanceOfertaDemandaRepository,
)
from infrastructure.database.repositories.upme_proyectos_repository import (
    UpmeProyectosRepository,
)

NOTA_METODOLOGICA = (
    "Margen de Reserva Operativo: cálculo propio del Portal con datos oficiales "
    "XM (Disponibilidad Declarada vs. equivalente de potencia promedio de la "
    "Demanda Real). NO es un índice regulado por la CREG — no debe confundirse "
    "con los índices oficiales NE/HSIN/PBP/Condición del Sistema (Estatuto CREG "
    "026/2014), que se calculan por separado en core/umbrales_oficiales.py."
)

NOTA_REGULATORIA = (
    "Margen Regulatorio (ENFICC vs. OEF): a diferencia del Margen de Reserva "
    "Operativo de arriba, ESTE SÍ es el mecanismo oficial de adecuación de "
    "oferta diseñado por la CREG — Cargo por Confiabilidad, Resolución CREG "
    "071/2006 — que compara la Energía Firme certificada de cada planta "
    "(ENFICC) contra la Obligación de Energía Firme (OEF, que escala con la "
    "demanda proyectada). Datos oficiales XM, sin transformación propia más "
    "allá de la agregación nacional."
)

HORAS_DIA = 24
GWH_A_MWH = 1000


class BalanceOfertaDemandaService:
    def __init__(
        self,
        balance_repo: Optional[BalanceOfertaDemandaRepository] = None,
        upme_repo: Optional[UpmeProyectosRepository] = None,
    ):
        self.balance_repo = balance_repo or BalanceOfertaDemandaRepository()
        self.upme_repo = upme_repo or UpmeProyectosRepository()

    # ── Cálculos puros (testeables sin BD) ──────────────────────────────

    @staticmethod
    def demanda_gwh_a_mw_promedio(demanda_gwh_dia: float) -> float:
        """Equivalente de potencia promedio de una demanda diaria de energía."""
        return (demanda_gwh_dia * GWH_A_MWH) / HORAS_DIA

    @staticmethod
    def calcular_margen(oferta_mw: Optional[float], demanda_gwh_dia: Optional[float]) -> Dict[str, Optional[float]]:
        """Margen de reserva operativo para un punto (oferta MW, demanda GWh/día)."""
        if oferta_mw is None or demanda_gwh_dia is None or demanda_gwh_dia == 0:
            return {"demandaMwPromedio": None, "margenMw": None, "margenPct": None}
        demanda_mw = BalanceOfertaDemandaService.demanda_gwh_a_mw_promedio(demanda_gwh_dia)
        if demanda_mw == 0:
            return {"demandaMwPromedio": 0.0, "margenMw": None, "margenPct": None}
        margen_mw = oferta_mw - demanda_mw
        return {
            "demandaMwPromedio": round(demanda_mw, 2),
            "margenMw": round(margen_mw, 2),
            "margenPct": round((margen_mw / demanda_mw) * 100, 2),
        }

    @staticmethod
    def calcular_margen_regulatorio(enficc_gwh: Optional[float], oef_gwh: Optional[float]) -> Dict[str, Optional[float]]:
        """Margen del mecanismo oficial CREG: (ENFICC - OEF) / OEF, en %."""
        if enficc_gwh is None or oef_gwh is None or oef_gwh == 0:
            return {"margenRegulatorioGwh": None, "margenRegulatorioPct": None}
        margen_gwh = enficc_gwh - oef_gwh
        return {
            "margenRegulatorioGwh": round(margen_gwh, 3),
            "margenRegulatorioPct": round((margen_gwh / oef_gwh) * 100, 2),
        }

    @staticmethod
    def mw_a_energia_firme_gwh_dia(mw: float) -> float:
        """
        Convierte MW de capacidad contrafactual en un equivalente de energía
        firme GWh/día (inverso de demanda_gwh_a_mw_promedio), para poder
        sumarlo a ENFICC en el contrafactual regulatorio. Es una simplificación
        explícita: asume que toda la capacidad del proyecto se certificaría
        como energía firme (MW operando 24h), igual que el contrafactual
        operativo ya asume que toda la capacidad se vuelve oferta declarada —
        misma convención en ambos simuladores, documentada en la nota
        metodológica de simular_contrafactual().
        """
        return (mw * HORAS_DIA) / GWH_A_MWH

    @staticmethod
    def calcular_mw_extra_contrafactual(
        fecha: pd.Timestamp,
        proyectos: List[Dict[str, Any]],
    ) -> float:
        """
        MW que se sumarían a la oferta de `fecha` si los proyectos seleccionados
        hubieran entrado en operación en su fecha_entrada_planeada_original en
        vez de su fecha_entrada_real (o de seguir retrasados, nunca).
        Solo aplica si a esa fecha el proyecto real aún no había entrado.
        """
        total = 0.0
        for p in proyectos:
            f_planeada = p.get("fecha_entrada_planeada_original")
            capacidad = p.get("capacidad_mw")
            if f_planeada is None or capacidad is None:
                continue
            f_planeada_ts = pd.Timestamp(f_planeada)
            if fecha < f_planeada_ts:
                continue
            f_real = p.get("fecha_entrada_real")
            ya_entro_de_verdad = f_real is not None and fecha >= pd.Timestamp(f_real)
            if ya_entro_de_verdad:
                continue
            total += float(capacidad)
        return total

    # ── Balance histórico nacional ──────────────────────────────────────

    def get_balance_historico(self, fecha_inicio: date, fecha_fin: date) -> Dict[str, Any]:
        rows = self.balance_repo.get_serie_diaria_oferta_demanda(fecha_inicio, fecha_fin)
        serie = []
        for r in rows:
            margen = self.calcular_margen(
                float(r["oferta_declarada_mw"]) if r["oferta_declarada_mw"] is not None else None,
                float(r["demanda_real_gwh"]) if r["demanda_real_gwh"] is not None else None,
            )
            margen_reg = self.calcular_margen_regulatorio(
                float(r["enficc_gwh"]) if r["enficc_gwh"] is not None else None,
                float(r["oef_gwh"]) if r["oef_gwh"] is not None else None,
            )
            serie.append({
                "fecha": r["fecha"].isoformat(),
                "ofertaDeclaradaMw": round(float(r["oferta_declarada_mw"]), 2) if r["oferta_declarada_mw"] is not None else None,
                "demandaRealGwh": round(float(r["demanda_real_gwh"]), 2) if r["demanda_real_gwh"] is not None else None,
                "generacionRealGwh": round(float(r["generacion_real_gwh"]), 2) if r["generacion_real_gwh"] is not None else None,
                "enficcGwh": round(float(r["enficc_gwh"]), 2) if r["enficc_gwh"] is not None else None,
                "oefGwh": round(float(r["oef_gwh"]), 2) if r["oef_gwh"] is not None else None,
                **margen,
                **margen_reg,
            })

        capacidad = self.balance_repo.get_capacidad_instalada_actual_mw()

        return {
            "serie": serie,
            "capacidadInstaladaActual": {
                "fecha": capacidad["fecha"].isoformat() if capacidad else None,
                "capacidadMw": round(float(capacidad["capacidad_mw"]), 2) if capacidad and capacidad["capacidad_mw"] else None,
                "nota": (
                    "Capacidad Efectiva Neta nominal del snapshot más reciente "
                    "(no se expone como serie histórica — ver docstring de "
                    "BalanceOfertaDemandaRepository)."
                ),
            },
            "coberturaDatos": {
                "ofertaDeclaradaDesde": FECHA_INICIO_DISPO_CONFIABLE.isoformat(),
                "demandaRealDesde": FECHA_INICIO_DEMANDA_CONFIABLE.isoformat(),
                "generacionDesde": FECHA_INICIO_GENERACION.isoformat(),
                "margenRegulatorioDesde": FECHA_INICIO_ENFICC_CONFIABLE.isoformat(),
            },
            "notaMetodologica": NOTA_METODOLOGICA,
            "notaRegulatoria": NOTA_REGULATORIA,
        }

    # ── Regional: demanda no atendida por área operativa ────────────────

    def get_demanda_no_atendida_regional(self, fecha_inicio: date, fecha_fin: date) -> Dict[str, Any]:
        rows = self.balance_repo.get_demanda_no_atendida_diaria_por_area(fecha_inicio, fecha_fin)
        serie = [
            {
                "fecha": r["fecha"].isoformat(),
                "areaOperativa": r["area_operativa"],
                "noAtendidaProgramadaGwh": round(float(r["no_atendida_programada_gwh"]), 4),
                "noAtendidaNoProgramadaGwh": round(float(r["no_atendida_no_programada_gwh"]), 4),
            }
            for r in rows
        ]
        return {
            "serie": serie,
            "nota": (
                "Único desagregado regional disponible hoy con datos oficiales XM: "
                "demanda no atendida por área operativa. La generación, disponibilidad "
                "y capacidad instalada NO tienen desagregación geográfica en la base de "
                "datos actual (el atributo región de las plantas no está poblado), por lo "
                "que no es posible calcular un margen de reserva por región."
            ),
        }

    # ── Proyectos UPME ───────────────────────────────────────────────────

    def get_proyectos_upme(
        self,
        tipo: Optional[str] = None,
        tecnologia: Optional[str] = None,
        estado: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows = self.upme_repo.get_proyectos(tipo, tecnologia, estado)
        hoy = pd.Timestamp(date.today())
        proyectos = []
        for r in rows:
            f_planeada = r.get("fecha_entrada_planeada_original")
            f_real = r.get("fecha_entrada_real")
            dias_retraso = None
            if f_planeada is not None:
                fecha_referencia = pd.Timestamp(f_real) if f_real is not None else hoy
                dias_retraso = max(0, (fecha_referencia - pd.Timestamp(f_planeada)).days)
            proyectos.append({
                "id": r["id"],
                "nombreProyecto": r["nombre_proyecto"],
                "tipo": r["tipo"],
                "tecnologia": r["tecnologia"],
                "capacidadMw": float(r["capacidad_mw"]) if r["capacidad_mw"] is not None else None,
                "departamento": r["departamento"],
                "areaOperativa": r["area_operativa"],
                "fechaEntradaPlaneadaOriginal": f_planeada.isoformat() if f_planeada else None,
                "fechaEntradaPlaneadaVigente": r["fecha_entrada_planeada_vigente"].isoformat()
                    if r["fecha_entrada_planeada_vigente"] else None,
                "fechaEntradaReal": f_real.isoformat() if f_real else None,
                "estado": r["estado"],
                "diasRetraso": dias_retraso,
                "fuente": r["fuente"],
                "notas": r["notas"],
            })
        return proyectos

    # ── Simulación contrafactual ─────────────────────────────────────────

    def simular_contrafactual(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        proyecto_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Recalcula el margen de reserva histórico — el operativo Y el
        regulatorio (ENFICC vs. OEF) — asumiendo que los proyectos UPME
        seleccionados (o, si no se especifican, todos los que tienen
        fecha_entrada_planeada_original y capacidad_mw) hubieran entrado en
        operación en su fecha originalmente planeada. El lado regulatorio
        usa mw_a_energia_firme_gwh_dia() para sumar la capacidad extra a
        ENFICC — ver esa función para la simplificación asumida.
        """
        ids_set = set(proyecto_ids) if proyecto_ids is not None else None
        todos = self.upme_repo.get_proyectos()
        seleccionados = [
            p for p in todos
            if p.get("fecha_entrada_planeada_original") is not None
            and p.get("capacidad_mw") is not None
            and (ids_set is None or p["id"] in ids_set)
        ]

        balance = self.get_balance_historico(fecha_inicio, fecha_fin)
        serie_contrafactual = []
        for punto in balance["serie"]:
            fecha_ts = pd.Timestamp(punto["fecha"])
            mw_extra = self.calcular_mw_extra_contrafactual(fecha_ts, seleccionados)

            oferta_real = punto["ofertaDeclaradaMw"]
            oferta_cf = (oferta_real or 0.0) + mw_extra if oferta_real is not None else None
            margen_cf = self.calcular_margen(oferta_cf, punto["demandaRealGwh"])

            enficc_real = punto["enficcGwh"]
            enficc_extra_gwh = self.mw_a_energia_firme_gwh_dia(mw_extra)
            enficc_cf = (enficc_real or 0.0) + enficc_extra_gwh if enficc_real is not None else None
            margen_reg_cf = self.calcular_margen_regulatorio(enficc_cf, punto["oefGwh"])

            serie_contrafactual.append({
                "fecha": punto["fecha"],
                "ofertaRealMw": oferta_real,
                "ofertaContrafactualMw": round(oferta_cf, 2) if oferta_cf is not None else None,
                "mwExtraProyectosRetrasados": round(mw_extra, 2),
                "margenRealPct": punto["margenPct"],
                "margenContrafactualPct": margen_cf["margenPct"],
                "diferenciaPuntosPorcentuales": (
                    round(margen_cf["margenPct"] - punto["margenPct"], 2)
                    if margen_cf["margenPct"] is not None and punto["margenPct"] is not None
                    else None
                ),
                "margenRegulatorioRealPct": punto["margenRegulatorioPct"],
                "margenRegulatorioContrafactualPct": margen_reg_cf["margenRegulatorioPct"],
                "diferenciaPuntosPorcentualesRegulatorio": (
                    round(margen_reg_cf["margenRegulatorioPct"] - punto["margenRegulatorioPct"], 2)
                    if margen_reg_cf["margenRegulatorioPct"] is not None and punto["margenRegulatorioPct"] is not None
                    else None
                ),
            })

        return {
            "serie": serie_contrafactual,
            "proyectosIncluidos": [
                {"id": p["id"], "nombreProyecto": p["nombre_proyecto"], "capacidadMw": float(p["capacidad_mw"])}
                for p in seleccionados
            ],
            "notaMetodologica": (
                NOTA_METODOLOGICA + " Simulación contrafactual: análisis exploratorio propio — "
                "asume que el proyecto entra íntegramente en la fecha originalmente planeada, sin "
                "modelar restricciones de red, hidrología ni otros factores. Correlación no implica "
                "causalidad; esta simulación cuantifica un escenario hipotético, no un pronóstico. "
                "El lado regulatorio (ENFICC vs. OEF) asume además que toda la capacidad extra se "
                "certificaría como energía firme — una simplificación adicional sobre el mecanismo "
                "real del Cargo por Confiabilidad."
            ),
        }

    # ── Correlación retraso UPME vs. déficit ─────────────────────────────

    def get_correlacion_retraso_deficit(self, fecha_inicio: date, fecha_fin: date) -> Dict[str, Any]:
        """
        Correlaciona MW retrasados acumulados contra DOS márgenes distintos:
        el operativo (cálculo propio, DispoDeclarada vs. Demanda) y el
        regulatorio oficial (ENFICC vs. OEF, Cargo por Confiabilidad). Se
        reportan ambos coeficientes por separado — nunca deben promediarse
        ni mezclarse, son mediciones de cosas distintas (ver notas del
        módulo y NOTA_REGULATORIA).
        """
        balance = self.get_balance_historico(fecha_inicio, fecha_fin)
        df_balance = pd.DataFrame(balance["serie"])
        resultado_vacio = {
            "serieMensual": [],
            "coeficienteCorrelacion": None,
            "coeficienteCorrelacionRegulatorio": None,
            "nProyectos": 0,
            "notaMetodologica": NOTA_METODOLOGICA,
            "notaRegulatoria": NOTA_REGULATORIA,
            "advertencia": "Correlación no implica causalidad — panel exploratorio, no una prueba causal.",
        }
        if df_balance.empty or df_balance["margenPct"].dropna().empty:
            return resultado_vacio

        df_balance["fecha"] = pd.to_datetime(df_balance["fecha"])
        df_balance = df_balance.set_index("fecha")
        margen_mensual = df_balance["margenPct"].resample("MS").mean()
        margen_reg_mensual = df_balance["margenRegulatorioPct"].resample("MS").mean()

        mw_retrasado_rows = self.upme_repo.get_serie_mensual_mw_retrasado(fecha_inicio, fecha_fin)
        if not mw_retrasado_rows:
            return resultado_vacio
        df_retraso = pd.DataFrame(mw_retrasado_rows)
        df_retraso["mes"] = pd.to_datetime(df_retraso["mes"])
        # psycopg2 devuelve NUMERIC como Decimal — coerción explícita a float
        # antes de operar con pandas/numpy (Decimal no es serializable a JSON
        # directamente y numpy no opera bien mezclado con Decimal).
        df_retraso["mw_retrasado_acumulado"] = df_retraso["mw_retrasado_acumulado"].astype(float)
        df_retraso = df_retraso.set_index("mes")

        panel = pd.concat(
            [
                margen_mensual.rename("margen_pct"),
                margen_reg_mensual.rename("margen_reg_pct"),
                df_retraso["mw_retrasado_acumulado"],
            ],
            axis=1,
        )
        # El margen regulatorio (ENFICC/OEF) puede faltar antes de 2007 aunque
        # el operativo sí exista — no descartar filas solo por eso.
        panel_operativo = panel[["margen_pct", "mw_retrasado_acumulado"]].dropna()
        panel_regulatorio = panel[["margen_reg_pct", "mw_retrasado_acumulado"]].dropna()

        if len(panel_operativo) < 3:
            resultado_vacio["serieMensual"] = [
                {
                    "mes": idx.date().isoformat(),
                    "margenPct": round(row.margen_pct, 2) if pd.notna(row.margen_pct) else None,
                    "margenRegulatorioPct": round(row.margen_reg_pct, 2) if pd.notna(row.margen_reg_pct) else None,
                    "mwRetrasadoAcumulado": round(row.mw_retrasado_acumulado, 2),
                }
                for idx, row in panel.dropna(subset=["mw_retrasado_acumulado"]).iterrows()
            ]
            resultado_vacio["advertencia"] += " Muy pocos meses con datos completos para un coeficiente confiable."
            return resultado_vacio

        with warnings.catch_warnings():
            # corr() sobre una serie constante (p. ej. 0 MW retrasado en todo el
            # rango) produce std=0 → división por cero → NaN, un resultado
            # matemáticamente correcto (correlación indefinida), no un error.
            warnings.simplefilter("ignore", category=RuntimeWarning)
            coeficiente = panel_operativo["margen_pct"].corr(panel_operativo["mw_retrasado_acumulado"])
            coeficiente_reg = (
                panel_regulatorio["margen_reg_pct"].corr(panel_regulatorio["mw_retrasado_acumulado"])
                if len(panel_regulatorio) >= 3 else float("nan")
            )

        panel_export = panel.dropna(subset=["mw_retrasado_acumulado"])
        return {
            "serieMensual": [
                {
                    "mes": idx.date().isoformat(),
                    "margenPct": round(row.margen_pct, 2) if pd.notna(row.margen_pct) else None,
                    "margenRegulatorioPct": round(row.margen_reg_pct, 2) if pd.notna(row.margen_reg_pct) else None,
                    "mwRetrasadoAcumulado": round(row.mw_retrasado_acumulado, 2),
                }
                for idx, row in panel_export.iterrows()
            ],
            "coeficienteCorrelacion": round(float(coeficiente), 3) if pd.notna(coeficiente) else None,
            "coeficienteCorrelacionRegulatorio": round(float(coeficiente_reg), 3) if pd.notna(coeficiente_reg) else None,
            "nProyectos": len({p.get("id") for p in self.upme_repo.get_proyectos()}),
            "notaMetodologica": NOTA_METODOLOGICA,
            "notaRegulatoria": NOTA_REGULATORIA,
            "advertencia": "Correlación no implica causalidad — panel exploratorio, no una prueba causal.",
        }
