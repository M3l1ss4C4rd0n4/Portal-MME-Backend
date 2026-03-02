#!/usr/bin/env python3
"""
Script de prueba FASE 20: Envía informe ejecutivo completo a Melissa (mjcardona)
para verificar toda la implementación:
  - FASE 19: Redis API caching
  - Nueva página "Seguimiento Predicciones" (3 callbacks, 13 métricas)
  - Integración con orquestador, PDF, gráficos

Flujo:
  1. Llama al orquestador para generar informe con datos reales
  2. Ejecuta pruebas de los callbacks de la nueva página
  3. Genera PDF con gráficos
  4. Construye HTML email premium + sección de validación técnica
  5. Envía a Melissa por Telegram + Email
"""
import os
import sys
import json
import requests
from datetime import datetime

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

API_BASE = "http://localhost:8000"
DASH_BASE = "http://127.0.0.1:8050"
API_KEY = os.getenv('API_KEY', 'mme-portal-energetico-2026-secret-key')
HDR = {"Content-Type": "application/json", "X-API-Key": API_KEY}

DEST_EMAIL = "mjcardona@minenergia.gov.co"
DEST_CHAT_ID = 5084190952


def api_call(intent, params=None, timeout=120):
    """Llama al orquestador."""
    try:
        r = requests.post(
            f"{API_BASE}/v1/chatbot/orchestrator",
            json={
                "sessionId": f"test_fase20_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "intent": intent,
                "parameters": params or {},
            },
            headers=HDR,
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json().get('data', {})
        else:
            print(f"  ⚠️ API {intent} → {r.status_code}")
    except Exception as e:
        print(f"  ⚠️ Error API {intent}: {e}")
    return {}


def test_dashboard_callbacks():
    """Ejecuta las pruebas de los 3 callbacks de la nueva página."""
    results = {}
    
    # Inicializar callbacks lazily
    try:
        requests.get(f"{DASH_BASE}/", timeout=10)
    except:
        return {"error": "Dashboard no disponible"}
    
    import time
    time.sleep(1)
    
    # CB1: Resumen ejecutivo + tabla maestra
    try:
        r = requests.post(f"{DASH_BASE}/_dash-update-component", json={
            "output": "..seccion-resumen-ejecutivo.children...tabla-resumen-predicciones.children...dd-metrica-seguimiento.options...store-resumen-predicciones.data..",
            "outputs": [
                {"id": "seccion-resumen-ejecutivo", "property": "children"},
                {"id": "tabla-resumen-predicciones", "property": "children"},
                {"id": "dd-metrica-seguimiento", "property": "options"},
                {"id": "store-resumen-predicciones", "property": "data"}
            ],
            "inputs": [{"id": "dd-metrica-seguimiento", "property": "id", "value": "dd-metrica-seguimiento"}],
            "changedPropIds": ["dd-metrica-seguimiento.id"]
        }, timeout=30)
        
        if r.status_code == 200:
            data = r.json().get('response', r.json())
            opciones = data.get('dd-metrica-seguimiento', {}).get('options', [])
            store = data.get('store-resumen-predicciones', {}).get('data', [])
            results['cb1'] = {
                'status': 'OK', 'http': 200, 'bytes': len(r.content),
                'metricas': len(opciones), 'store_records': len(store),
                'opciones': opciones, 'store': store
            }
        else:
            results['cb1'] = {'status': 'FAIL', 'http': r.status_code}
    except Exception as e:
        results['cb1'] = {'status': 'ERROR', 'error': str(e)}
    
    # CB2: Análisis detallado por métrica
    test_metrics = ['DEMANDA', 'EMBALSES', 'PRECIO_BOLSA', 'Solar', 'Hidráulica']
    results['cb2'] = {}
    for metric in test_metrics:
        try:
            r = requests.post(f"{DASH_BASE}/_dash-update-component", json={
                "output": "..kpis-metrica-detalle.children...grafica-predicho-vs-real.children...tabla-dia-a-dia.children...grafica-error-diario.children..",
                "outputs": [
                    {"id": "kpis-metrica-detalle", "property": "children"},
                    {"id": "grafica-predicho-vs-real", "property": "children"},
                    {"id": "tabla-dia-a-dia", "property": "children"},
                    {"id": "grafica-error-diario", "property": "children"}
                ],
                "inputs": [{"id": "btn-analizar-metrica", "property": "n_clicks", "value": 1}],
                "changedPropIds": ["btn-analizar-metrica.n_clicks"],
                "state": [
                    {"id": "selector-metrica-detalle", "property": "value", "value": metric},
                    {"id": "selector-periodo-detalle", "property": "value", "value": "30"}
                ]
            }, timeout=30)
            results['cb2'][metric] = {
                'status': 'OK' if r.status_code == 200 else 'FAIL',
                'http': r.status_code,
                'bytes': len(r.content)
            }
        except Exception as e:
            results['cb2'][metric] = {'status': 'ERROR', 'error': str(e)}
    
    # CB3: Historial de calidad
    try:
        r = requests.post(f"{DASH_BASE}/_dash-update-component", json={
            "output": "tabla-quality-history.children",
            "outputs": {"id": "tabla-quality-history", "property": "children"},
            "inputs": [{"id": "dd-metrica-seguimiento", "property": "id", "value": "dd-metrica-seguimiento"}],
            "changedPropIds": ["dd-metrica-seguimiento.id"]
        }, timeout=30)
        results['cb3'] = {
            'status': 'OK' if r.status_code == 200 else 'FAIL',
            'http': r.status_code,
            'bytes': len(r.content)
        }
    except Exception as e:
        results['cb3'] = {'status': 'ERROR', 'error': str(e)}
    
    return results


def _mape_to_calidad(mape_decimal):
    """Convierte MAPE (decimal, ej: 0.05) a etiqueta de calidad."""
    if not isinstance(mape_decimal, (int, float)):
        return '?', '#9ca3af'
    if mape_decimal < 0.05:
        return 'Excelente', '#10b981'
    elif mape_decimal < 0.10:
        return 'Bueno', '#3b82f6'
    elif mape_decimal < 0.15:
        return 'Aceptable', '#f59e0b'
    else:
        return 'Revisar', '#ef4444'


def generate_prediction_charts(pred_data_list):
    """
    Genera gráficas PNG de predicciones para incluir en el PDF.
    Recibe lista de dicts del orquestador con 'fuente', 'predicciones', etc.
    Retorna lista de paths a PNGs temporales.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import tempfile

    chart_paths = []
    colors = ['#1e3a5f', '#e76f50', '#287270', '#8b5cf6']

    for i, pred_data in enumerate(pred_data_list):
        fuente = pred_data.get('fuente', f'Métrica_{i}')
        preds = pred_data.get('predicciones', [])
        stats = pred_data.get('estadisticas', {})
        modelo = pred_data.get('modelo', '')

        if not preds:
            continue

        try:
            fechas = [datetime.strptime(p['fecha'], '%Y-%m-%d') for p in preds]

            # Detectar campo de valor (puede ser valor_gwh, valor_pct, valor_cop, etc.)
            val_key = None
            for k in preds[0].keys():
                if k.startswith('valor'):
                    val_key = k
                    break
            if not val_key:
                continue

            valores = [p[val_key] for p in preds]
            inf_key = 'intervalo_inferior'
            sup_key = 'intervalo_superior'
            tiene_ic = inf_key in preds[0] and sup_key in preds[0]

            fig, ax = plt.subplots(figsize=(7, 2.8))
            color = colors[i % len(colors)]

            ax.plot(fechas, valores, color=color, linewidth=2, label='Predicción')

            if tiene_ic:
                inf = [p[inf_key] for p in preds]
                sup = [p[sup_key] for p in preds]
                ax.fill_between(fechas, inf, sup, alpha=0.15, color=color, label='IC 95%')

            ax.set_title(f'{fuente} — Predicción 30 días', fontsize=11, fontweight='bold', color='#1e293b')
            if modelo:
                ax.text(0.99, 0.97, f'Modelo: {modelo}', transform=ax.transAxes,
                        fontsize=7, color='#6b7280', ha='right', va='top')

            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
            plt.xticks(fontsize=8)
            plt.yticks(fontsize=8)

            # Unidad del eje Y
            unit = val_key.replace('valor_', '').upper()
            ax.set_ylabel(unit, fontsize=8, color='#475569')

            ax.grid(True, alpha=0.3, linestyle='--')
            ax.legend(fontsize=7, loc='upper left')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            plt.tight_layout()
            path = os.path.join(tempfile.gettempdir(), f'pred_chart_{fuente}.png')
            fig.savefig(path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            chart_paths.append((fuente, path))
        except Exception as e:
            print(f"   ⚠️ Chart {fuente}: {e}")

    return chart_paths


def build_pdf_validation_page(store_data, pred_chart_paths=None):
    """
    Genera página(s) HTML para el PDF con:
      - Tabla de las 13 métricas con MAPE real y Calidad
      - Gráficas de predicciones
    Solo datos relevantes. NO va en email ni en Telegram.
    """
    import base64

    # ── Tabla de métricas ──
    metricas_rows = ""
    # Ordenar: Excelente primero, luego Bueno, Aceptable, Revisar
    sorted_store = sorted(store_data, key=lambda s: s.get('mape_entrenamiento', 999))

    for s in sorted_store:
        fuente = s.get('fuente', '?')
        modelo = s.get('modelo', '?')
        mape = s.get('mape_entrenamiento', None)
        confianza = s.get('confianza', None)
        dias = s.get('dias_predichos', '?')

        calidad, badge_color = _mape_to_calidad(mape)
        mape_str = f"{mape*100:.2f}%" if isinstance(mape, (int, float)) else '?'
        conf_str = f"{confianza*100:.0f}%" if isinstance(confianza, (int, float)) else '?'

        metricas_rows += f"""
        <tr>
          <td style="padding:5px 8px;border-bottom:1px solid #dee2e6;font-size:8pt;font-weight:bold;">{fuente}</td>
          <td style="padding:5px 8px;border-bottom:1px solid #dee2e6;font-size:7pt;color:#6b7280;">{modelo}</td>
          <td style="padding:5px 8px;border-bottom:1px solid #dee2e6;font-size:8pt;text-align:center;">{mape_str}</td>
          <td style="padding:5px 8px;border-bottom:1px solid #dee2e6;font-size:8pt;text-align:center;">{conf_str}</td>
          <td style="padding:5px 8px;border-bottom:1px solid #dee2e6;font-size:8pt;text-align:center;">{dias}d</td>
          <td style="padding:5px 8px;border-bottom:1px solid #dee2e6;text-align:center;">
            <span style="background:{badge_color};color:#fff;padding:2px 8px;border-radius:10px;font-size:7pt;">{calidad}</span>
          </td>
        </tr>"""

    # Conteo por calidad
    counts = {'Excelente': 0, 'Bueno': 0, 'Aceptable': 0, 'Revisar': 0}
    for s in store_data:
        cal, _ = _mape_to_calidad(s.get('mape_entrenamiento'))
        if cal in counts:
            counts[cal] += 1

    # ── Gráficas de predicciones como imágenes embebidas ──
    charts_html = ""
    if pred_chart_paths:
        for fuente, path in pred_chart_paths:
            try:
                with open(path, 'rb') as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                charts_html += f"""
        <div style="margin:8px 10px;">
          <img src="data:image/png;base64,{img_b64}"
               style="width:100%;max-width:680px;border:1px solid #e5e7eb;border-radius:6px;" />
        </div>"""
            except Exception:
                pass

    return f"""
    <div class="page">
      <table class="header-bar" cellpadding="0" cellspacing="0">
        <tr>
          <td class="sidebar-mark" rowspan="2">&nbsp;</td>
          <td class="header-content">
            <div class="header-title">Seguimiento de Predicciones ML</div>
            <div class="header-date">Fecha: {datetime.now().strftime('%d de %B de %Y')}</div>
          </td>
        </tr>
      </table>
      <div class="header-line"></div>
      <div class="header-sep"></div>

      <!-- Resumen compacto -->
      <div class="section-hdr" style="background:#254553;">Resumen &mdash; 13 M&eacute;tricas Predictivas en Producci&oacute;n</div>
      <table style="width:90%;margin:6px auto;border-collapse:collapse;">
        <tr>
          <td style="text-align:center;padding:8px;background:#e8f5e9;width:25%;">
            <div style="font-size:16pt;font-weight:bold;color:#10b981;">{counts['Excelente']}</div>
            <div style="font-size:7pt;color:#555;">Excelente (&lt;5%)</div>
          </td>
          <td style="text-align:center;padding:8px;background:#e3f2fd;width:25%;">
            <div style="font-size:16pt;font-weight:bold;color:#3b82f6;">{counts['Bueno']}</div>
            <div style="font-size:7pt;color:#555;">Bueno (&lt;10%)</div>
          </td>
          <td style="text-align:center;padding:8px;background:#fff8e1;width:25%;">
            <div style="font-size:16pt;font-weight:bold;color:#f59e0b;">{counts['Aceptable']}</div>
            <div style="font-size:7pt;color:#555;">Aceptable (&lt;15%)</div>
          </td>
          <td style="text-align:center;padding:8px;background:#fce4ec;width:25%;">
            <div style="font-size:16pt;font-weight:bold;color:#ef4444;">{counts['Revisar']}</div>
            <div style="font-size:7pt;color:#555;">Revisar (&ge;15%)</div>
          </td>
        </tr>
      </table>

      <!-- Tabla completa -->
      <div style="margin:4px 10px;">
      <table style="width:100%;border-collapse:collapse;font-size:8pt;">
        <tr style="background:#1e3a5f;color:#fff;">
          <th style="padding:6px 8px;text-align:left;">M&eacute;trica</th>
          <th style="padding:6px 8px;text-align:left;">Modelo ML</th>
          <th style="padding:6px 8px;text-align:center;">MAPE %</th>
          <th style="padding:6px 8px;text-align:center;">Confianza</th>
          <th style="padding:6px 8px;text-align:center;">Horizonte</th>
          <th style="padding:6px 8px;text-align:center;">Calidad</th>
        </tr>
        {metricas_rows}
      </table>
      </div>

      <div style="margin-top:10px;text-align:center;font-size:7pt;color:#999;">
        MAPE = Error Absoluto Medio Porcentual (entrenamiento) &bull;
        Calidad: Excelente &lt;5% | Bueno &lt;10% | Aceptable &lt;15% | Revisar &ge;15%
      </div>
    </div>

    <!-- Página de gráficas de predicciones -->
    {"" if not charts_html else f'''
    <div class="page">
      <table class="header-bar" cellpadding="0" cellspacing="0">
        <tr>
          <td class="sidebar-mark" rowspan="2">&nbsp;</td>
          <td class="header-content">
            <div class="header-title">Gr&aacute;ficas de Predicciones</div>
            <div class="header-date">Fecha: {datetime.now().strftime('%d de %B de %Y')}</div>
          </td>
        </tr>
      </table>
      <div class="header-line"></div>
      <div class="header-sep"></div>
      <div class="section-hdr" style="background:#125685;">Predicciones a 30 d&iacute;as con Intervalo de Confianza 95%</div>
      {charts_html}
    </div>
    '''}
    """


def main():
    print("=" * 60)
    print("  📊 INFORME DE PRUEBA FASE 20 → Melissa (mjcardona)")
    print("=" * 60)
    
    # ── 1. Pruebas del dashboard ──
    print("\n1️⃣  Ejecutando pruebas de la nueva página Seguimiento Predicciones...")
    dash_results = test_dashboard_callbacks()
    
    cb1 = dash_results.get('cb1', {})
    cb2 = dash_results.get('cb2', {})
    cb3 = dash_results.get('cb3', {})
    
    total_ok = sum(1 for _, i in cb2.items() if i.get('status') == 'OK')
    total_ok += (1 if cb1.get('status') == 'OK' else 0) + (1 if cb3.get('status') == 'OK' else 0)
    total_tests = len(cb2) + 2
    print(f"   ✅ Dashboard: {total_ok}/{total_tests} tests pasaron")
    print(f"   Métricas: {cb1.get('metricas', '?')} activas")
    
    # ── 2. Generar informe ejecutivo del orquestador ──
    print("\n2️⃣  Generando informe ejecutivo del orquestador...")
    d_informe = api_call('informe_ejecutivo')
    informe_texto = d_informe.get('informe', '')
    generado_con_ia = d_informe.get('generado_con_ia', False)
    fecha_generacion = d_informe.get('fecha_generacion', datetime.now().strftime('%Y-%m-%d %H:%M'))
    contexto = d_informe.get('contexto_datos', {})
    
    if informe_texto:
        print(f"   ✅ Informe: {len(informe_texto)} chars, IA={generado_con_ia}")
    else:
        print("   ⚠️ No se obtuvo informe del orquestador — se enviará solo validación técnica")
    
    # ── 3. Datos complementarios ──
    print("\n3️⃣  Obteniendo datos complementarios...")
    d_estado = api_call('estado_actual', timeout=60)
    fichas_kpi = d_estado.get('fichas', []) if d_estado else []
    
    noticias = []
    d_news = api_call('noticias_sector', timeout=60)
    if d_news:
        noticias = d_news.get('noticias', [])
    
    # Predicciones (4 métricas clave para gráficas + 3 para email)
    predicciones_lista = []
    pred_para_graficas = []
    METRICAS_GRAFICAS = [
        ('DEMANDA', 'Demanda'),
        ('GENE_TOTAL', 'Generación Total'),
        ('PRECIO_BOLSA', 'Precio Bolsa'),
        ('EMBALSES_PCT', 'Embalses %'),
    ]
    for metric_id, metric_name in METRICAS_GRAFICAS:
        d_pred = api_call('predicciones', {'fuente': metric_id, 'horizonte': 30}, timeout=60)
        if d_pred and d_pred.get('estadisticas'):
            predicciones_lista.append(d_pred)
            pred_para_graficas.append(d_pred)
    
    print(f"   KPIs: {len(fichas_kpi)}, Noticias: {len(noticias)}, Predicciones: {len(predicciones_lista)}")
    
    # ── 4. Generar gráficos ──
    print("\n4️⃣  Generando gráficos del informe + predicciones...")
    chart_paths = []
    try:
        from whatsapp_bot.services.informe_charts import generate_all_informe_charts
        charts = generate_all_informe_charts()
        for key in ('generacion', 'embalses', 'precios'):
            path = charts.get(key, (None,))[0]
            if path and os.path.isfile(path):
                chart_paths.append(path)
        print(f"   ✅ Gráficos informe: {len(chart_paths)}")
    except Exception as e:
        print(f"   ⚠️ Gráficos informe: {e}")
    
    # Gráficas de predicciones para la página 6
    pred_chart_paths = []
    try:
        pred_chart_paths = generate_prediction_charts(pred_para_graficas)
        print(f"   ✅ Gráficos predicciones: {len(pred_chart_paths)} ({', '.join(f[0] for f in pred_chart_paths)})")
    except Exception as e:
        print(f"   ⚠️ Gráficos predicciones: {e}")
    
    # ── 5. Generar PDF (con página 6 de validación técnica) ──
    print("\n5️⃣  Generando PDF con página de validación técnica...")
    pdf_path = None
    try:
        from domain.services.report_service import (
            generar_pdf_informe,
            _CSS, _load_logo_b64,
            _build_page_mercado, _build_page_generacion,
            _build_page_hidrologia, _build_page_analisis,
            _build_page_noticias,
        )
        import tempfile
        from weasyprint import HTML as WP_HTML

        # Generar las 5 páginas normales + página 6 de validación
        hoy = fecha_generacion or datetime.now().strftime('%Y-%m-%d %H:%M')
        fecha_label = datetime.now().strftime('%Y-%m-%d')
        ctx = contexto or {}
        logo_b64 = _load_logo_b64()

        page1 = _build_page_mercado(
            logo_b64, fecha_label,
            fichas_kpi or [], ctx.get('tabla_indicadores_clave', []),
            chart_paths, pred_resumen=ctx.get('predicciones_mes_resumen', {}),
        )
        page2 = _build_page_generacion(
            logo_b64, fecha_label,
            ctx.get('generacion_por_fuente', {}), chart_paths,
            pred_resumen=ctx.get('predicciones_mes_resumen', {}),
        )
        page3 = _build_page_hidrologia(
            logo_b64, fecha_label,
            ctx.get('embalses_detalle', {}),
            ctx.get('predicciones_mes_resumen', {}), chart_paths,
        )
        page4 = _build_page_analisis(logo_b64, fecha_label, informe_texto or '')
        page5 = _build_page_noticias(logo_b64, fecha_label, [], noticias or [])

        # Página 6+7: Tabla métricas + gráficas predicciones (SOLO en el PDF)
        store_data = cb1.get('store', []) if cb1 else []
        page6 = build_pdf_validation_page(store_data, pred_chart_paths)

        full_html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><style>{_CSS}</style></head>
<body>
  {page1}
  {page2}
  {page3}
  {page4}
  {page5}
  {page6}
</body>
</html>"""

        filename = f'Informe_Ejecutivo_MME_{fecha_label}.pdf'
        pdf_path = os.path.join(tempfile.gettempdir(), filename)
        WP_HTML(string=full_html).write_pdf(pdf_path)

        size_kb = os.path.getsize(pdf_path) / 1024
        print(f"   ✅ PDF: {pdf_path} ({size_kb:.1f} KB) — 6 páginas (incl. validación técnica)")
    except Exception as e:
        print(f"   ⚠️ PDF custom falló ({e}), intentando PDF estándar...")
        try:
            from domain.services.report_service import generar_pdf_informe
            pdf_path = generar_pdf_informe(
                informe_texto or "Informe en proceso de generación",
                fecha_generacion, generado_con_ia,
                chart_paths=chart_paths,
                fichas=fichas_kpi,
                predicciones=predicciones_lista,
                anomalias=[],
                noticias=noticias,
                contexto_datos=contexto,
            )
            if pdf_path:
                size_kb = os.path.getsize(pdf_path) / 1024
                print(f"   ✅ PDF fallback: {pdf_path} ({size_kb:.1f} KB) — 5 páginas")
        except Exception as e2:
            print(f"   ⚠️ PDF fallback: {e2}")
    
    # ── 6. Construir HTML email (SIN validación técnica — eso va SOLO en el PDF) ──
    print("\n6️⃣  Construyendo email HTML premium (informe estándar)...")
    try:
        from domain.services.notification_service import build_daily_email_html, send_email
        
        email_html = build_daily_email_html(
            informe_texto or "Informe ejecutivo en proceso.",
            noticias=noticias,
            fichas=fichas_kpi,
            predicciones=predicciones_lista,
            anomalias=[],
            generado_con_ia=generado_con_ia,
        )
        # NO se inyecta sección técnica — eso va SOLO en el PDF adjunto
        print(f"   ✅ HTML: {len(email_html):,} chars (informe estándar, sin datos técnicos)")
    except Exception as e:
        print(f"   ⚠️ Error HTML: {e}")
        email_html = None
    
    # ── 7. Enviar por Telegram (SOLO el PDF, sin detalles técnicos en el mensaje) ──
    print(f"\n7️⃣  Enviando PDF por Telegram (chat_id={DEST_CHAT_ID})...")
    try:
        from domain.services.notification_service import _get_telegram_token
        import httpx
        
        token = _get_telegram_token()
        if token:
            base = f"https://api.telegram.org/bot{token}"
            with httpx.Client(timeout=30.0) as client:
                # Solo enviar el PDF con un caption breve
                if pdf_path and os.path.isfile(pdf_path):
                    with open(pdf_path, 'rb') as f:
                        resp_doc = client.post(
                            f"{base}/sendDocument",
                            data={
                                "chat_id": str(DEST_CHAT_ID),
                                "caption": f"Informe Ejecutivo MME — {datetime.now().strftime('%Y-%m-%d')}\nIncluye validacion tecnica de nuevas funcionalidades (pag. 6)",
                            },
                            files={"document": (os.path.basename(pdf_path), f, "application/pdf")},
                        )
                        if resp_doc.status_code == 200:
                            print(f"   ✅ PDF enviado por Telegram")
                        else:
                            print(f"   ❌ PDF Telegram: {resp_doc.status_code} {resp_doc.text[:200]}")
                else:
                    print("   ⚠️ No hay PDF para enviar")
        else:
            print("   ❌ TELEGRAM_BOT_TOKEN no configurado")
    except Exception as e:
        print(f"   ❌ Error Telegram: {e}")
    
    # ── 8. Enviar por Email (informe estándar + PDF con validación en pág. 6) ──
    print(f"\n8️⃣  Enviando email a {DEST_EMAIL}...")
    if email_html:
        try:
            result = send_email(
                to_list=[DEST_EMAIL],
                subject=f"Informe Ejecutivo Diario — Portal Energetico MME — {datetime.now().strftime('%Y-%m-%d')}",
                body_html=email_html,
                pdf_path=pdf_path,
            )
            print(f"   📧 Resultado: {result}")
            print(f"   ℹ️  Validación técnica incluida en página 6 del PDF adjunto")
        except Exception as e:
            print(f"   ❌ Error email: {e}")
    else:
        print("   ❌ No se pudo construir el HTML del email")
    
    # ── 9. Limpieza ──
    if pdf_path and os.path.isfile(pdf_path):
        try:
            os.remove(pdf_path)
        except OSError:
            pass
    for cp in chart_paths:
        try:
            if cp and os.path.isfile(cp):
                os.remove(cp)
        except OSError:
            pass
    for _, cp in pred_chart_paths:
        try:
            if cp and os.path.isfile(cp):
                os.remove(cp)
        except OSError:
            pass
    
    print(f"\n{'=' * 60}")
    print(f"  ✅ INFORME DE PRUEBA FASE 20 COMPLETADO")
    print(f"  📧 Email → {DEST_EMAIL}")
    print(f"  📱 Telegram → chat_id {DEST_CHAT_ID}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
