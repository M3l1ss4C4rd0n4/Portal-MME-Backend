"""
Script de prueba para enviar el informe ejecutivo por email.

Flujo completo (idéntico al que usa Celery send_daily_summary):
  1. Llama al orquestador para obtener informe IA, KPIs, predicciones y anomalías.
  2. Genera el PDF con todos los gráficos incrustados.
  3. Construye el HTML con la plantilla corporativa premium completa.
  4. Envía el email con el PDF adjunto.

Uso:
  python scripts/send_test_informe_email.py mjcardona@minenergia.gov.co
  python scripts/send_test_informe_email.py --pdf-only   # solo genera PDF en /tmp
  python scripts/send_test_informe_email.py --keep-pdf correo@minenergia.gov.co
"""
import sys
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from datetime import datetime
import requests

from domain.services.notification_service import build_daily_email_html, send_email
from domain.services.report_service import generar_pdf_informe


API_BASE = "http://localhost:8000"

# Correos de ejemplo en documentación — NO son buzones reales.
_PLACEHOLDER_EMAILS = {
    'tu@correo.gov.co',
    'correo@ejemplo.com',
    'test@test.com',
    'example@example.com',
}
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _validar_destinatario(email: str) -> None:
    email = email.strip().lower()
    if email in _PLACEHOLDER_EMAILS or email.startswith('tu@'):
        print(
            f"\n❌ Destinatario inválido: {email}\n"
            "   Ese es un correo de EJEMPLO de la documentación, no un buzón real.\n"
            "   El SMTP lo acepta pero el mensaje nunca llegará.\n"
            "   Usa tu correo real, por ejemplo:\n"
            "   python scripts/send_test_informe_email.py mjcardona@minenergia.gov.co\n"
        )
        sys.exit(1)
    if not _EMAIL_RE.match(email):
        print(f"\n❌ Formato de correo inválido: {email}\n")
        sys.exit(1)


def _api_call(intent: str, parameters: dict = None) -> dict:
    API_KEY = os.getenv('API_KEY')
    if not API_KEY:
        raise ValueError("API_KEY no configurada en variables de entorno")
    try:
        resp = requests.post(
            f"{API_BASE}/v1/chatbot/orchestrator",
            json={
                "sessionId": f"email_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{intent}",
                "intent": intent,
                "parameters": parameters or {},
            },
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json().get('data', {})
        print(f"   ⚠️  {intent} respondió {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"   ⚠️  Error en {intent}: {e}")
    return {}


def generar_charts_y_pdf(informe_texto, fecha_gen, con_ia, fichas, predicciones, anomalias, noticias, contexto_datos):
    chart_paths = []
    portal_data = {}
    portal_chart_paths = {}
    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, 'whatsapp_bot'))
        from services.informe_charts import generate_all_informe_charts
        charts = generate_all_informe_charts()
        for key in ['generacion', 'embalses', 'precios', 'demanda', 'precio_multi', 'aportes_hidricos',
                    'despacho_termica', 'capacidad_embalse', 'aportes_demanda']:
            if key in charts:
                fp = charts[key][0] if isinstance(charts[key], (list, tuple)) else charts[key]
                if fp and os.path.isfile(str(fp)):
                    chart_paths.append(str(fp))
        print(f"   Gráficos sector: {len(chart_paths)}")
    except Exception as e:
        print(f"   ⚠️  No se pudieron generar gráficos sector: {e}")

    try:
        from services.informe_portal_data import fetch_all_portal_dashboards
        from services.informe_portal_charts import generate_all_portal_charts
        portal_data = fetch_all_portal_dashboards()
        portal_chart_paths = generate_all_portal_charts(portal_data)
        print(f"   Gráficos portal: {len(portal_chart_paths)}")
    except Exception as e:
        print(f"   ⚠️  No se pudieron generar datos/gráficos portal: {e}")

    pdf_path = generar_pdf_informe(
        informe_texto,
        fecha_generacion=fecha_gen,
        generado_con_ia=con_ia,
        chart_paths=chart_paths,
        fichas=fichas,
        predicciones=predicciones,
        anomalias=anomalias,
        noticias=noticias,
        contexto_datos=contexto_datos,
        portal_data=portal_data or None,
        portal_chart_paths=portal_chart_paths or None,
    )
    return pdf_path, chart_paths


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a.startswith('-')]
    positional = [a for a in sys.argv[1:] if not a.startswith('-')]

    pdf_only = '--pdf-only' in args
    keep_pdf = '--keep-pdf' in args or pdf_only

    if pdf_only and not positional:
        destinatario = None
    elif not positional:
        print("Uso: python scripts/send_test_informe_email.py [--pdf-only] [--keep-pdf] <correo_destino>")
        print("Ejemplo: python scripts/send_test_informe_email.py mjcardona@minenergia.gov.co")
        sys.exit(1)
    else:
        destinatario = positional[0].strip()
        _validar_destinatario(destinatario)

    print(f"\n{'='*60}")
    print(f"  ENVÍO DE INFORME EJECUTIVO - PRUEBA COMPLETA")
    print(f"{'='*60}")
    if pdf_only:
        print(f"  Modo: solo PDF (sin email)")
    else:
        print(f"  Destinatario: {destinatario}")
    print(f"  SMTP: {os.getenv('SMTP_SERVER')} ({os.getenv('SMTP_USER')})")
    print(f"{'='*60}\n")

    # ── 1. Informe IA ──
    print("1️⃣  Obteniendo informe ejecutivo IA...")
    d_informe = _api_call('informe_ejecutivo')
    informe_texto = d_informe.get('informe', '')
    generado_con_ia = d_informe.get('generado_con_ia', False)
    fecha_generacion = d_informe.get('fecha_generacion', datetime.now().strftime('%Y-%m-%d %H:%M'))
    contexto_datos = d_informe.get('contexto_datos') or {}
    if not informe_texto:
        print("   ❌ No se pudo obtener el informe. Abortando.")
        sys.exit(1)
    print(f"   ✅ Informe: {len(informe_texto)} chars | IA={generado_con_ia}")

    # ── 2. Estado actual (fichas KPI) ──
    print("\n2️⃣  Obteniendo KPIs (estado actual)...")
    d_estado = _api_call('estado_actual')
    fichas = d_estado.get('fichas', [])
    print(f"   ✅ KPIs obtenidos: {len(fichas)}")

    # ── 3. Predicciones 1 mes ──
    print("\n3️⃣  Obteniendo predicciones a 1 mes...")
    d_pred = _api_call('predicciones_sector', {'horizonte': '1_mes'})
    predicciones = d_pred.get('predicciones', [])
    print(f"   ✅ Predicciones: {len(predicciones)} puntos")

    # ── 4. Anomalías ──
    print("\n4️⃣  Obteniendo anomalías detectadas...")
    d_anomalias = _api_call('anomalias_detectadas')
    anomalias = d_anomalias.get('anomalias', [])
    print(f"   ✅ Anomalías: {len(anomalias)}")

    # ── 5. Noticias ──
    print("\n5️⃣  Obteniendo noticias del sector...")
    d_noticias = _api_call('noticias_sector')
    noticias = d_noticias.get('noticias', [])
    print(f"   ✅ Noticias: {len(noticias)}")

    # ── 6. PDF con gráficos completos ──
    print("\n6️⃣  Generando PDF completo con gráficos...")
    pdf_path, chart_paths = generar_charts_y_pdf(
        informe_texto, fecha_generacion, generado_con_ia,
        fichas, predicciones, anomalias, noticias, contexto_datos,
    )
    if pdf_path:
        print(f"   ✅ PDF: {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")
        if keep_pdf:
            informes_dir = os.path.join(PROJECT_ROOT, 'whatsapp_bot', 'informes')
            os.makedirs(informes_dir, exist_ok=True)
            dest_copy = os.path.join(informes_dir, os.path.basename(pdf_path))
            import shutil
            shutil.copy2(pdf_path, dest_copy)
            print(f"   📁 Copia guardada: {dest_copy}")
    else:
        print("   ⚠️  PDF no generado (se enviará solo HTML)")

    if pdf_only:
        print("\n✅ PDF generado (modo --pdf-only, no se envió email)")
        if not keep_pdf and pdf_path and os.path.isfile(pdf_path):
            os.remove(pdf_path)
        sys.exit(0)

    # ── 7. HTML premium completo ──
    print("\n7️⃣  Construyendo HTML premium...")
    indices_compuestos = contexto_datos.get('indices_compuestos') if contexto_datos else None
    email_html = build_daily_email_html(
        informe_texto,
        noticias=noticias,
        fichas=fichas,
        predicciones=predicciones or None,
        anomalias=anomalias or None,
        generado_con_ia=generado_con_ia,
        indices_compuestos=indices_compuestos,
    )
    print(f"   ✅ HTML: {len(email_html):,} chars")

    # ── 8. Enviar ──
    asunto = f"[PRUEBA] Informe Ejecutivo Sector Eléctrico — {datetime.now().strftime('%Y-%m-%d')}"
    print(f"\n8️⃣  Enviando email...")
    resultado = send_email(
        to_list=[destinatario],
        subject=asunto,
        body_html=email_html,
        pdf_path=pdf_path,
    )
    print(f"   Resultado: {resultado}")

    # Limpiar temporales (salvo --keep-pdf)
    if not keep_pdf:
        for p in ([pdf_path] + chart_paths):
            if p and os.path.isfile(str(p)):
                try:
                    os.remove(str(p))
                except OSError:
                    pass

    if resultado.get('sent', 0) > 0:
        print(f"\n✅ Email completo enviado a {destinatario}")
    else:
        print(f"\n❌ Error enviando email: {resultado}")
