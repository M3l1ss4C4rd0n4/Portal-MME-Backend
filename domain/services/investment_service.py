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


class InvestmentService:
    """Servicio para propuestas de inversión en energías renovables."""

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
          - Generación total SIN ≈ 80 TWh/año (XM 2024)
          - Factor conservador 0.6: no toda la oferta desplaza térmica
          - CU de referencia ≈ 250 COP/kWh (XM promedio reciente)

        Returns:
            mw_total, generacion_adicional_gwh, reduccion_cu_pct,
            ahorro_estimado_cop_kwh
        """
        gen_adicional_mwh = (
            mw_solar * GEN_SOLAR_MWH_POR_MW
            + mw_eolica * GEN_EOLICA_MWH_POR_MW
        )
        pct_del_sistema = gen_adicional_mwh / GEN_TOTAL_SISTEMA_MWH_ANUAL
        reduccion_cu_pct = pct_del_sistema * 0.6 * 100

        return {
            "mw_total": round(mw_solar + mw_eolica, 0),
            "mw_solar": mw_solar,
            "mw_eolica": mw_eolica,
            "generacion_adicional_gwh": round(gen_adicional_mwh / 1_000, 1),
            "reduccion_cu_pct": round(reduccion_cu_pct, 2),
            "ahorro_estimado_cop_kwh": round(
                reduccion_cu_pct / 100 * 250, 1
            ),
        }
