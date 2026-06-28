#!/usr/bin/env python3
"""
PROYECCION_HIDROLOGIA_COMPLETA_V3.pdf
Revisión integral con honestidad técnica. PyMuPDF 1.27.1.
API: append() requiere fitz.Font object; write_text() aplica color.
"""

import fitz
from pathlib import Path

OUTPUT = Path("/home/admonctrlxm/server/docs/predicciones/PROYECCION_HIDROLOGIA_COMPLETA_V3.pdf")

# Font objects (reusables)
F = fitz.Font("helv")
FB = fitz.Font("hebo")
FI = fitz.Font("heit")

# Colores
C_TITLE = (0.0, 0.25, 0.45)
C_BODY = (0.15, 0.15, 0.15)
C_ACCENT = (0.8, 0.25, 0.15)
C_OK = (0.15, 0.5, 0.25)
C_WARN = (0.75, 0.45, 0.1)
C_GRAY = (0.5, 0.5, 0.5)
C_LIGHT = (0.7, 0.7, 0.7)
C_BOX_BG = (0.98, 0.98, 0.98)
C_BOX_BORDER = (0.7, 0.7, 0.7)
C_HIGHLIGHT_BG = (0.95, 0.92, 0.85)
C_HIGHLIGHT_BORDER = (0.6, 0.5, 0.3)
C_WHITE = (1, 1, 1)
C_NEAR_WHITE = (0.97, 0.97, 0.97)
C_ALERT_BG = (1, 0.97, 0.93)
C_SUBTITLE = (0.2, 0.4, 0.6)

PAGE_W, PAGE_H = 595, 842
MARGIN = 50
TEXT_W = PAGE_W - 2 * MARGIN

# Datos reales del sistema
REAL_MAPE_EMB_PCT_MIN = 1.4
REAL_MAPE_EMB_PCT_MAX = 31.9
REAL_MAPE_EMB_PCT_AVG = 7.3
REAL_MAPE_HIDRAULICA_AVG = 32.8
REAL_MAPE_DEMANDA_AVG = 4.1
REAL_MAPE_SOLAR_AVG = 13.1
REAL_MAPE_EOLICA_AVG = 38.2
REAL_MAPE_PRECIO_AVG = 35.9
EMBALSE_ACTUAL = 74.3
META_XM = 80.0
PREDICCION_AGOSTO = 77.31


def tw_write(page, texts, color=C_BODY):
    """texts = [(x, y, text, font_obj, fontsize), ...]"""
    tw = fitz.TextWriter(page.rect)
    for x, y, text, font_obj, fontsize in texts:
        tw.append((x, y), text, font=font_obj, fontsize=fontsize)
    tw.write_text(page, color=color)


def draw_rect(page, x, y, w, h, fill, stroke, width=0.5):
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(x, y, x + w, y + h))
    shape.finish(color=stroke, fill=fill, width=width)
    shape.commit()


def draw_line(page, x1, y1, x2, y2, color=C_LIGHT, width=0.5):
    shape = page.new_shape()
    shape.draw_line((x1, y1), (x2, y2))
    shape.finish(color=color, width=width)
    shape.commit()


def text_len(text, fontname_str, fontsize):
    return fitz.get_text_length(text, fontname=fontname_str, fontsize=fontsize)


def text_wrap(page, x, y, w, text, font_obj, fontname_str, fontsize, color, line_h):
    words = text.split()
    line = ""
    cy = y
    for word in words:
        test = line + " " + word if line else word
        if text_len(test, fontname_str, fontsize) > w:
            tw = fitz.TextWriter(page.rect)
            tw.append((x, cy), line, font=font_obj, fontsize=fontsize)
            tw.write_text(page, color=color)
            cy += line_h
            line = word
        else:
            line = test
    if line:
        tw = fitz.TextWriter(page.rect)
        tw.append((x, cy), line, font=font_obj, fontsize=fontsize)
        tw.write_text(page, color=color)
        cy += line_h
    return cy


def bullet_list(page, x, y, w, items, font_obj, fontname_str, fontsize, color, line_h, bullet="•"):
    cy = y
    for item in items:
        text = f"{bullet} {item}"
        words = text.split()
        line = ""
        first = True
        for word in words:
            indent = 12 if not first else 0
            test = line + " " + word if line else word
            if text_len(test, fontname_str, fontsize) > w - indent:
                tw = fitz.TextWriter(page.rect)
                tw.append((x + indent, cy), line, font=font_obj, fontsize=fontsize)
                tw.write_text(page, color=color)
                cy += line_h
                line = word
                first = False
            else:
                line = test
        if line:
            tw = fitz.TextWriter(page.rect)
            indent = 12 if not first else 0
            tw.append((x + indent, cy), line, font=font_obj, fontsize=fontsize)
            tw.write_text(page, color=color)
            cy += line_h
    return cy


def draw_highlight_box(page, x, y, w, text_lines, title=None, font_obj=F, fontname_str="helv", fontsize=9, line_h=13):
    n_lines = len(text_lines)
    h = (n_lines + (2 if title else 0)) * line_h + 12
    draw_rect(page, x, y, w, h, C_HIGHLIGHT_BG, C_HIGHLIGHT_BORDER)
    cy = y + 8
    if title:
        tw = fitz.TextWriter(page.rect)
        tw.append((x + 8, cy), title, font=FB, fontsize=fontsize + 1)
        tw.write_text(page, color=C_HIGHLIGHT_BORDER)
        cy += line_h + 2
    for line in text_lines:
        tw = fitz.TextWriter(page.rect)
        tw.append((x + 8, cy), line, font=font_obj, fontsize=fontsize)
        tw.write_text(page, color=C_BODY)
        cy += line_h
    return y + h + 5


def footer(page, num, total=13):
    tw_write(page, [
        (MARGIN, PAGE_H - 30, "Documento técnico — 22/06/2026  |  Portal Energético MME — Sistema de Predicciones ML", F, 8),
        (PAGE_W - MARGIN - 50, PAGE_H - 30, f"Página {num}/{total}", F, 8),
    ], C_GRAY)


def page_header(page, title, num):
    y = 35
    tw_write(page, [(MARGIN, y, "PORTAL ENERGÉTICO MME — SISTEMA DE PREDICCIONES ML", F, 8)], C_GRAY)
    tw_write(page, [(PAGE_W - MARGIN - 50, y, f"Página {num}/13", F, 8)], C_GRAY)
    draw_line(page, MARGIN, 48, PAGE_W - MARGIN, 48)
    y = 70
    tw_write(page, [(MARGIN, y, title, FB, 16)], C_TITLE)
    return 95


# ═══════════════════════════════════════════════════════════════════════════
# DOCUMENTO
# ═══════════════════════════════════════════════════════════════════════════
doc = fitz.open()

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 1: PORTADA
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
shape = page.new_shape()
shape.draw_rect(fitz.Rect(0, 0, PAGE_W, 200))
shape.finish(color=C_TITLE, fill=C_TITLE)
shape.commit()
shape = page.new_shape()
shape.draw_rect(fitz.Rect(0, 200, PAGE_W, 208))
shape.finish(color=C_ACCENT, fill=C_ACCENT)
shape.commit()

tw_write(page, [
    (MARGIN, 80, "PROYECCIÓN HIDROLÓGICA", FB, 28),
    (MARGIN, 115, "Sistema de Predicciones ML del Portal Energético", F, 14),
    (MARGIN, 140, "Análisis técnico honesto: qué hace el modelo hoy,", FI, 11),
    (MARGIN, 158, "qué no puede hacer, y qué investigación propone para el futuro", FI, 11),
], C_WHITE)

y = 230
draw_rect(page, MARGIN, y, TEXT_W, 165, C_BOX_BG, C_BOX_BORDER)
tw_write(page, [(MARGIN + 10, y + 18, "CONTEXTO DEL ANÁLISIS", FB, 12)], C_TITLE)

card_w = (TEXT_W - 20) / 3
yc = y + 40
labels = [
    ("Fecha de análisis", "Junio 2026", C_BODY),
    ("Fenómeno evaluado", "El Niño >95%", C_ACCENT),
    ("Horizonte", "31 agosto 2026", C_BODY),
    ("Meta XM", f"{META_XM}% útil", C_OK),
    ("Estado actual (20 jun)", f"{EMBALSE_ACTUAL}%", C_ACCENT),
    ("Predicción modelo", f"{PREDICCION_AGOSTO}%", C_WARN),
]
for i, (label, value, color) in enumerate(labels):
    cx = MARGIN + 10 + (i % 3) * (card_w + 5)
    cy_card = yc + (i // 3) * 60
    draw_rect(page, cx, cy_card, card_w, 50, C_WHITE, C_BOX_BORDER)
    tw_write(page, [(cx + 8, cy_card + 12, label, F, 8)], C_GRAY)
    tw_write(page, [(cx + 8, cy_card + 30, value, FB, 13)], color)

y = 410
draw_rect(page, MARGIN, y, TEXT_W, 75, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 16, "RESULTADO CLAVE", FB, 11),
    (MARGIN + 10, y + 36, f"El modelo Prophet + ARIMA predice {PREDICCION_AGOSTO}% para el 31 de agosto 2026.", F, 10),
    (MARGIN + 10, y + 52, "Recuperación de +3.5 pp, pero NO alcanza la meta del 80%. La proyección IDEAM reduce probabilidades.", F, 10),
], C_ACCENT)

y = 500
draw_rect(page, MARGIN, y, TEXT_W, 70, C_HIGHLIGHT_BG, C_HIGHLIGHT_BORDER)
tw_write(page, [
    (MARGIN + 10, y + 16, "NOTA DE HONESTIDAD TÉCNICA", FB, 11),
    (MARGIN + 10, y + 34, "Este documento usa datos reales del sistema de predicciones del Portal Energético MME.", F, 9),
    (MARGIN + 10, y + 48, "Los errores (MAPE) provienen de la base de datos de producción. Cuando no sabemos algo, lo decimos.", F, 9),
    (MARGIN + 10, y + 62, "Cuando el sistema tiene una limitación, la admitimos. No inventamos números para lucir mejor.", F, 9),
    (MARGIN + 10, y + 76, "Si encuentra un término técnico que no entiende, consulte el Glosario en la página 13.", FI, 9),
], C_HIGHLIGHT_BORDER)

y = 590
tw_write(page, [(MARGIN, y, "CONTENIDO", FB, 14)], C_TITLE)
contenido = [
    "1. ¿Qué es un modelo de Machine Learning? ............................................................. 2",
    "2. ¿Qué modelo usa el Portal Energético hoy? .......................................................... 3",
    "3. ¿Cómo se entrena y con qué frecuencia? .............................................................. 4",
    "4. ¿Qué tan bueno es? — Datos reales de error (MAPE) .......................................... 5",
    "5. ¿Por qué este modelo y no otro? ........................................................................... 6",
    "6. Errores del modelo: qué NO puede hacer hoy ...................................................... 7",
    "7. Propuesta de investigación: PINN-LSTM (futuro) .............................................. 8",
    "8. Función de pérdida híbrida y calibración conformal ......................................... 9",
    "9. Análisis de sensibilidad inversa .......................................................................... 10",
    "10. Resultados esperados y beneficios .................................................................. 11",
    "11. Conclusiones y recomendaciones ....................................................................... 12",
    "Apéndice: Glosario de términos técnicos ................................................................. 13",
]
yc = y + 22
for line in contenido:
    tw = fitz.TextWriter(page.rect)
    tw.append((MARGIN, yc), line, font=F, fontsize=9)
    tw.write_text(page, color=C_BODY)
    yc += 14

footer(page, 1)
print("Página 1 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 2: ¿QUÉ ES ML?
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "1. ¿QUÉ ES UN MODELO DE MACHINE LEARNING?", 2)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Un modelo de Machine Learning (ML) es un programa de computador que aprende patrones a partir de datos históricos para hacer predicciones sobre el futuro. A diferencia de una calculadora o una hoja de Excel, donde una persona escribe las reglas, en el ML el programa descubre las reglas por sí mismo.",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "Ejemplo sencillo: imagine que le muestra a un niño 100 fotos de perros y 100 de gatos.",
    "Al principio el niño confunde algunos, pero con el tiempo aprende a distinguirlos.",
    "Un modelo de ML hace exactamente eso, pero con números: le muestra datos históricos",
    "de embalses, generación, demanda — y aprende a predecir qué pasará mañana."
], title="PARA ENTENDERLO SIN SER EXPERTO")

y += 10
tw_write(page, [(MARGIN, y, "1.1 ¿Qué tipos de modelos usa el Portal Energético?", FB, 12)], C_SUBTITLE)
y += 20

modelos = [
    ("PROPHET (Meta/Facebook)", "Modelo de series temporales que descompone los datos en: tendencia + estacionalidad + eventos especiales. Maneja bien datos faltantes.", "Embalses, biomasa (series con estacionalidad anual)"),
    ("ARIMA estacional (Auto-ARIMA)", "Modelo estadístico clásico que encuentra automáticamente los mejores parámetros. Captura dependencias de corto plazo.", "Térmica, eólica (series con autocorrelación)"),
    ("ENSEMBLE (combinación)", "Mezcla las predicciones de Prophet y ARIMA dándole más peso al que ha tenido mejor desempeño recientemente. La idea es que 'dos cabezas piensan mejor que una'.", "Embalses (la combinación supera a cada modelo solo)"),
]
for nombre, desc, uso in modelos:
    draw_rect(page, MARGIN, y, TEXT_W, 55, C_NEAR_WHITE, C_BOX_BORDER)
    tw_write(page, [
        (MARGIN + 8, y + 12, nombre, FB, 10),
        (MARGIN + 8, y + 26, desc, F, 9),
        (MARGIN + 8, y + 40, f"Uso en el Portal: {uso}", FI, 8),
    ], C_BODY)
    y += 62

y += 5
draw_rect(page, MARGIN, y, TEXT_W, 50, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "NOTA IMPORTANTE", FB, 10),
    (MARGIN + 10, y + 28, "LightGBM NO es un modelo de predicción en nuestro sistema. Es una herramienta auxiliar que se usa", F, 9),
    (MARGIN + 10, y + 40, "DENTRO del proceso de calibración de intervalos de confianza (explicado en la página 9).", F, 9),
], C_ACCENT)

footer(page, 2)
print("Página 2 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 3: ¿QUÉ MODELO USA EL PORTAL HOY?
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "2. ¿QUÉ MODELO USA EL PORTAL ENERGÉTICO HOY?", 3)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El Portal Energético del MME usa un modelo ENSEMBLE (pronunciado 'onsámbel', del francés 'conjunto'): combina las predicciones de Prophet y ARIMA estacional. No es un modelo 'preentrenado' como GPT-4. Se entrena desde cero con datos del Sistema Interconectado Nacional (SIN) de Colombia cada 3 días.",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "¿Qué significa 'preentrenado'? GPT-4 es preentrenado: ya leyó internet antes de que usted lo use.",
    "Nuestro modelo NO es así. Cada 3 días 'olvida' lo anterior y vuelve a aprender desde cero",
    "con los datos más recientes de XM (2020-2026) y backfill histórico (2000-2019).",
    "Esto es una ventaja: se adapta a cambios. Y una desventaja: no acumula 'memoria' de eventos raros."
], title="DIFERENCIA CLAVE: PREENTRENADO vs REENTRENADO")

y += 10
tw_write(page, [(MARGIN, y, "2.1 ¿Qué datos usa el modelo?", FB, 12)], C_SUBTITLE)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El modelo solo ve UNA cosa: la serie temporal de la variable que quiere predecir. Por ejemplo, para embalses solo ve los valores históricos de porcentaje de capacidad útil. No ve el índice ONI (El Niño), no ve precipitaciones del IDEAM, no ve caudales de ríos. Esto es intencional para mantenerlo simple, pero es una limitación que explicaremos en la página 7.",
    F, "helv", 10, C_BODY, 16)

y += 10
draw_rect(page, MARGIN, y, TEXT_W, 80, C_NEAR_WHITE, C_BOX_BORDER)
tw_write(page, [
    (MARGIN + 8, y + 12, "DATOS DE ENTRADA ACTUALES", FB, 10),
    (MARGIN + 8, y + 28, "• Serie temporal de la métrica a predecir (ej: PorcVoluUtilDiar para embalses)", F, 9),
    (MARGIN + 8, y + 42, "• Rango: últimos 365-730 días de datos históricos de la base PostgreSQL", F, 9),
    (MARGIN + 8, y + 56, "• Frecuencia: diaria (algunas métricas son horarias, pero el modelo agrupa a diario)", F, 9),
    (MARGIN + 8, y + 70, "• NO usa variables exógenas: ni ONI, ni precipitación, ni irradiancia solar, ni viento", F, 9),
], C_BODY)

y += 95
y = text_wrap(page, MARGIN, y, TEXT_W,
    "El modelo hace una predicción puntual (un número para cada día futuro) y un intervalo de confianza (un rango donde cree que estará el valor real). El intervalo se calibra con una técnica llamada 'predicción conformal' que explicamos en la página 9.",
    F, "helv", 10, C_BODY, 16)

y += 5
draw_rect(page, MARGIN, y, TEXT_W, 45, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "ADVERTENCIA", FB, 10),
    (MARGIN + 10, y + 28, "El PDF anterior (V2) decía que LightGBM predice 'demanda, precio bolsa, solar, eólica'. Eso es incorrecto.", F, 9),
    (MARGIN + 10, y + 40, "LightGBM solo calibra intervalos. Las predicciones las hacen Prophet y ARIMA.", F, 9),
], C_ACCENT)

footer(page, 3)
print("Página 3 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 4: PIPELINE DE ENTRENAMIENTO
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "3. ¿CÓMO SE ENTRENA Y CON QUÉ FRECUENCIA?", 4)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El sistema se reentrena automáticamente cada 3 días (domingo, miércoles, sábado a las 2:00 AM) mediante Celery Beat, un programador automático de tareas que corre en el servidor sin intervención humana. El pipeline completo toma entre 18 y 25 minutos.",
    F, "helv", 10, C_BODY, 16)

y += 10
tw_write(page, [(MARGIN, y, "3.1 Pasos del pipeline (del código real)", FB, 12)], C_SUBTITLE)
y += 18

pasos = [
    ("PASO 1: CARGA DE DATOS (3-5 segundos)", "Query a PostgreSQL: SELECT fecha, valor_gwh FROM metrics WHERE metrica = 'PorcVoluUtilDiar' AND entidad = 'Sistema'. Rango: últimos 365-730 días."),
    ("PASO 2: PREPARACIÓN (1-2 segundos)", "Interpolación de fechas faltantes, winsorización (recorte de valores extremos que superan 3 desviaciones estándar), formateo para Prophet (columnas 'ds' y 'y') y ARIMA (índice temporal)."),
    ("PASO 3: ENTRENAMIENTO PARALELO (3-5 minutos)", "Prophet: optimización MAP (30-60 segundos). ARIMA: búsqueda stepwise de parámetros (2-3 minutos). Validación hold-out: se reservan los últimos 30 días como 'prueba final' que el modelo NO ve durante entrenamiento, para medir qué tan bien generaliza."),
    ("PASO 4: COMBINACIÓN ENSEMBLE (segundos)", "Carga pesos dinámicos de predictions_quality_history. Si no hay historial, usa 50/50. Promedio ponderado de predicciones."),
    ("PASO 5: CALIBRACIÓN CONFORMAL (10-20 segundos)", "Entrena LightGBM auxiliar sobre características del calendario (día del año, día de semana, mes). Calcula scores de calibración. Ajusta intervalos de confianza. Garantía: cobertura ≥ nivel de confianza."),
    ("PASO 6: ALMACENAMIENTO (segundos)", "INSERT 450 registros (90 días × 5 fuentes) con UPSERT en PostgreSQL. Invalidación automática de caché Redis (TTL 1 hora)."),
]
for titulo, desc in pasos:
    draw_rect(page, MARGIN, y, TEXT_W, 48, C_NEAR_WHITE, C_BOX_BORDER)
    tw_write(page, [
        (MARGIN + 8, y + 10, titulo, FB, 9),
        (MARGIN + 8, y + 24, desc, F, 8),
    ], C_BODY)
    y += 55

y += 5
draw_highlight_box(page, MARGIN, y, TEXT_W, [
    "¿Por qué cada 3 días y no cada día? Porque los datos de XM no cambian drásticamente",
    "diariamente y el reentrenamiento consume recursos del servidor. Cada 3 días es un",
    "balance entre frescura del modelo y eficiencia computacional."
], title="FRECUENCIA DE REENTRENAMIENTO")

footer(page, 4)
print("Página 4 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 5: DATOS REALES DE ERROR (MAPE)
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "4. ¿QUÉ TAN BUENO ES? — DATOS REALES DE ERROR", 5)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "A continuación presentamos los errores reales del sistema, extraídos de la base de datos de producción (tabla predictions_quality_history) en junio de 2026. El error se mide con MAPE: Error Porcentual Absoluto Medio. Un MAPE de 5% significa que, en promedio, el modelo se equivoca en 5% del valor real.",
    F, "helv", 10, C_BODY, 16)

y += 10
tw_write(page, [(MARGIN, y, "4.1 MAPE real por fuente energética (datos de producción)", FB, 12)], C_SUBTITLE)
y += 18

# Tabla de MAPEs reales
encabezados = ["Fuente energética", "MAPE promedio", "MAPE mínimo", "MAPE máximo", "Evaluaciones"]
col_w = [TEXT_W * 0.30, TEXT_W * 0.18, TEXT_W * 0.18, TEXT_W * 0.18, TEXT_W * 0.16]
xs = [MARGIN]
for w in col_w[:-1]:
    xs.append(xs[-1] + w)

# Header tabla
row_h = 22
draw_rect(page, MARGIN, y, TEXT_W, row_h, C_TITLE, C_TITLE)
for i, h in enumerate(encabezados):
    tw_write(page, [(xs[i] + 5, y + 14, h, FB, 8)], C_WHITE)
y += row_h

# Filas
datos_mape = [
    ("Embalses (%)", f"{REAL_MAPE_EMB_PCT_AVG}%", f"{REAL_MAPE_EMB_PCT_MIN}%", f"{REAL_MAPE_EMB_PCT_MAX}%", "31"),
    ("Demanda", f"{REAL_MAPE_DEMANDA_AVG}%", "0.6%", "26.4%", "20"),
    ("Solar", f"{REAL_MAPE_SOLAR_AVG}%", "1.8%", "62.9%", "18"),
    ("Hidráulica", f"{REAL_MAPE_HIDRAULICA_AVG}%", "2.5%", "48.1%", "135"),
    ("Eólica", f"{REAL_MAPE_EOLICA_AVG}%", "9.1%", "91.1%", "17"),
    ("Precio Bolsa", f"{REAL_MAPE_PRECIO_AVG}%", "9.2%", "58.5%", "17"),
]
for fuente, prom, minv, maxv, n in datos_mape:
    draw_rect(page, MARGIN, y, TEXT_W, row_h, C_NEAR_WHITE, C_BOX_BORDER)
    vals = [fuente, prom, minv, maxv, n]
    for i, v in enumerate(vals):
        tw_write(page, [(xs[i] + 5, y + 14, v, F if i > 0 else FB, 8)], C_BODY)
    y += row_h

y += 10
draw_highlight_box(page, MARGIN, y, TEXT_W, [
    "¿Qué significa esto? Los embalses tienen un MAPE promedio de 7.3%, pero ha llegado",
    "hasta 31.9% en momentos de crisis (probablemente El Niño 2023-2024). La demanda",
    "parece tener buen MAPE (4.1%), pero tiene outliers extremos que filtramos porque",
    "indican problemas de datos, no del modelo. La eólica es la más difícil: 38.2% de error."
], title="INTERPRETACIÓN HONESTA DE LOS DATOS")

y += 10
y = text_wrap(page, MARGIN, y, TEXT_W,
    "El PDF anterior (V2) decía 'MAPE 3.2% para embalses' como si fuera un hecho estable. La realidad es que el MAPE varía según la época del año, la condición climática, y la calidad de los datos de entrada. Presentar un solo número es engañoso. Presentamos el rango completo.",
    F, "helv", 10, C_BODY, 16)

y += 5
draw_rect(page, MARGIN, y, TEXT_W, 50, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "TRANSPARENCIA", FB, 10),
    (MARGIN + 10, y + 28, "No tenemos un benchmark de validación cruzada temporal riguroso. Los MAPEs son ex-post:", F, 9),
    (MARGIN + 10, y + 40, "se calculan DESPUÉS de que pasa el día, comparando predicción vs valor real. Esto es útil pero no", F, 9),
    (MARGIN + 10, y + 52, "equivalente a un test de laboratorio controlado. Lo admitimos.", F, 9),
], C_ACCENT)

footer(page, 5)
print("Página 5 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 6: ¿POR QUÉ ESTE MODELO?
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "5. ¿POR QUÉ ESTE MODELO Y NO OTRO?", 6)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "La elección de Prophet + ARIMA ensemble no fue arbitraria. Se evaluaron múltiples modelos y se eligió este porque ofrece el mejor balance entre precisión, interpretabilidad, velocidad y robustez ante datos faltantes (comunes en datos de XM).",
    F, "helv", 10, C_BODY, 16)

y += 10
tw_write(page, [(MARGIN, y, "5.1 Comparativa honesta de modelos evaluados", FB, 12)], C_SUBTITLE)
y += 18

# Tabla comparativa
encabezados2 = ["Modelo", "MAPE real", "Tiempo", "Fortalezas", "Debilidades"]
col_w2 = [TEXT_W * 0.18, TEXT_W * 0.12, TEXT_W * 0.12, TEXT_W * 0.30, TEXT_W * 0.28]
xs2 = [MARGIN]
for w in col_w2[:-1]:
    xs2.append(xs2[-1] + w)

draw_rect(page, MARGIN, y, TEXT_W, row_h, C_TITLE, C_TITLE)
for i, h in enumerate(encabezados2):
    tw_write(page, [(xs2[i] + 5, y + 14, h, FB, 8)], C_WHITE)
y += row_h

comparativa = [
    ("Prophet", "3.5-7%", "30-60s", "Estacionalidad, changepoints, datos faltantes", "Cambios abruptos no previstos"),
    ("ARIMA est.", "4-32%", "2-3min", "Autocorrelación, IC estadísticos", "Requiere estacionariedad: que la serie no cambie de comportamiento drásticamente con el tiempo (ej: si antes variaba entre 70-80% y ahora varía entre 40-50%, no es estacionaria)"),
    ("Ensemble", "1.4-32%", "3-5min", "Combina fortalezas, pesos dinámicos", "Más complejo de mantener"),
    ("LSTM", "No probado", "30-60min", "Patrones complejos teóricos", "Requiere 10,000+ datos, GPU"),
    ("XGBoost", "No probado", "45-90s", "Robusto a outliers teórico", "No captura temporalidad"),
]
for modelo, mape, tiempo, fort, deb in comparativa:
    draw_rect(page, MARGIN, y, TEXT_W, row_h, C_NEAR_WHITE, C_BOX_BORDER)
    vals = [modelo, mape, tiempo, fort, deb]
    for i, v in enumerate(vals):
        tw_write(page, [(xs2[i] + 5, y + 14, v, F, 8)], C_BODY)
    y += row_h

y += 10
y = text_wrap(page, MARGIN, y, TEXT_W,
    "Nota: Los MAPEs de LSTM y XGBoost dicen 'No probado' porque el sistema actual no los ejecuta en producción para embalses. Han sido evaluados en experimentos locales pero no integrados al pipeline. El PDF anterior (V2) presentaba números teóricos como si fueran reales. Corregimos eso.",
    F, "helv", 9, C_ACCENT, 14)

y += 10
tw_write(page, [(MARGIN, y, "5.2 ¿Por qué la combinación funciona?", FB, 12)], C_SUBTITLE)
y += 18

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "PROPHET aporta: detección de tendencias de largo plazo, modelado de estacionalidad anual (ciclos de lluvias), manejo de changepoints (cambios de política), tolerancia a datos faltantes.",
    "ARIMA aporta: captura de dependencias de corto plazo, intervalos de confianza con fundamentación estadística, modelado de estacionalidad semanal, corrección por errores previos.",
    "El ensemble aprende: mediante pesos dinámicos inversos al MAPE reciente, da más peso al modelo que ha estado acertando más en los últimos días."
], F, "helv", 9, C_BODY, 14)

y += 5
draw_highlight_box(page, MARGIN, y, TEXT_W, [
    "Fórmula real del código: w_i = (1 / MAPE_i) / sum(1 / MAPE_j)",
    "Si Prophet tuvo MAPE 4% y ARIMA 6%, los pesos serían: Prophet 60%, ARIMA 40%.",
    "Estos pesos se recalculan en cada reentrenamiento. No son fijos."
], title="CÓMO FUNCIONAN LOS PESOS DEL ENSEMBLE")

footer(page, 6)
print("Página 6 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 7: ERRORES DEL MODELO
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "6. ERRORES DEL MODELO: QUÉ NO PUEDE HACER HOY", 7)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Es importante ser honestos: el modelo ensemble Prophet + ARIMA es funcional para condiciones normales, pero tiene limitaciones fundamentales que NO puede superar con la arquitectura actual. Estas limitaciones son inherentes al tipo de modelo y a los datos de entrada.",
    F, "helv", 10, C_BODY, 16)

y += 10
tw_write(page, [(MARGIN, y, "6.1 Error 1: No captura eventos climáticos extremos", FB, 12)], C_ACCENT)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El modelo aprende patrones ESTADÍSTICOS de los datos históricos. Si en los últimos 6 años no ha ocurrido un El Niño intenso comparable al de 2026, el modelo NO tiene información suficiente para anticipar cómo se comportarán los embalses. Asume que el futuro se parece al pasado reciente.",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "El modelo predice 77.31% para agosto 2026 basándose en la estacionalidad histórica.",
    "PERO la proyección climática del IDEAM indica déficit de lluvias en cuencas clave.",
    "El modelo NO incluye el índice ONI (Niño Oscilación del Sur) como variable de entrada.",
    "Resultado: predicción que puede ser optimista y no reflejar el riesgo real del fenómeno."
], title="EJEMPLO CONCRETO: EL NIÑO 2026-2027")

y += 10
tw_write(page, [(MARGIN, y, "6.2 Error 2: No incorpora leyes físicas", FB, 12)], C_ACCENT)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El modelo es puramente estadístico. No conoce la ecuación de potencia hidráulica P = ρgQHη, ni el efecto fotovoltaico, ni el límite de Betz para aerogeneradores. Esto significa que puede generar predicciones físicamente inconsistentes.",
    F, "helv", 10, C_BODY, 16)

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "Puede predecir generación hidráulica alta sin considerar caudales reales.",
    "No respeta el balance de potencia: suma de generaciones ≠ demanda + pérdidas.",
    "No puede identificar configuraciones pre-crisis (umbrales de caudal, ONI, embalses).",
    "Los intervalos de confianza se amplían excesivamente (>50%) para horizontes >90 días."
], F, "helv", 9, C_BODY, 14)

y += 10
tw_write(page, [(MARGIN, y, "6.3 Error 3: Datos de entrada limitados", FB, 12)], C_ACCENT)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El modelo solo utiliza la serie temporal de la variable objetivo como entrada. No incorpora variables climáticas exógenas que mejorarían drásticamente la predicción ante condiciones anómalas.",
    F, "helv", 10, C_BODY, 16)

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "Precipitación IDEAM (cuencas Magdalena, Cauca, Nechí)",
    "Irradiancia solar NASA POWER (Costa Caribe, La Guajira)",
    "Velocidad del viento IDEAM (Alta Guajira, parques eólicos)",
    "Índice ONI (Niño Oscilación del Sur) de NOAA",
    "Caudales afluentes reales (Q en la ecuación hidráulica)"
], F, "helv", 9, C_BODY, 14)

y += 5
draw_rect(page, MARGIN, y, TEXT_W, 45, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "CONCLUSIÓN DE ESTA SECCIÓN", FB, 10),
    (MARGIN + 10, y + 28, "El modelo actual es ADECUADO para condiciones normales. Es INSUFICIENTE para eventos extremos.", F, 9),
    (MARGIN + 10, y + 40, "La siguiente sección propone una línea de investigación para superar estas limitaciones.", F, 9),
], C_ACCENT)

footer(page, 7)
print("Página 7 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 8: PROPUESTA PINN-LSTM
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "7. PROPUESTA DE INVESTIGACIÓN: PINN-LSTM (FUTURO)", 8)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Esta sección describe una PROPUESTA DE INVESTIGACIÓN, no un sistema implementado. Está basada en la tesis de Melissa Cardona (Universidad del Atlántico, 2026) y representa un roadmap técnico para mejorar el sistema en el mediano plazo (12-24 meses).",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "¿Qué es PINN-LSTM? Una red neuronal que combina dos ideas:",
    "• LSTM (Long Short-Term Memory): captura dependencias temporales de largo alcance.",
    "• PINN (Physics-Informed Neural Network): incorpora ecuaciones físicas como restricciones.",
    "La red aprende de los datos PERO también respeta las leyes de la física."
], title="PARA ENTENDERLO SIN SER EXPERTO")

y += 10
tw_write(page, [(MARGIN, y, "7.1 Ecuaciones físicas que incorporaría", FB, 12)], C_SUBTITLE)
y += 18

draw_rect(page, MARGIN, y, TEXT_W, 55, C_NEAR_WHITE, C_BOX_BORDER)
tw_write(page, [
    (MARGIN + 8, y + 10, "HIDROELÉCTRICA: P = ρ · g · Q · H · η", FB, 10),
    (MARGIN + 8, y + 24, "ρ = 1000 kg/m³, g = 9.81 m/s², Q = caudal (m³/s), H = altura hidráulica (m), η = eficiencia (~0.90)", F, 9),
    (MARGIN + 8, y + 38, "La red aprendería que sin caudal (Q ≈ 0), la potencia no puede ser alta.", FI, 8),
], C_BODY)
y += 62

draw_rect(page, MARGIN, y, TEXT_W, 55, C_NEAR_WHITE, C_BOX_BORDER)
tw_write(page, [
    (MARGIN + 8, y + 10, "SOLAR FOTOVOLTAICA: P = η(T) · A · G", FB, 10),
    (MARGIN + 8, y + 24, "η(T) = eficiencia dependiente de temperatura, A = área del panel (m²), G = irradiancia solar (W/m²)", F, 9),
    (MARGIN + 8, y + 38, "La red aprendería que sin irradiancia (G ≈ 0 de noche), la potencia es cero.", FI, 8),
], C_BODY)
y += 62

draw_rect(page, MARGIN, y, TEXT_W, 55, C_NEAR_WHITE, C_BOX_BORDER)
tw_write(page, [
    (MARGIN + 8, y + 10, "EÓLICA: P = Cp · 0.5 · ρ · A · v³", FB, 10),
    (MARGIN + 8, y + 24, "Cp = coeficiente de potencia (≤ 0.593, límite de Betz), v = velocidad del viento (m/s)", F, 9),
    (MARGIN + 8, y + 38, "La red aprendería que la potencia crece con el CUBO del viento, no linealmente.", FI, 8),
], C_BODY)
y += 62

y += 5
draw_rect(page, MARGIN, y, TEXT_W, 50, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "ESTADO ACTUAL DE ESTA INVESTIGACIÓN", FB, 10),
    (MARGIN + 10, y + 28, "Esta propuesta es ACADÉMICA. No hay código implementado en el Portal Energético.", F, 9),
    (MARGIN + 10, y + 40, "Requiere: recolección de datos climáticos, desarrollo de modelo, validación histórica, integración.", F, 9),
], C_ACCENT)

footer(page, 8)
print("Página 8 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 9: FUNCIÓN DE PÉRDIDA Y CALIBRACIÓN CONFORMAL
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "8. FUNCIÓN DE PÉRDIDA HÍBRIDA Y CALIBRACIÓN CONFORMAL", 9)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Esta página explica dos conceptos técnicos que el PDF anterior (V2) omitió o confundió: (1) cómo una PINN aprende respetando la física, y (2) cómo el sistema actual calibra sus intervalos de confianza.",
    F, "helv", 10, C_BODY, 16)

y += 10
tw_write(page, [(MARGIN, y, "8.1 Función de pérdida híbrida (propuesta PINN-LSTM)", FB, 12)], C_SUBTITLE)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "En una red neuronal tradicional, la 'pérdida' mide qué tan lejos está la predicción del valor real. En una PINN, la pérdida tiene DOS componentes: error de predicción + error físico.",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "L_total = L_datos + λ_hidráulico · L_hidráulica + λ_solar · L_solar + λ_eólica · L_eólica + L_regularización",
    "",
    "L_datos: ¿Qué tan lejos está mi predicción del valor real observado?",
    "L_hidráulica: ¿Respeta la ecuación P = ρgQHη? Si predigo P=100MW pero Q=0, hay error físico.",
    "L_regularización: Evita que la red 'memorice' en lugar de 'aprender' (overfitting: cuando el modelo aprende de memoria los datos de entrenamiento pero falla con datos nuevos).",
    "λ (lambda): Pesos que balancean qué tan estricto es cada término. Se ajustan automáticamente mediante gradientes (cambios pequeños en los parámetros que reducen el error)."
], title="DESGLOSE DE LA FUNCIÓN DE PÉRDIDA")

y += 10
tw_write(page, [(MARGIN, y, "8.2 Calibración conformal (SISTEMA ACTUAL)", FB, 12)], C_SUBTITLE)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El sistema actual usa una técnica avanzada llamada Split Conformal Prediction para calibrar los intervalos de confianza. Esto garantiza que, en promedio, el valor real caiga dentro del intervalo al menos el % de veces que prometemos (ej: 90%).",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "¿Cómo funciona? 1) Separa los últimos 60 días de datos como 'calibración'.",
    "2) Entrena un LightGBM auxiliar SOLO sobre features temporales (día del año, día de semana).",
    "3) Calcula el error del LightGBM en esos 60 días: |real - predicho|.",
    "4) El percentil 90 de esos errores (el valor que supera al 90% de los errores, es decir, casi todos) se suma/resta a la predicción del ensemble.",
    "5) Resultado: intervalo [predicción - q, predicción + q] con garantía estadística."
], title="PARA ENTENDERLO SIN SER EXPERTO: CALIBRACIÓN CONFORMAL")

y += 10
y = text_wrap(page, MARGIN, y, TEXT_W,
    "¿Por qué es importante? Sin calibración conformal, los intervalos de Prophet y ARIMA son 'optimistas': prometen 95% de cobertura pero en la práctica cubren menos. La calibración conformal corrige esto usando datos recientes. Es una de las características más técnicamente robustas del sistema actual.",
    F, "helv", 10, C_BODY, 16)

y += 5
draw_rect(page, MARGIN, y, TEXT_W, 45, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "CORRECCIÓN DEL PDF ANTERIOR", FB, 10),
    (MARGIN + 10, y + 28, "El PDF V2 decía que LightGBM predice 'demanda, precio, solar, eólica'. Eso era incorrecto.", F, 9),
    (MARGIN + 10, y + 40, "LightGBM es el modelo AUXILIAR de calibración conformal. No hace predicciones principales.", F, 9),
], C_ACCENT)

footer(page, 9)
print("Página 9 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 10: ANÁLISIS DE SENSIBILIDAD INVERSA
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "9. ANÁLISIS DE SENSIBILIDAD INVERSA", 10)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Esta sección describe una técnica propuesta en la investigación de Melissa Cardona para identificar qué combinaciones de variables llevan a crisis energética. Es conceptual: no está implementada en el sistema actual.",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "¿Qué es la sensibilidad inversa? En lugar de preguntar '¿qué pasará si llueve poco?',",
    "se pregunta: '¿qué condiciones de lluvia, viento, demanda y embalses producen",
    "un déficit de generación mayor al 10%?' Es como 'correr el modelo hacia atrás':",
    "dado un resultado de crisis, ¿qué entradas lo causaron?"
], title="PARA ENTENDERLO SIN SER EXPERTO")

y += 10
tw_write(page, [(MARGIN, y, "9.1 Definición de déficit relativo", FB, 12)], C_SUBTITLE)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Se define el déficit relativo δ como la diferencia entre demanda y generación total, dividida por la demanda. Un δ > 10% podría indicar riesgo de racionamiento. El umbral de crisis τ* se define como el percentil 90 de δ durante episodios históricos de racionamiento (2009-2010, 2015-2016).",
    F, "helv", 10, C_BODY, 16)

y += 10
tw_write(page, [(MARGIN, y, "9.2 Variables de entrada analizadas", FB, 12)], C_SUBTITLE)
y += 18

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "Caudales afluentes Q_t (IDEAM) — variable física determinante",
    "Niveles de embalse agregado (XM)",
    "Índice ONI (NOAA) — señal climática global",
    "Demanda nacional P_dem,t (XM)",
    "Precio de bolsa (XM) — proxy de estrés del sistema",
    "Irradiancia solar G_t (NASA POWER)",
    "Velocidad del viento v_t (IDEAM)"
], F, "helv", 9, C_BODY, 14)

y += 10
tw_write(page, [(MARGIN, y, "9.3 Ranking de sensibilidad", FB, 12)], C_SUBTITLE)
y += 18

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El ranking S_j mide cuánto cambia el déficit cuando cambia cada variable. Identifica los factores desencadenantes de mayor influencia. Por ejemplo, si S_caudal = 0.8 y S_viento = 0.1, el caudal es 8 veces más importante que el viento para predecir crisis.",
    F, "helv", 10, C_BODY, 16)

y += 5
draw_rect(page, MARGIN, y, TEXT_W, 50, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "ESTADO DE IMPLEMENTACIÓN", FB, 10),
    (MARGIN + 10, y + 28, "Este análisis de sensibilidad inversa es PROPUESTA ACADÉMICA. No está codificado en el Portal.", F, 9),
    (MARGIN + 10, y + 40, "Requiere: modelo PINN-LSTM entrenado, datos multivariados, optimizador L-BFGS-B.", F, 9),
], C_ACCENT)

footer(page, 10)
print("Página 10 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 11: RESULTADOS ESPERADOS
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "10. RESULTADOS ESPERADOS Y BENEFICIOS", 11)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Esta sección presenta PROYECCIONES TEÓRICAS de lo que podría lograrse si se implementa la investigación PINN-LSTM. Estos números NO son garantías: son objetivos basados en la literatura científica y la tesis de Melissa Cardona.",
    F, "helv", 10, C_BODY, 16)

y = draw_highlight_box(page, MARGIN, y + 5, TEXT_W, [
    "IMPORTANTE: Los números de esta sección son PROYECCIONES TEÓRICAS.",
    "No provienen de ejecuciones reales del sistema. Son metas de investigación",
    "basadas en resultados publicados en literatura científica sobre PINNs."
], title="ADVERTENCIA SOBRE ESTIMACIONES")

y += 10
tw_write(page, [(MARGIN, y, "10.1 Mejoras cuantitativas proyectadas", FB, 12)], C_SUBTITLE)
y += 18

encabezados3 = ["Métrica", "Sistema actual", "Proyección PINN-LSTM", "Nota"]
col_w3 = [TEXT_W * 0.22, TEXT_W * 0.22, TEXT_W * 0.28, TEXT_W * 0.28]
xs3 = [MARGIN]
for w in col_w3[:-1]:
    xs3.append(xs3[-1] + w)

draw_rect(page, MARGIN, y, TEXT_W, row_h, C_TITLE, C_TITLE)
for i, h in enumerate(encabezados3):
    tw_write(page, [(xs3[i] + 5, y + 14, h, FB, 8)], C_WHITE)
y += row_h

proyecciones = [
    ("MAPE embalses", "1.4% - 31.9%", "< 2.5% (estable)", "Incorporando ONI y caudales"),
    ("MAPE demanda", "0.6% - 26.4%", "< 3% (estable)", "Modelo físico + climático"),
    ("Cobertura IC", "85-90% (estimado)", "90-95% (garantizado)", "Monte Carlo Dropout"),
    ("Horizonte", "90 días (moderado)", "365 días (experimental)", "Con confianza moderada"),
    ("Alerta pre-crisis", "No disponible", "30-90 días", "Umbral configurable"),
]
for met, actual, proj, nota in proyecciones:
    draw_rect(page, MARGIN, y, TEXT_W, row_h, C_NEAR_WHITE, C_BOX_BORDER)
    vals = [met, actual, proj, nota]
    for i, v in enumerate(vals):
        tw_write(page, [(xs3[i] + 5, y + 14, v, F, 8)], C_BODY)
    y += row_h

y += 10
tw_write(page, [(MARGIN, y, "10.2 Mejoras cualitativas", FB, 12)], C_SUBTITLE)
y += 18

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "Predicciones físicamente consistentes: respetan leyes de conservación de energía y masa.",
    "Cuantificación de incertidumbre ante eventos extremos: intervalos bien calibrados para El Niño.",
    "Alertas tempranas basadas en umbrales de variables de entrada (no solo de salida).",
    "Interpretabilidad: el modelo 'sabe' por qué predice lo que predice (gracias a las ecuaciones físicas).",
    "Replicabilidad en sistemas similares: Brasil, Perú, Ecuador, Centroamérica."
], F, "helv", 9, C_BODY, 14)

y += 10
tw_write(page, [(MARGIN, y, "10.3 Impacto en la toma de decisiones", FB, 12)], C_SUBTITLE)
y += 18

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "Planificación del despacho económico con mayor horizonte temporal (de 30 a 90+ días).",
    "Gestión proactiva de reservas hidráulicas: protocolos de conservación antes de la crisis.",
    "Activación temprana de generación térmica de respaldo (menor costo de oportunidad).",
    "Información para políticas públicas de seguridad energética basada en evidencia física.",
    "Reducción del riesgo de racionamiento y sus costos socioeconómicos."
], F, "helv", 9, C_BODY, 14)

footer(page, 11)
print("Página 11 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 12: CONCLUSIONES Y RECOMENDACIONES
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "11. CONCLUSIONES Y RECOMENDACIONES", 12)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "El sistema actual de predicciones ML del Portal Energético (Prophet + ARIMA ensemble con calibración conformal) es funcional y cumple con los requisitos de planificación operativa para condiciones normales. Sin embargo, presenta limitaciones críticas ante eventos climáticos extremos como El Niño, debido a su naturaleza puramente estadística y la ausencia de variables climáticas exógenas.",
    F, "helv", 10, C_BODY, 16)

y += 10
tw_write(page, [(MARGIN, y, "Conclusiones clave", FB, 12)], C_SUBTITLE)
y += 18

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "El modelo actual es ADECUADO para condiciones normales (MAPE embalses 1.4-31.9%, promedio 7.3%).",
    "El modelo actual es INSUFICIENTE para eventos extremos (no captura El Niño, no usa ONI).",
    "La calibración conformal es una fortaleza técnica subestimada del sistema actual.",
    "La propuesta PINN-LSTM es INVESTIGACIÓN FUTURA: requiere 12-24 meses de desarrollo.",
    "La inversión en este modelo representa un seguro contra racionamientos futuros."
], F, "helv", 9, C_BODY, 14)

y += 10
tw_write(page, [(MARGIN, y, "Recomendaciones inmediatas (bajo costo, alto impacto)", FB, 12)], C_SUBTITLE)
y += 18

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "INTEGRAR el índice ONI como regresor en el modelo actual de embalses (costo: bajo, impacto: medio).",
    "INCORPORAR precipitación IDEAM y caudales como variables de entrada (costo: medio, impacto: alto).",
    "DESARROLLAR prototipo PINN-LSTM para una métrica piloto: embalses (costo: alto, impacto: muy alto).",
    "VALIDAR contra episodios históricos: 2009-2010 (racionamiento), 2015-2016 (El Niño fuerte).",
    "ESTABLECER alianza con Universidad del Atlántico (Melissa Cardona) para implementación colaborativa."
], F, "helv", 9, C_BODY, 14)

y += 10
draw_rect(page, MARGIN, y, TEXT_W, 60, C_ALERT_BG, C_ACCENT, 1)
tw_write(page, [
    (MARGIN + 10, y + 12, "MENSAJE FINAL", FB, 11),
    (MARGIN + 10, y + 30, "No necesitamos el modelo perfecto. Necesitamos un modelo que sea honesto sobre sus limitaciones", F, 9),
    (MARGIN + 10, y + 42, "y que mejore continuamente. El sistema actual cumple el primer requisito. La propuesta PINN-LSTM", F, 9),
    (MARGIN + 10, y + 54, "apunta al segundo. Juntos, representan una estrategia de predicción energética robusta y transparente.", F, 9),
], C_ACCENT)

y += 75
tw_write(page, [(MARGIN, y, "Referencias técnicas", FB, 12)], C_SUBTITLE)
y += 18

y = bullet_list(page, MARGIN, y, TEXT_W, [
    "Cardona Navarro, M. (2026). Estudio de la generación de potencia del SIN mediante redes neuronales profundas y validación Monte Carlo. Trabajo de Grado, Programa de Física, Universidad del Atlántico.",
    "Código fuente del sistema: server/domain/services/predictions_service_extended.py",
    "Configuración de tareas: server/tasks/__init__.py (Celery Beat schedule)",
    "Vovk, V., Gammerman, A., & Shafer, G. (2005). Algorithmic Learning in a Random World. Springer. (Conformal Prediction)"
], F, "helv", 8, C_BODY, 13)

footer(page, 12)
print("Página 12 completada")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 13: GLOSARIO
# ═══════════════════════════════════════════════════════════════════════════
page = doc.new_page(width=PAGE_W, height=PAGE_H)
y = page_header(page, "APÉNDICE: GLOSARIO DE TÉRMINOS TÉCNICOS", 13)

y = text_wrap(page, MARGIN, y, TEXT_W,
    "Este glosario explica cada término técnico usado en el documento para que un lector sin conocimiento previo de machine learning o energía pueda entenderlo todo.",
    F, "helv", 10, C_BODY, 16)

y += 10

glosario = [
    ("ARIMA", "AutoRegressive Integrated Moving Average. Modelo estadístico clásico que predice el futuro basándose en valores pasados de la misma serie. 'Auto-regresivo' = usa valores pasados; 'Integrado' = trabaja con diferencias; 'Moving Average' = usa errores pasados."),
    ("Calibración conformal", "Técnica estadística que ajusta los intervalos de confianza para que cumplan su promesa. Si dice '90% de confianza', el valor real cae dentro del intervalo al menos 90% de las veces. Garantía matemática."),
    ("Caudal (Q)", "Volumen de agua que pasa por un punto de un río por unidad de tiempo. Se mide en m³/s. Es la variable más importante para predecir generación hidroeléctrica."),
    ("Ensemble", "Combinación de varios modelos. En nuestro caso: promedio ponderado de Prophet y ARIMA. La idea es que 'dos cabezas piensan mejor que una'."),
    ("Epistémica (incertidumbre)", "Incertidumbre que viene de NO SABER suficiente (pocos datos, modelo imperfecto). Se reduce con más datos o mejor modelo. Diferente de la incertidumbre ALEATORIA (inherente al sistema)."),
    ("Índice ONI", "Oceanic Niño Index. Medida oficial de NOAA que cuantifica la intensidad del fenómeno El Niño. Valores > +1.5 indican El Niño fuerte. Valores < -1.5 indican La Niña."),
    ("LSTM", "Long Short-Term Memory. Tipo de red neuronal que 'recuerda' patrones de largo plazo. Útil para series temporales donde lo que pasó hace 6 meses importa para hoy."),
    ("MAPE", "Mean Absolute Percentage Error. Error Porcentual Absoluto Medio. MAPE = 5% significa que, en promedio, el modelo se equivoca en 5% del valor real."),
    ("PINN", "Physics-Informed Neural Network. Red neuronal que aprende de datos Y respeta ecuaciones físicas. No puede predecir 'agua sin lluvia' porque la física no lo permite."),
    ("Prophet", "Modelo de series temporales desarrollado por Meta (Facebook). Descompone los datos en tendencia + estacionalidad + eventos especiales. Maneja bien datos faltantes."),
    ("Split Conformal Prediction", "Variante de calibración conformal que divide los datos en entrenamiento y calibración. Es la técnica que usa nuestro sistema con LightGBM auxiliar."),
    ("Celery Beat", "Programador automático de tareas que ejecuta procesos en el servidor en horarios definidos. En nuestro caso: reentrena el modelo cada 3 días a las 2:00 AM."),
    ("Hold-out", "Técnica de validación: se reserva una parte de los datos (ej: últimos 30 días) para probar el modelo DESPUÉS de entrenarlo. El modelo no ve esos datos durante el entrenamiento."),
    ("Percentil", "Valor que divide un conjunto de datos en porcentajes. El percentil 90 es el valor que supera al 90% de los datos. Ej: si el percentil 90 del error es 5%, el 90% de los errores son menores a 5%."),
    ("Overfitting", "Cuando un modelo aprende de memoria los datos de entrenamiento pero falla al predecir datos nuevos. Es como memorizar las respuestas de un examen en lugar de entender la materia."),
    ("Winsorización", "Técnica para manejar valores extremos (outliers): en lugar de eliminarlos, los 'recorta' a un valor máximo razonable (>3 desviaciones estándar)."),
    ("Estacionariedad", "Propiedad de una serie temporal que no cambia su comportamiento estadístico con el tiempo. Si una serie pasa de variar entre 70-80% a variar entre 40-50%, NO es estacionaria."),
]

for termino, definicion in glosario:
    draw_rect(page, MARGIN, y, TEXT_W, 32, C_NEAR_WHITE, C_BOX_BORDER)
    tw_write(page, [(MARGIN + 8, y + 8, termino + ":", FB, 9)], C_TITLE)
    y = text_wrap(page, MARGIN + 8, y + 18, TEXT_W - 16, definicion, F, "helv", 7.5, C_BODY, 11)
    y += 2

footer(page, 13)
print("Página 13 completada")

# Guardar final
doc.save(str(OUTPUT))
print(f"\n✅ PDF generado exitosamente: {OUTPUT}")
print(f"   Total páginas: {len(doc)}")
print(f"   Tamaño archivo: {OUTPUT.stat().st_size / 1024:.1f} KB")

