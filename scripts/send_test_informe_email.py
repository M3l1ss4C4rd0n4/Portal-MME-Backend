"""
Script de prueba para enviar el informe ejecutivo por email.

Flujo completo (idéntico al que usa Celery send_daily_summary):
  1. Llama al orquestador para obtener el informe con datos REALES.
  2. Genera el PDF con gráficos incrustados.
  3. Construye el HTML con la plantilla corporativa premium.
  4. Envía el email con el PDF adjunto.
"""
import sys
import os

# Agregar el directorio raíz del proyecto al path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Cargar variables de entorno desde .env
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from datetime import datetime
import requests

from domain.services.notification_service import build_daily_email_html, send_email
from domain.services.report_service import generar_pdf_informe


def obtener_informe_real() -> dict:
    """Llama al orquestador para obtener el informe con datos reales de la BD."""
    API_BASE = "http://localhost:8000"
    API_KEY = os.getenv('API_KEY', 'mme-portal-energetico-2026-secret-key')

    try:
        resp = requests.post(
            f"{API_BASE}/v1/chatbot/orchestrator",
            json={
                "sessionId": f"email_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "intent": "informe_ejecutivo",
                "parameters": {},
            },
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            return {
                'informe': data.get('informe', ''),
                'generado_con_ia': data.get('generado_con_ia', False),
                'fecha_generacion': data.get('fecha_generacion', ''),
            }
        else:
            print(f"⚠️  Orquestador respondió {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"⚠️  Error llamando al orquestador: {e}")

    return {}


def obtener_noticias_sector() -> list:
    """Llama al orquestador para obtener las noticias del sector."""
    API_BASE = "http://localhost:8000"
    API_KEY = os.getenv('API_KEY', 'mme-portal-energetico-2026-secret-key')

    try:
        resp = requests.post(
            f"{API_BASE}/v1/chatbot/orchestrator",
            json={
                "sessionId": f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "intent": "noticias_sector",
                "parameters": {},
            },
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            noticias = data.get('noticias', [])
            print(f"   ✅ Noticias obtenidas: {len(noticias)}")
            return noticias
        else:
            print(f"   ⚠️  Noticias respondió {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️  Error obteniendo noticias: {e}")

    return []


def generar_pdf_con_graficos(informe_texto: str, fecha_gen: str, con_ia: bool):
    """Genera PDF con gráficos incrustados (igual que el bot de Telegram)."""
    chart_paths = []
    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, 'whatsapp_bot'))
        from services.informe_charts import generate_all_informe_charts
        charts = generate_all_informe_charts()
        for key in ['generacion', 'embalses', 'precios']:
            if key in charts:
                filepath = charts[key][0]
                if filepath:
                    chart_paths.append(filepath)
        print(f"   Gráficos generados: {len(chart_paths)}")
    except Exception as e:
        print(f"   ⚠️  No se pudieron generar gráficos: {e}")

    pdf_path = generar_pdf_informe(
        informe_texto,
        fecha_generacion=fecha_gen,
        generado_con_ia=con_ia,
        chart_paths=chart_paths,
    )
    return pdf_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/send_test_informe_email.py <correo_destino>")
        sys.exit(1)

    destinatario = sys.argv[1]
    print(f"\n{'='*60}")
    print(f"  ENVÍO DE INFORME EJECUTIVO - PRUEBA")
    print(f"{'='*60}")
    print(f"  Destinatario: {destinatario}")
    print(f"  SMTP: {os.getenv('SMTP_SERVER')} ({os.getenv('SMTP_USER')})")
    print(f"{'='*60}\n")

    # ── 1. Obtener informe con datos reales ──
    print("1️⃣  Obteniendo informe del orquestador (datos reales de la BD)...")
    informe_data = obtener_informe_real()
    informe_texto = informe_data.get('informe', '')

    if not informe_texto:
        print("   ❌ No se pudo obtener el informe. Abortando.")
        sys.exit(1)

    print(f"   ✅ Informe obtenido: {len(informe_texto)} caracteres")
    print(f"   IA: {informe_data.get('generado_con_ia', False)}")
    print(f"   Fecha: {informe_data.get('fecha_generacion', 'N/D')}")

    # ── 2. Obtener noticias del sector ──
    print("\n2️⃣  Obteniendo noticias del sector energético...")
    noticias = obtener_noticias_sector()

    # ── 3. Generar PDF ──
    print("\n3️⃣  Generando PDF con gráficos...")
    pdf_path = generar_pdf_con_graficos(
        informe_texto,
        informe_data.get('fecha_generacion', ''),
        informe_data.get('generado_con_ia', False),
    )
    if pdf_path:
        file_size = os.path.getsize(pdf_path)
        print(f"   ✅ PDF generado: {pdf_path} ({file_size:,} bytes)")
    else:
        print("   ⚠️  PDF no generado (se enviará solo HTML)")

    # ── 4. Construir HTML con plantilla premium ──
    print("\n4️⃣  Construyendo plantilla HTML premium...")
    email_html = build_daily_email_html(informe_texto, noticias=noticias)
    print(f"   ✅ HTML generado: {len(email_html):,} caracteres")

    # ── 5. Enviar email con PDF adjunto ──
    asunto = (
        f"[PRUEBA] Informe Ejecutivo del Sector Eléctrico — "
        f"{datetime.now().strftime('%Y-%m-%d')}"
    )
    print(f"\n5️⃣  Enviando email...")
    resultado = send_email(
        to_list=[destinatario],
        subject=asunto,
        body_html=email_html,
        pdf_path=pdf_path,
    )
    print(f"   Resultado: {resultado}")

    # Limpiar PDF temporal
    if pdf_path and os.path.isfile(pdf_path):
        try:
            os.remove(pdf_path)
        except OSError:
            pass

    if resultado.get('sent', 0) > 0:
        print(f"\n✅ Email enviado exitosamente a {destinatario}")
    else:
        print(f"\n❌ Error enviando email")

