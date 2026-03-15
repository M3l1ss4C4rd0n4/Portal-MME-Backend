import sys
sys.path.insert(0, '.')

checks = []

# OE7: CU real
from domain.services.investment_service import InvestmentService
svc = InvestmentService()
has_real = hasattr(svc, '_get_parametros_reales')
if has_real:
    p = svc._get_parametros_reales()
    cu = p.get('cu_cop_kwh', 250)
    checks.append(f"{'OK' if abs(cu-189) < 30 else 'FAIL'} OE7 CU real: {cu:.1f} COP/kWh")
else:
    checks.append("FAIL OE7 _get_parametros_reales NO existe")

# OE6: 7 escenarios
from domain.services.simulation_service import SimulationService
sim = SimulationService()
esc_count = 0
for attr in ['get_escenarios_disponibles', 'get_escenarios_predefinidos', 'ESCENARIOS', 'escenarios']:
    if hasattr(sim, attr):
        val = getattr(sim, attr)
        esc = val() if callable(val) else val
        esc_count = len(esc) if esc else 0  # type: ignore[arg-type]
        checks.append(f"{'OK' if esc_count>=7 else 'FAIL'} OE6 Escenarios: {esc_count}/7 (via {attr})")
        break

# OE4: Predicciones 365d en BD
from infrastructure.database.connection import PostgreSQLConnectionManager
cm = PostgreSQLConnectionManager()
try:
    with cm.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT horizonte_dias, count(*) FROM predictions GROUP BY horizonte_dias ORDER BY horizonte_dias")
        rows = cur.fetchall()
        p365 = next((r[1] for r in rows if r[0]==365), 0)
        checks.append(f"{'OK' if p365 > 1000 else 'FAIL'} OE4 Predicciones 365d: {p365} filas | all: {rows}")
except Exception as e:
    checks.append(f"FAIL OE4 BD error: {e}")

# OE3: Mapa NT
from domain.services.losses_nt_service import LossesNTService
nt = LossesNTService()
if hasattr(nt, 'get_perdidas_por_departamento'):
    df_nt = nt.get_perdidas_por_departamento()
    checks.append(f"OK OE3 Mapa NT: {len(df_nt)} dptos")
else:
    checks.append(f"FAIL OE3 get_perdidas_por_departamento NO existe")

# OE1: Mapas distribucion y comercializacion
from domain.services.distribution_service import DistributionService
from domain.services.commercial_service import CommercialService
df_d = DistributionService().get_demanda_por_departamento()
df_c = CommercialService().get_usuarios_por_departamento()
checks.append(f"OK OE1 Mapas: {len(df_d)} dptos distribucion, {len(df_c)} comercializacion")

# OE5: ReportService
try:
    from domain.services.report_service import ReportService  # type: ignore[attr-defined]
    rs = ReportService()
    pdf_methods = [m for m in dir(rs) if 'pdf' in m.lower() or 'report' in m.lower() or 'informe' in m.lower()]
    has_pdf = any('pdf' in m.lower() for m in pdf_methods)
    checks.append(f"{'OK' if has_pdf else 'WARN'} OE5 PDF methods: {pdf_methods}")
except Exception as e:
    checks.append(f"FAIL OE5 ReportService: {e}")

print("\n=== CODIGO EN MEMORIA ===")
for c in checks:
    icon = "✅" if c.startswith("OK") else ("⚠️" if c.startswith("WARN") else "❌")
    print(f"{icon} {c}")
