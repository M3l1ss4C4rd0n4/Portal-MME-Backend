#!/usr/bin/env python3
"""
Script de prueba: genera el informe ejecutivo y lo envía SOLO a:
- Email: mjcardona@minenergia.gov.co
- Telegram: chat_id 5084190952 (Melissa)

Esto NO envía al resto de destinatarios. Solo para validar los cambios
de embalses + predicciones_mes.
"""
import os
import sys
import re as _re
import json
import requests
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

API_BASE = "http://localhost:8000"
API_KEY = os.getenv('API_KEY', 'mme-portal-energetico-2026-secret-key')
HDR = {"Content-Type": "application/json", "X-API-Key": API_KEY}

DEST_EMAIL = "mjcardona@minenergia.gov.co"
DEST_CHAT_ID = 5084190952


def _clean_markdown_for_telegram(text: str) -> str:
    """Convierte markdown estándar a Telegram Markdown v1."""
    text = _re.sub(r'^#\s+INFORME.+\n?', '', text)
    text = _re.sub(r'^\ud83d\udcc5\s*Fecha:.+\n?', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'^##\s*(\d+\.\s*.+)$', r'*\1*', text, flags=_re.MULTILINE)
    text = _re.sub(r'^###?\s*(\d+\.\d+\s*.+)$', r'_\1_', text, flags=_re.MULTILINE)
    text = _re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = _re.sub(r'^-\s+', '▸ ', text, flags=_re.MULTILINE)
    text = _re.sub(r'^\s{2,}-\s+', '  · ', text, flags=_re.MULTILINE)
    return text.strip()


def _api_call(intent, params=None, timeout=120):
    try:
        r = requests.post(
            f"{API_BASE}/v1/chatbot/orchestrator",
            json={
                "sessionId": f"test_informe_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "intent": intent,
                "parameters": params or {},
            },
            headers=HDR,
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json().get('data', {})
        else:
            print(f"❌ API {intent} → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"❌ Error API {intent}: {e}")
    return {}


def main():
    print("=" * 60)
    print("📊 TEST: Informe Ejecutivo → solo mjcardona")
    print("=" * 60)

    # ── 1. Generar informe (llama al orquestador con los cambios) ──
    print("\n🔄 Obteniendo informe ejecutivo de la API...")
    d_informe = _api_call('informe_ejecutivo')

    informe_texto = d_informe.get('informe')
    generado_con_ia = d_informe.get('generado_con_ia', False)
    fecha_generacion = d_informe.get('fecha_generacion', datetime.now().strftime('%Y-%m-%d %H:%M'))
    contexto = d_informe.get('contexto_datos', {})

    if not informe_texto:
        print("❌ No se obtuvo informe. Abortando.")
        return

    print(f"✅ Informe obtenido: {len(informe_texto)} chars, IA={generado_con_ia}")

    # ── Verificar los campos nuevos en el contexto ──
    print("\n🔍 Verificando campos nuevos en el contexto...")

    # Verificar embalses
    fichas = contexto.get('estado_actual', {}).get('fichas', [])
    ficha_embalses = None
    for f in fichas:
        if 'embalse' in f.get('indicador', '').lower():
            ficha_embalses = f
            break

    if ficha_embalses:
        ctx_emb = ficha_embalses.get('contexto', {})
        print(f"  💧 Embalses valor: {ficha_embalses.get('valor')}%")
        print(f"     Fecha dato: {ficha_embalses.get('fecha')}")
        print(f"     Promedio 30d: {ctx_emb.get('promedio_30d')}")
        print(f"     Media histórica 2020-2025: {ctx_emb.get('media_historica_2020_2025')}")
        print(f"     Desviación vs media 2020-2025: {ctx_emb.get('desviacion_pct_media_historica_2020_2025')}%")
        print(f"     Estado: {ctx_emb.get('estado')}")
        print(f"     Nota: {ctx_emb.get('nota_embalses', 'N/A')}")
    else:
        print("  ⚠️ No se encontró ficha de embalses")

    # Verificar predicciones_mes
    pred_mes = contexto.get('predicciones_mes', {})
    metricas = pred_mes.get('metricas_clave', {})
    print(f"\n  📈 Predicciones del mes:")
    print(f"     Horizonte: {pred_mes.get('horizonte')}")
    for clave in ['generacion', 'precio_bolsa', 'embalses']:
        m = metricas.get(clave, {})
        if m:
            print(f"     {m.get('emoji','')} {m.get('indicador','?')}: "
                  f"prom={m.get('promedio_periodo')} {m.get('unidad','')}, "
                  f"rango={m.get('rango_min')}-{m.get('rango_max')}, "
                  f"cambio={m.get('cambio_pct_vs_historico')}%, "
                  f"tend={m.get('tendencia')}")
        else:
            print(f"     ⚠️ '{clave}' no encontrada en predicciones_mes")

    # ── 2. Obtener KPIs y datos extra ──
    print("\n🔄 Obteniendo datos complementarios...")
    d_estado = _api_call('estado_actual', timeout=60)
    fichas_kpi = d_estado.get('fichas', []) if d_estado else []

    noticias = []
    d_news = _api_call('noticias_sector', timeout=60)
    if d_news:
        noticias = d_news.get('noticias', [])

    print(f"  KPIs: {len(fichas_kpi)}, Noticias: {len(noticias)}")

    # ── 2b. Obtener predicciones para las 3 métricas clave ──
    print("\n🔄 Obteniendo predicciones (3 métricas)...")
    _PRED_METRICS = [
        ('GENE_TOTAL', 'Generación Total del Sistema'),
        ('PRECIO_BOLSA', 'Precio de Bolsa Nacional'),
        ('EMBALSES_PCT', 'Porcentaje de Embalses'),
    ]
    predicciones_lista = []
    for metric_id, metric_name in _PRED_METRICS:
        d_pred = _api_call('predicciones', {'fuente': metric_id, 'horizonte': 30}, timeout=60)
        if d_pred and d_pred.get('estadisticas'):
            predicciones_lista.append(d_pred)
            st = d_pred['estadisticas']
            print(f"  ✅ {metric_name}: prom={st.get('promedio_gwh', 0):.1f}")
        else:
            print(f"  ⚠️ {metric_name}: sin datos")
    predicciones_data = predicciones_lista[0] if predicciones_lista else {}
    print(f"  Total predicciones obtenidas: {len(predicciones_lista)}")

    # ── 3. Generar gráficos ──
    chart_paths = []
    try:
        from whatsapp_bot.services.informe_charts import generate_all_informe_charts
        charts = generate_all_informe_charts()
        for key in ('generacion', 'embalses', 'precios'):
            path = charts.get(key, (None,))[0]
            if path and os.path.isfile(path):
                chart_paths.append(path)
        print(f"  Gráficos: {len(chart_paths)}")
    except Exception as e:
        print(f"  ⚠️ Gráficos no disponibles: {e}")

    # ── 4. Generar PDF ──
    pdf_path = None
    try:
        from domain.services.report_service import generar_pdf_informe
        pdf_path = generar_pdf_informe(
            informe_texto, fecha_generacion, generado_con_ia,
            chart_paths=chart_paths,
            fichas=fichas_kpi,
            predicciones=predicciones_lista or predicciones_data,
            anomalias=[],
            noticias=noticias,
        )
        if pdf_path:
            size_kb = os.path.getsize(pdf_path) / 1024
            print(f"  ✅ PDF generado: {pdf_path} ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"  ⚠️ Error generando PDF: {e}")

    # ── 5. Construir mensaje Telegram ──
    tg_message = (
        f"📊 *INFORME EJECUTIVO — TEST DE CAMBIOS*\n\n"
        f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"🔧 _Prueba de cambios: embalses + predicciones mes_\n\n"
    )
    if fichas_kpi:
        for f in fichas_kpi[:3]:
            emoji = f.get('emoji', '⚡')
            ind = f.get('indicador', '')
            val = f.get('valor', '')
            uni = f.get('unidad', '')
            ctx = f.get('contexto', {})
            var_pct = ctx.get('variacion_vs_promedio_pct', '')
            etiqueta_var = ctx.get('etiqueta_variacion', 'vs 7d')
            tg_message += f"{emoji} *{ind}:* {val} {uni}"
            if isinstance(var_pct, (int, float)):
                tg_message += f" ({var_pct:+.1f}% {etiqueta_var})"
            tg_message += "\n"

            # Si es embalses, mostrar los campos nuevos
            if 'embalse' in ind.lower():
                media_h = ctx.get('media_historica_2020_2025')
                desv_h = ctx.get('desviacion_pct_media_historica_2020_2025')
                if media_h is not None and desv_h is not None:
                    dir_txt = "por encima" if desv_h >= 0 else "por debajo"
                    tg_message += (
                        f"   📊 Media 2020-2025: {media_h:.1f}% → "
                        f"*{abs(desv_h):.1f}% {dir_txt}*\n"
                    )
        tg_message += "\n"

    # Resumen narrativo (recortado + limpio para Telegram)
    narrative_short = _clean_markdown_for_telegram(informe_texto[:1500])
    if len(narrative_short) > 1500:
        narrative_short = narrative_short[:1497] + '...'
    tg_message += f"{narrative_short}\n\n"
    tg_message += "_Portal Energético — TEST de cambios_"

    if len(tg_message) > 4000:
        tg_message = tg_message[:3900] + "\n\n_(recortado)_"

    # ── 6. Enviar SOLO a Melissa (Telegram) ──
    print(f"\n📤 Enviando a Telegram chat_id={DEST_CHAT_ID}...")
    try:
        from domain.services.notification_service import _get_telegram_token
        import httpx

        token = _get_telegram_token()
        if token:
            base = f"https://api.telegram.org/bot{token}"
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{base}/sendMessage",
                    json={
                        "chat_id": DEST_CHAT_ID,
                        "text": tg_message,
                        "parse_mode": "Markdown",
                    },
                )
                if resp.status_code == 200:
                    print(f"  ✅ Mensaje Telegram enviado")
                else:
                    print(f"  ❌ Telegram error: {resp.status_code} {resp.text[:200]}")

                if pdf_path and os.path.isfile(pdf_path):
                    with open(pdf_path, 'rb') as f:
                        resp_doc = client.post(
                            f"{base}/sendDocument",
                            data={
                                "chat_id": str(DEST_CHAT_ID),
                                "caption": "📎 Informe Ejecutivo — TEST cambios embalses + predicciones",
                            },
                            files={"document": (os.path.basename(pdf_path), f, "application/pdf")},
                        )
                        if resp_doc.status_code == 200:
                            print(f"  ✅ PDF enviado por Telegram")
                        else:
                            print(f"  ❌ PDF Telegram error: {resp_doc.status_code}")
        else:
            print("  ❌ TELEGRAM_BOT_TOKEN no configurado")
    except Exception as e:
        print(f"  ❌ Error Telegram: {e}")

    # ── 7. Enviar SOLO a mjcardona (Email) ──
    print(f"\n📧 Enviando email a {DEST_EMAIL}...")
    try:
        from domain.services.notification_service import send_email, build_daily_email_html
        email_html = build_daily_email_html(
            informe_texto,
            noticias=noticias,
            fichas=fichas_kpi,
            predicciones=predicciones_lista or predicciones_data,
            anomalias=[],
            generado_con_ia=generado_con_ia,
        )
        result = send_email(
            to_list=[DEST_EMAIL],
            subject=f"📊 Informe Ejecutivo (TEST) — {datetime.now().strftime('%Y-%m-%d')}",
            body_html=email_html,
            pdf_path=pdf_path,
        )
        print(f"  Email resultado: {result}")
    except Exception as e:
        print(f"  ❌ Error email: {e}")

    # ── Limpieza ──
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

    print("\n✅ TEST completado.")


if __name__ == '__main__':
    main()
