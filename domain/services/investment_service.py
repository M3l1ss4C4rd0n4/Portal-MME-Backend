"""
InvestmentService — Benchmarks LCOE internacionales y calculadora
de impacto tarifario para propuestas de inversión en renovables.

Fuentes:
  - IRENA Renewable Power Generation Costs 2023
  - UPME Plan de Expansión 2023-2037
  - XM Colombia — Informe de Operación SIN 2024
"""

BENCHMARKS_LCOE = {
    "solar_fv": {
        "nombre": "Solar Fotovoltaica",
        "colombia": {"min": 45, "max": 60, "unit": "USD/MWh"},
        "china": {"min": 28, "max": 35, "unit": "USD/MWh"},
        "alemania": {"min": 40, "max": 55, "unit": "USD/MWh"},
        "espana": {"min": 35, "max": 45, "unit": "USD/MWh"},
        "factor_capacidad_colombia": "18-22% (Costa Atlántica)",
        "meta_upme_2027_mw": 1_500,
        "fuente": "IRENA 2023 + UPME Plan Expansión 2023-2037",
    },
    "eolica": {
        "nombre": "Eólica",
        "colombia": {"min": 40, "max": 55, "unit": "USD/MWh"},
        "china": {"min": 25, "max": 35, "unit": "USD/MWh"},
        "alemania": {"min": 35, "max": 50, "unit": "USD/MWh"},
        "espana": {"min": 30, "max": 45, "unit": "USD/MWh"},
        "factor_capacidad_colombia": "40-50% (La Guajira)",
        "meta_upme_2027_mw": 3_000,
        "fuente": "IRENA 2023 + UPME Plan Expansión 2023-2037",
    },
    "hidro_pequena": {
        "nombre": "Hidroeléctrica Pequeña (<10 MW)",
        "colombia": {"min": 60, "max": 80, "unit": "USD/MWh"},
        "china": {"min": 50, "max": 70, "unit": "USD/MWh"},
        "alemania": {"min": 70, "max": 90, "unit": "USD/MWh"},
        "espana": {"min": 65, "max": 85, "unit": "USD/MWh"},
        "factor_capacidad_colombia": "35-45%",
        "meta_upme_2027_mw": 500,
        "fuente": "IRENA 2023",
    },
}

# Factores técnicos Colombia (XM/IDEAM/UPME)
GEN_SOLAR_MWH_POR_MW = 1_800     # Factor capacidad ~20.5% × 8760h
GEN_EOLICA_MWH_POR_MW = 3_500    # Factor capacidad ~40% × 8760h
GEN_TOTAL_SISTEMA_MWH_ANUAL = 80_000_000  # ~80 TWh SIN 2024

# ── Constantes financieras Colombia ──────────────────────────────────────────
CAPEX_USD_POR_MW = {
    "solar_fv":      850_000,   # USD/MW instalado Colombia 2024 (UPME)
    "eolica":      1_100_000,   # USD/MW La Guajira 2024
    "hidro_pequena": 2_200_000, # USD/MW filo de agua
}
OPEX_PORCENTAJE_CAPEX = {
    "solar_fv":      0.015,  # 1.5% CAPEX/año
    "eolica":        0.020,  # 2.0% CAPEX/año
    "hidro_pequena": 0.025,  # 2.5% CAPEX/año
}
FACTOR_CAPACIDAD = {
    "solar_fv":      0.20,   # ~20% Costa Atlántica (IDEAM)
    "eolica":        0.45,   # ~45% La Guajira (IDEAM)
    "hidro_pequena": 0.40,   # ~40% filo de agua
}
FACTOR_CO2_COLOMBIANO = 0.126       # tCO2/MWh (IDEAM 2023)
EMPLEOS_POR_MW = {
    "solar_fv":      5.2,    # empleos directos/MW instalado
    "eolica":        3.8,
    "hidro_pequena": 8.5,
}
PRECIO_CARBONO_USD_TON = 15.0       # mercado colombiano de carbono


def _get_trm() -> float:
    """TRM vigente — intenta DynamicConfig (API Banco de la República), fallback a config."""
    try:
        from core.config import get_TRM
        return get_TRM()
    except Exception:
        return 4_200.0


# ── Especificaciones de aerogeneradores plan inversión China ──────────────────
# Fuentes: fichas técnicas fabricante + UPME Plan Expansión 2023-2037

from dataclasses import dataclass, field  # noqa: E402 (ya importado arriba si aplica)
from typing import Optional  # noqa: E402


@dataclass
class WindTurbineSpec:
    """
    Especificaciones técnicas de un aerogenerador para cálculo de LCOE.

    La curva de potencia se define como lista de tuplas (viento_ms, potencia_kw)
    y se usa para integrar la distribución de Weibull del sitio.

    Fuentes:
        - Goldwind GW155-4.0MW: ficha técnica Goldwind 2023.
        - Mingyang MySE 5.5-155: ficha técnica Mingyang 2023.
        - NREL Cost of Wind Energy Review 2023.
    """

    modelo: str
    potencia_nominal_kw: float           # kW
    diametro_rotor_m: float              # metros
    altura_buje_m: float                 # metros
    velocidad_nominal_ms: float          # m/s (rated wind speed)
    velocidad_arranque_ms: float = 3.0   # cut-in
    velocidad_parada_ms: float = 25.0    # cut-out
    capex_usd_kw: float = 1_100.0        # USD/kW instalado
    opex_usd_kw_anio: float = 22.0       # USD/kW·año
    # Curva de potencia simplificada: [(v_ms, P_kw), ...]
    curva_potencia: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.curva_potencia:
            # Curva cúbica simplificada entre cut-in y rated speed
            self.curva_potencia = [
                (v, min(
                    self.potencia_nominal_kw,
                    self.potencia_nominal_kw * ((v - self.velocidad_arranque_ms) /
                    (self.velocidad_nominal_ms - self.velocidad_arranque_ms)) ** 3,
                ))
                for v in [float(i) for i in range(
                    int(self.velocidad_arranque_ms), int(self.velocidad_parada_ms) + 1
                )]
            ]

    def potencia_en(self, v_ms: float) -> float:
        """Potencia interpolada (kW) para velocidad de viento v_ms."""
        if v_ms < self.velocidad_arranque_ms or v_ms > self.velocidad_parada_ms:
            return 0.0
        # Interpolación lineal sobre curva
        for i in range(len(self.curva_potencia) - 1):
            v0, p0 = self.curva_potencia[i]
            v1, p1 = self.curva_potencia[i + 1]
            if v0 <= v_ms <= v1:
                t = (v_ms - v0) / (v1 - v0) if v1 > v0 else 0.0
                return p0 + t * (p1 - p0)
        return self.potencia_nominal_kw


# Catálogo de turbinas del plan de inversión chino (MME 2025-2037)
TURBINAS_PLAN_CHINA: dict[str, WindTurbineSpec] = {
    # CAPEX/OPEX basados en NREL Cost of Wind Energy Review 2023 ajustado por
    # factor Colombia (logística, aranceles, financiamiento +15 %).
    # Fuentes: NREL ATB 2023, IRENA Renewable Power Costs 2023, UPME 2024.
    "GOLDWIND_GW155_4MW": WindTurbineSpec(
        modelo="Goldwind GW155-4.0MW (nearshore La Guajira)",
        potencia_nominal_kw=4_000,
        diametro_rotor_m=155,
        altura_buje_m=110,
        velocidad_nominal_ms=10.5,
        velocidad_arranque_ms=3.0,
        velocidad_parada_ms=25.0,
        capex_usd_kw=3_200,   # NREL 2023: ~2800-3400 USD/kW offshore + factor CO
        opex_usd_kw_anio=90,  # NREL 2023: 80-100 USD/kW·año offshore
    ),
    "MINGYANG_MYSE_5_5_155": WindTurbineSpec(
        modelo="Mingyang MySE 5.5-155 (offshore La Guajira)",
        potencia_nominal_kw=5_500,
        diametro_rotor_m=155,
        altura_buje_m=120,
        velocidad_nominal_ms=11.5,
        velocidad_arranque_ms=3.0,
        velocidad_parada_ms=25.0,
        capex_usd_kw=3_500,   # MySE plataforma offshore; mayor coste subestructura
        opex_usd_kw_anio=110, # IRENA 2023: 100-120 USD/kW·año plataforma flotante
    ),
}


class LaGuajiraWindResource:
    """
    Recurso eólico de La Guajira (Colombia) parametrizado con distribución
    de Weibull calibrada a partir de datos ERA5-Land y IDEAM.

    Parámetros Weibull:
        k = 2.2  (factor de forma; vientos persistentes La Guajira)
        c = 9.5 m/s (factor de escala; zona offshore/costera noreste)

    Fuentes:
        - ERA5: Copernicus Climate Change Service (C3S, ECMWF) 1991-2023.
        - IDEAM Atlas de Viento Colombia (2015).
        - UPME Plan Expansión 2023-2037 — Potencial eólico La Guajira.
        - Ortega & Durán (2021) "Wind energy assessment in La Guajira" — JCR.
    """

    # Parámetros Weibull calibrados (offshore, 100 m agl)
    K_WEIBULL: float = 2.2
    C_WEIBULL: float = 9.5   # m/s

    # Horas anuales
    HORAS_ANIO: int = 8_760

    def __init__(
        self,
        k: float = 2.2,
        c: float = 9.5,
    ) -> None:
        self.k = k
        self.c = c

    def _weibull_pdf(self, v: float) -> float:
        """PDF de Weibull f(v) para velocidad v (m/s)."""
        import math
        if v <= 0:
            return 0.0
        return (self.k / self.c) * (v / self.c) ** (self.k - 1) * math.exp(-(v / self.c) ** self.k)

    def calculate_capacity_factor(
        self,
        turbine: WindTurbineSpec,
        v_max: float = 30.0,
        n_pasos: int = 300,
    ) -> float:
        """
        Factor de capacidad (%) integrando la distribución Weibull de La Guajira
        sobre la curva de potencia de la turbina.

        CF = (1/Pnom) × ∫₀^v_max P(v) × f_W(v) dv × 8760 / 8760
             = (1/Pnom) × ∫₀^v_max P(v) × f_W(v) dv

        Integración numérica por regla del trapecio.

        Args:
            turbine:   Especificaciones de la turbina.
            v_max:     Velocidad máxima de integración (m/s).
            n_pasos:   Número de intervalos para integración numérica.

        Returns:
            Factor de capacidad como fracción decimal (ej. 0.44 = 44%).
        """
        dv = v_max / n_pasos
        integral = 0.0
        for i in range(n_pasos):
            v_mid = (i + 0.5) * dv
            p_kw = turbine.potencia_en(v_mid)
            fw = self._weibull_pdf(v_mid)
            integral += p_kw * fw * dv

        cf = integral / turbine.potencia_nominal_kw if turbine.potencia_nominal_kw > 0 else 0.0
        return min(max(cf, 0.0), 1.0)   # clamp [0, 1]


class InvestmentService:
    """Servicio para propuestas de inversión en energías renovables."""

    def calculate_lcoe_eolico_guajira(
        self,
        turbine_key: str = "GOLDWIND_GW155_4MW",
        n_turbinas: int = 100,
        vida_util_anios: int = 25,
        tasa_descuento: float = 0.10,
        precio_carbono_usd_ton: float = 15.0,
        k_weibull: float = 2.2,
        c_weibull: float = 9.5,
    ) -> dict:
        """
        Calcula el LCOE específico para un parque eólico en La Guajira usando:
          - Curva de potencia real de la turbina (WindTurbineSpec)
          - Distribución Weibull calibrada a ERA5 La Guajira
          - TRM dinámica desde DynamicConfig (API Banco de la República)
          - Créditos de carbono del mercado colombiano

        LCOE (USD/MWh) = [CAPEX + Σ(OPEX_t / (1+r)^t)] / Σ(E_t / (1+r)^t)

        Args:
            turbine_key:           Clave en TURBINAS_PLAN_CHINA.
            n_turbinas:            Número de aerogeneradores.
            vida_util_anios:       Vida útil del proyecto.
            tasa_descuento:        Tasa de descuento real (fracción decimal).
            precio_carbono_usd_ton: Precio de carbono (USD/tCO2).
            k_weibull:             Factor de forma Weibull (default ERA5 La Guajira).
            c_weibull:             Factor de escala Weibull m/s (default ERA5).

        Returns:
            Dict con lcoe_usd_mwh, lcoe_cop_kwh, factor_capacidad_pct,
            capex_total_usd, capex_total_cop, generacion_anual_mwh,
            co2_evitado_ton_anual, turbina_info, trm_usada.

        Referencias:
            - ERA5: Copernicus C3S — ECMWF.
            - Goldwind / Mingyang: fichas técnicas fabricante 2023.
            - UPME Plan Expansión 2023-2037.
            - IEA Wind TCP Annual Report 2023.
        """
        turbine = TURBINAS_PLAN_CHINA.get(turbine_key)
        if turbine is None:
            raise ValueError(
                f"Turbina '{turbine_key}' no encontrada. "
                f"Opciones: {list(TURBINAS_PLAN_CHINA)}"
            )

        recurso = LaGuajiraWindResource(k=k_weibull, c=c_weibull)
        cf = recurso.calculate_capacity_factor(turbine)

        potencia_parque_kw = turbine.potencia_nominal_kw * n_turbinas
        gen_anual_mwh = potencia_parque_kw / 1_000 * cf * LaGuajiraWindResource.HORAS_ANIO

        capex_total_usd = turbine.capex_usd_kw * potencia_parque_kw
        opex_anual_usd  = turbine.opex_usd_kw_anio * potencia_parque_kw

        co2_ton_anual = gen_anual_mwh * FACTOR_CO2_COLOMBIANO
        ingresos_carbono_anual = co2_ton_anual * precio_carbono_usd_ton

        # Flujos descontados
        suma_costos = capex_total_usd + sum(
            opex_anual_usd / (1 + tasa_descuento) ** t
            for t in range(1, vida_util_anios + 1)
        )
        suma_energia = sum(
            gen_anual_mwh / (1 + tasa_descuento) ** t
            for t in range(1, vida_util_anios + 1)
        )
        # Créditos de carbono reducen el LCOE efectivo
        suma_carbono = sum(
            ingresos_carbono_anual / (1 + tasa_descuento) ** t
            for t in range(1, vida_util_anios + 1)
        )

        lcoe_bruto = suma_costos / suma_energia if suma_energia > 0 else 0.0
        lcoe_neto  = (suma_costos - suma_carbono) / suma_energia if suma_energia > 0 else 0.0

        trm = _get_trm()
        lcoe_cop_kwh_bruto = lcoe_bruto / 1_000 * trm   # USD/MWh → COP/kWh
        lcoe_cop_kwh_neto  = lcoe_neto  / 1_000 * trm

        return {
            "turbina_key":              turbine_key,
            "turbina_modelo":           turbine.modelo,
            "n_turbinas":               n_turbinas,
            "potencia_parque_mw":       round(potencia_parque_kw / 1_000, 1),
            "factor_capacidad_pct":     round(cf * 100, 2),
            "k_weibull":                k_weibull,
            "c_weibull":                c_weibull,
            "generacion_anual_mwh":     round(gen_anual_mwh, 0),
            "capex_total_usd":          round(capex_total_usd, 0),
            "capex_usd_kw":             turbine.capex_usd_kw,
            "opex_anual_usd":           round(opex_anual_usd, 0),
            "lcoe_bruto_usd_mwh":       round(lcoe_bruto, 2),
            "lcoe_neto_usd_mwh":        round(lcoe_neto, 2),
            "lcoe_bruto_cop_kwh":       round(lcoe_cop_kwh_bruto, 2),
            "lcoe_neto_cop_kwh":        round(lcoe_cop_kwh_neto, 2),
            "co2_evitado_ton_anual":    round(co2_ton_anual, 0),
            "ingresos_carbono_usd_anual": round(ingresos_carbono_anual, 0),
            "trm_usada":                trm,
            "capex_total_cop":          round(capex_total_usd * trm, 0),
            "vida_util_anios":          vida_util_anios,
            "tasa_descuento_pct":       tasa_descuento * 100,
            "fuentes": (
                "ERA5 Copernicus C3S; Goldwind/Mingyang fichas técnicas 2023; "
                "UPME Plan Expansión 2023-2037; IDEAM Atlas Viento Colombia."
            ),
        }

    def _get_parametros_reales(self) -> dict:
        """
        Lee de BD el CU promedio y la generación total del SIN (últimos 30/365d).
        Si la BD no está disponible devuelve los valores de referencia hardcodeados.
        Fuentes BD: cu_daily.cu_total, metrics(Gene/Sistema).
        """
        try:
            from infrastructure.database.connection import PostgreSQLConnectionManager
            cm = PostgreSQLConnectionManager()
            with cm.get_connection() as conn:
                cur = conn.cursor()

                # CU promedio últimos 30 días (COP/kWh)
                cur.execute(
                    "SELECT avg(cu_total) FROM cu_daily "
                    "WHERE fecha >= current_date - interval '30 days'"
                )
                cu_row = cur.fetchone()
                cu_real = float(cu_row[0]) if cu_row and cu_row[0] else 250.0

                # Generación total SIN últimos 365 días (MWh)
                cur.execute(
                    "SELECT sum(valor_gwh) * 1000 FROM metrics "
                    "WHERE metrica = 'Gene' AND entidad = 'Sistema' "
                    "AND fecha >= current_date - interval '365 days'"
                )
                gen_row = cur.fetchone()
                gen_mwh = float(gen_row[0]) if gen_row and gen_row[0] else 80_000_000.0

                return {"cu_cop_kwh": cu_real, "gen_total_mwh": gen_mwh}
        except Exception:
            # Fallback silencioso — nunca romper el dashboard
            return {"cu_cop_kwh": 250.0, "gen_total_mwh": 80_000_000.0}

    def get_benchmarks(self) -> list[dict]:
        """
        Retorna lista de dicts flat para usar en dash_table.DataTable.
        """
        rows = []
        for key, data in BENCHMARKS_LCOE.items():
            col = data["colombia"]
            chi = data["china"]
            ale = data["alemania"]
            esp = data["espana"]
            rows.append({
                "tecnologia": data["nombre"],
                "lcoe_colombia": f"{col['min']}–{col['max']} {col['unit']}",
                "lcoe_china": f"{chi['min']}–{chi['max']} {chi['unit']}",
                "lcoe_alemania": f"{ale['min']}–{ale['max']} {ale['unit']}",
                "lcoe_espana": f"{esp['min']}–{esp['max']} {esp['unit']}",
                "factor_cap_colombia": data["factor_capacidad_colombia"],
                "meta_upme_2027_mw": f"{data['meta_upme_2027_mw']:,} MW",
                "fuente": data["fuente"],
                # Para coloreo condicional: ¿Colombia es competitivo?
                # Solar y eólica Colombia son comparables a Alemania/España
                "_competitivo": key in ("solar_fv", "eolica"),
            })
        return rows

    def calculate_cu_impact(
        self,
        mw_solar: float = 0.0,
        mw_eolica: float = 0.0,
    ) -> dict:
        """
        Estima el impacto en el CU dado un incremento de capacidad renovable.

        Metodología:
          - 1 MW solar en Colombia ≈ 1,800 MWh/año (factor cap. 20.5%)
          - 1 MW eólico en La Guajira ≈ 3,500 MWh/año (factor cap. 40%)
          - Generación total SIN: leída de BD (metrics Gene/Sistema 365d)
          - Factor conservador 0.6: no toda la oferta desplaza térmica
          - CU de referencia: leído de BD (cu_daily promedio 30d)

        Returns:
            mw_total, generacion_adicional_gwh, reduccion_cu_pct,
            ahorro_estimado_cop_kwh, cu_referencia_cop_kwh
        """
        params = self._get_parametros_reales()
        cu_ref = params["cu_cop_kwh"]
        gen_total_mwh = params["gen_total_mwh"]

        gen_adicional_mwh = (
            mw_solar * GEN_SOLAR_MWH_POR_MW
            + mw_eolica * GEN_EOLICA_MWH_POR_MW
        )
        pct_del_sistema = gen_adicional_mwh / gen_total_mwh
        reduccion_cu_pct = pct_del_sistema * 0.6 * 100

        return {
            "mw_total": round(mw_solar + mw_eolica, 0),
            "mw_solar": mw_solar,
            "mw_eolica": mw_eolica,
            "generacion_adicional_gwh": round(gen_adicional_mwh / 1_000, 1),
            "reduccion_cu_pct": round(reduccion_cu_pct, 2),
            "ahorro_estimado_cop_kwh": round(reduccion_cu_pct / 100 * cu_ref, 1),
            "cu_referencia_cop_kwh": round(cu_ref, 2),
            "gen_total_sin_gwh": round(gen_total_mwh / 1_000, 0),
        }

    def calculate_financial_analysis(
        self,
        tecnologia: str,
        mw: float,
        vida_util_años: int = 25,
        tasa_descuento: float = 0.10,
        precio_energia_usd_mwh: float = 55.0,
    ) -> dict:
        """
        Calcula análisis financiero completo para un proyecto de energía
        renovable en Colombia.

        Retorna TIR, VAN, Payback, CO2 evitado y empleos generados.
        Fuentes: UPME 2024, IDEAM 2023, mercado carbono Colombia.
        """
        from scipy.optimize import brentq

        capex = CAPEX_USD_POR_MW[tecnologia] * mw
        opex_anual = capex * OPEX_PORCENTAJE_CAPEX[tecnologia]
        gen_anual_mwh = mw * 8760 * FACTOR_CAPACIDAD[tecnologia]

        ingresos_energia = gen_anual_mwh * precio_energia_usd_mwh
        co2_ton_anual = gen_anual_mwh * FACTOR_CO2_COLOMBIANO
        ingresos_carbono = co2_ton_anual * PRECIO_CARBONO_USD_TON
        ingresos_total = ingresos_energia + ingresos_carbono
        flujo_neto = ingresos_total - opex_anual

        # Flujos de caja: año 0 = -CAPEX, años 1-N = flujo_neto
        flujos = [-capex] + [flujo_neto] * vida_util_años

        def npv(r: float) -> float:
            return sum(f / (1 + r) ** t for t, f in enumerate(flujos))

        van = npv(tasa_descuento)

        try:
            tir = brentq(npv, 0.001, 0.999)
        except Exception as e:
            tir = flujo_neto / capex if capex > 0 else 0.0

        payback = capex / flujo_neto if flujo_neto > 0 else 99.0

        empleos_directos = int(EMPLEOS_POR_MW[tecnologia] * mw)

        return {
            "tecnologia": tecnologia,
            "mw": mw,
            "capex_total_usd": round(capex, 0),
            "capex_total_cop": round(capex * _get_trm(), 0),
            "trm_ref_cop_usd": _get_trm(),
            "opex_anual_usd": round(opex_anual, 0),
            "generacion_anual_mwh": round(gen_anual_mwh, 0),
            "ingresos_anuales_usd": round(ingresos_total, 0),
            "flujo_neto_anual_usd": round(flujo_neto, 0),
            "van_usd": round(van, 0),
            "tir_pct": round(float(tir) * 100, 2),  # type: ignore[arg-type]
            "payback_años": round(payback, 1),
            "co2_evitado_ton_anual": round(co2_ton_anual, 0),
            "co2_evitado_total": round(co2_ton_anual * vida_util_años, 0),
            "ingresos_carbono_usd_anual": round(ingresos_carbono, 0),
            "empleos_directos": empleos_directos,
            "empleos_indirectos": int(empleos_directos * 2.5),
            "empleos_total": int(empleos_directos * 3.5),
            "vida_util_años": vida_util_años,
            "tasa_descuento_pct": tasa_descuento * 100,
        }
