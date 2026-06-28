#!/usr/bin/env python3
"""
PROYECCION_HIDROLOGIA_COMPLETA_V4.pdf
Generado con ReportLab 5.0 para máxima calidad tipográfica.
Incluye página introductoria de contexto energético.
14 páginas totales.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, KeepTogether, Frame, PageTemplate
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from pathlib import Path

OUTPUT = Path("/home/admonctrlxm/server/docs/predicciones/PROYECCION_HIDROLOGIA_COMPLETA_V4.pdf")

# ─── COLORES ──────────────────────────────────────────────────────────────
C_TITLE = colors.HexColor("#0a3d62")
C_ACCENT = colors.HexColor("#c0392b")
C_OK = colors.HexColor("#27ae60")
C_WARN = colors.HexColor("#e67e22")
C_GRAY = colors.HexColor("#7f8c8d")
C_LIGHT = colors.HexColor("#bdc3c7")
C_BOX_BG = colors.HexColor("#f8f9fa")
C_HIGHLIGHT_BG = colors.HexColor("#fff3cd")
C_HIGHLIGHT_BORDER = colors.HexColor("#856404")
C_ALERT_BG = colors.HexColor("#f8d7da")
C_ALERT_BORDER = colors.HexColor("#721c24")
C_NEAR_WHITE = colors.HexColor("#f4f4f4")
C_BODY = colors.HexColor("#2c3e50")
C_SUBTITLE = colors.HexColor("#2980b9")

# ─── DATOS REALES ─────────────────────────────────────────────────────────
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

# ─── ESTILOS ──────────────────────────────────────────────────────────────
def build_styles():
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name="TitleMain",
        fontSize=28,
        leading=34,
        textColor=C_TITLE,
        spaceAfter=12,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name="TitlePage",
        fontSize=18,
        leading=24,
        textColor=C_TITLE,
        spaceAfter=10,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name="Subtitle",
        fontSize=13,
        leading=17,
        textColor=C_SUBTITLE,
        spaceAfter=8,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name="Body",
        fontSize=10,
        leading=14,
        textColor=C_BODY,
        spaceAfter=8,
        fontName="Helvetica",
        alignment=TA_JUSTIFY,
    ))
    
    styles.add(ParagraphStyle(
        name="BodyBold",
        parent=styles["Body"],
        fontName="Helvetica-Bold",
    ))
    
    styles.add(ParagraphStyle(
        name="HighlightTitle",
        fontSize=10,
        leading=13,
        textColor=C_HIGHLIGHT_BORDER,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    ))
    
    styles.add(ParagraphStyle(
        name="HighlightBody",
        fontSize=9,
        leading=12,
        textColor=C_BODY,
        fontName="Helvetica",
        spaceAfter=3,
    ))
    
    styles.add(ParagraphStyle(
        name="AlertTitle",
        fontSize=10,
        leading=13,
        textColor=C_ALERT_BORDER,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    ))
    
    styles.add(ParagraphStyle(
        name="AlertBody",
        fontSize=9,
        leading=12,
        textColor=C_ALERT_BORDER,
        fontName="Helvetica",
        spaceAfter=3,
    ))
    
    styles.add(ParagraphStyle(
        name="Footer",
        fontSize=8,
        leading=10,
        textColor=C_GRAY,
        fontName="Helvetica",
    ))
    
    styles.add(ParagraphStyle(
        name="CardLabel",
        fontSize=8,
        leading=10,
        textColor=C_GRAY,
        fontName="Helvetica",
    ))
    
    styles.add(ParagraphStyle(
        name="CardValue",
        fontSize=12,
        leading=15,
        textColor=C_BODY,
        fontName="Helvetica-Bold",
    ))
    
    styles.add(ParagraphStyle(
        name="GlosarioTerm",
        fontSize=9,
        leading=12,
        textColor=C_TITLE,
        fontName="Helvetica-Bold",
        spaceAfter=2,
    ))
    
    styles.add(ParagraphStyle(
        name="GlosarioDef",
        fontSize=8,
        leading=11,
        textColor=C_BODY,
        fontName="Helvetica",
        spaceAfter=6,
    ))
    
    return styles


def highlight_box(title, lines):
    """Crea una tabla con fondo amarillo pálido para explicaciones."""
    data = [[Paragraph(f"<b>{title}</b>", ParagraphStyle(name="ht", fontSize=9, leading=12, textColor=C_HIGHLIGHT_BORDER, fontName="Helvetica-Bold"))]]
    for line in lines:
        data.append([Paragraph(line, ParagraphStyle(name="hb", fontSize=9, leading=12, textColor=C_BODY, fontName="Helvetica"))])
    
    t = Table(data, colWidths=[160*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_HIGHLIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, C_HIGHLIGHT_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def alert_box(title, lines):
    """Crea una tabla con fondo rojo pálido para alertas."""
    data = [[Paragraph(f"<b>{title}</b>", ParagraphStyle(name="at", fontSize=9, leading=12, textColor=C_ALERT_BORDER, fontName="Helvetica-Bold"))]]
    for line in lines:
        data.append([Paragraph(line, ParagraphStyle(name="ab", fontSize=9, leading=12, textColor=C_ALERT_BORDER, fontName="Helvetica"))])
    
    t = Table(data, colWidths=[160*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_ALERT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, C_ALERT_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def metric_card(label, value, color=C_BODY):
    """Tarjeta de métrica."""
    data = [
        [Paragraph(label, ParagraphStyle(name="cl", fontSize=7, leading=9, textColor=C_GRAY, fontName="Helvetica"))],
        [Paragraph(f"<b>{value}</b>", ParagraphStyle(name="cv", fontSize=11, leading=14, textColor=color, fontName="Helvetica-Bold"))],
    ]
    t = Table(data, colWidths=[48*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, C_LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def build_table(headers, rows, col_widths):
    """Tabla con estilo profesional."""
    data = [headers] + rows
    t = Table(data, colWidths=col_widths)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_TITLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, C_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_NEAR_WHITE, colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ]
    t.setStyle(TableStyle(style))
    return t


# ─── HEADER/FOOTER ───────────────────────────────────────────────────────
def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(C_GRAY)
    canvas.drawString(20*mm, 280*mm, "PORTAL ENERGÉTICO MME — SISTEMA DE PREDICCIONES ML")
    canvas.drawRightString(190*mm, 280*mm, f"Página {doc.page}/{doc.total_pages}")
    canvas.setStrokeColor(C_LIGHT)
    canvas.line(20*mm, 278*mm, 190*mm, 278*mm)
    canvas.restoreState()


# ═══════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL DOCUMENTO
# ═══════════════════════════════════════════════════════════════════════════
styles = build_styles()

story = []

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 0: CONTEXTO ENERGÉTICO (NUEVA)
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("CONTEXTO ENERGÉTICO COLOMBIANO", styles["TitlePage"]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph(
    "Antes de explicar el modelo de predicción, es necesario entender tres conceptos básicos del sector energético colombiano. Si ya los conoce, puede saltar a la página 2.",
    styles["Body"]
))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>¿Qué es el Sistema Interconectado Nacional (SIN)?</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El SIN es la red eléctrica que conecta a Colombia. Es como una autopista de energía: las plantas generadoras (hidroeléctricas, térmicas, eólicas, solares) 'inyectan' electricidad a la red, y los consumidores (hogares, fábricas, empresas) la 'extraen'. El SIN debe mantener un equilibrio perfecto: la generación debe ser igual a la demanda en todo momento. Si hay más demanda que generación, se producen apagones. Si hay más generación que demanda, se desperdicia energía.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>¿Qué es XM (Operador del Sistema)?</b>", styles["Subtitle"]))
story.append(Paragraph(
    "XM S.A. E.S.P. es la empresa encargada de operar el SIN. Es como el 'controlador de tráfico' de la red eléctrica. XM decide qué plantas generadoras deben encenderse cada hora (despacho económico), cuánto cuesta la energía (precio de bolsa), y cuánta energía hay disponible en los embalses. XM publica datos diarios que el Portal Energético del MME utiliza para entrenar el modelo de predicción.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>¿Qué es un embalse y por qué importa?</b>", styles["Subtitle"]))
story.append(Paragraph(
    "Un embalse es un lago artificial creado al represar un río con una presa. El agua almacenada se usa para generar electricidad en plantas hidroeléctricas. Colombia depende del 65-70% de su electricidad de la hidroelectricidad, por lo que el nivel de los embalses es CRÍTICO para la seguridad energética del país. Cuando los embalses están bajos (por sequía o El Niño), Colombia debe usar generación térmica (más cara y contaminante) o enfrentar racionamientos.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("PARA ENTENDERLO SIN SER EXPERTO", [
    "Imagine que el embalse es una cuenta de ahorros de agua. Durante la época de lluvias (abril-noviembre),",
    "la cuenta se llena (llueve y los ríos llevan agua). Durante la época seca (diciembre-marzo),",
    "se gasta el ahorro (se usa el agua para generar electricidad). Si la cuenta llega a cero,",
    "no hay electricidad hidroeléctrica. El modelo de predicción intenta adivinar cuánto 'ahorro'",
    "quedará en 2-3 meses para que XM pueda planificar con anticipación."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>¿Qué es El Niño y por qué afecta los embalses?</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El Niño es un fenómeno climático que calienta el océano Pacífico y altera los patrones de lluvia en Colombia. Durante El Niño, las lluvias disminuyen en las cuencas hidrográficas clave (Magdalena, Cauca), lo que reduce los aportes de agua a los embalses. Un El Niño 'muy fuerte' puede reducir los niveles de embalse en 20-30 puntos porcentuales, poniendo en riesgo la seguridad energética. El modelo de predicción del Portal Energético intenta anticipar este riesgo.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(alert_box("POR QUÉ ESTE CONTEXTO IMPORTA PARA EL DOCUMENTO", [
    "Sin entender que Colombia depende del 65-70% de hidroelectricidad, no se entiende por qué",
    "predecir embalses es tan importante. Sin entender que XM publica los datos, no se entiende",
    "de dónde vienen los números. Sin entender El Niño, no se entiende por qué el modelo",
    "falla en eventos extremos. Este contexto es el cimiento de todo lo que sigue."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 1: PORTADA
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("PROYECCIÓN HIDROLÓGICA", styles["TitleMain"]))
story.append(Paragraph(
    "<font color='#7f8c8d'>Sistema de Predicciones ML del Portal Energético</font>",
    ParagraphStyle(name="ts", fontSize=13, leading=17, textColor=C_GRAY, fontName="Helvetica", spaceAfter=4)
))
story.append(Paragraph(
    "<i>Análisis técnico honesto: qué hace el modelo hoy, qué no puede hacer, y qué investigación propone para el futuro</i>",
    ParagraphStyle(name="ti", fontSize=10, leading=14, textColor=C_GRAY, fontName="Helvetica-Oblique", spaceAfter=12)
))
story.append(Spacer(1, 4*mm))

# Tarjetas de contexto
row1 = [
    metric_card("Fecha de análisis", "Junio 2026"),
    metric_card("Fenómeno evaluado", "El Niño >95%", C_ACCENT),
    metric_card("Horizonte", "31 agosto 2026"),
]
row2 = [
    metric_card("Meta XM", f"{META_XM}% útil", C_OK),
    metric_card("Estado actual (20 jun)", f"{EMBALSE_ACTUAL}%", C_ACCENT),
    metric_card("Predicción modelo", f"{PREDICCION_AGOSTO}%", C_WARN),
]
t1 = Table([row1, row2], colWidths=[52*mm, 52*mm, 52*mm], hAlign="LEFT")
t1.setStyle(TableStyle([
    ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ("TOPPADDING", (0, 0), (-1, -1), 2),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
]))
story.append(t1)
story.append(Spacer(1, 6*mm))

story.append(alert_box("RESULTADO CLAVE", [
    f"El modelo Prophet + ARIMA predice {PREDICCION_AGOSTO}% para el 31 de agosto 2026.",
    "Recuperación de +3.5 puntos porcentuales, pero NO alcanza la meta del 80%.",
    "La proyección climática del IDEAM reduce aún más las probabilidades de éxito."
]))
story.append(Spacer(1, 4*mm))

story.append(highlight_box("NOTA DE HONESTIDAD TÉCNICA", [
    "Este documento usa datos reales del sistema de predicciones del Portal Energético MME.",
    "Los errores (MAPE) provienen de la base de datos de producción. Cuando no sabemos algo, lo decimos.",
    "Cuando el sistema tiene una limitación, la admitimos. No inventamos números para lucir mejor.",
    "Si encuentra un término técnico que no entiende, consulte el Glosario en la página 14."
]))
story.append(Spacer(1, 6*mm))

story.append(Paragraph("<b>CONTENIDO</b>", styles["Subtitle"]))
contenido_items = [
    "0. Contexto energético colombiano (esta página) .......................................................... 1",
    "1. ¿Qué es un modelo de Machine Learning? ................................................................. 2",
    "2. ¿Qué modelo usa el Portal Energético hoy? .............................................................. 3",
    "3. ¿Cómo se entrena y con qué frecuencia? ............................................................... 4",
    "4. ¿Qué tan bueno es? — Datos reales de error (MAPE) ............................................ 5",
    "5. ¿Por qué este modelo y no otro? ............................................................................. 6",
    "6. Errores del modelo: qué NO puede hacer hoy .................................................... 7",
    "7. Propuesta de investigación: PINN-LSTM (futuro) ............................................. 8",
    "8. Función de pérdida híbrida y calibración conformal ........................................ 9",
    "9. Análisis de sensibilidad inversa .............................................................................. 10",
    "10. Resultados esperados y beneficios ...................................................................... 11",
    "11. Conclusiones y recomendaciones ........................................................................... 12",
    "Apéndice: Glosario de términos técnicos ...................................................................... 13",
]
for item in contenido_items:
    story.append(Paragraph(item, ParagraphStyle(name="toc", fontSize=9, leading=13, textColor=C_BODY, fontName="Helvetica")))

story.append(PageBreak())

print("Páginas 0-1 (contexto + portada) construidas")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 2: ¿QUÉ ES ML?
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("1. ¿QUÉ ES UN MODELO DE MACHINE LEARNING?", styles["TitlePage"]))
story.append(Paragraph(
    "Un modelo de Machine Learning (ML) es un programa de computador que aprende patrones a partir de datos históricos para hacer predicciones sobre el futuro. A diferencia de una calculadora o una hoja de Excel, donde una persona escribe las reglas, en el ML el programa descubre las reglas por sí mismo.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("PARA ENTENDERLO SIN SER EXPERTO", [
    "Ejemplo sencillo: imagine que le muestra a un niño 100 fotos de perros y 100 de gatos.",
    "Al principio el niño confunde algunos, pero con el tiempo aprende a distinguirlos.",
    "Un modelo de ML hace exactamente eso, pero con números: le muestra datos históricos",
    "de embalses, generación, demanda — y aprende a predecir qué pasará mañana."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>1.1 ¿Qué tipos de modelos usa el Portal Energético?</b>", styles["Subtitle"]))

modelos_data = [
    ["<b>Modelo</b>", "<b>Qué hace</b>", "<b>Para qué se usa</b>"],
    ["PROPHET (Meta/Facebook)", "Descompone datos en: tendencia + estacionalidad + eventos especiales. Maneja bien datos faltantes.", "Embalses, biomasa (series con estacionalidad anual)"],
    ["ARIMA estacional (Auto-ARIMA)", "Modelo estadístico clásico que encuentra automáticamente los mejores parámetros. Captura dependencias de corto plazo.", "Térmica, eólica (series con autocorrelación)"],
    ["ENSEMBLE (combinación)", "Mezcla las predicciones de Prophet y ARIMA dándole más peso al que ha tenido mejor desempeño recientemente. La idea: 'dos cabezas piensan mejor que una'.", "Embalses (la combinación supera a cada modelo solo)"],
]
t_modelos = Table(modelos_data, colWidths=[45*mm, 70*mm, 45*mm])
t_modelos.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), C_TITLE),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ("TOPPADDING", (0, 0), (-1, 0), 6),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_NEAR_WHITE, colors.white]),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 1), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
]))
story.append(t_modelos)
story.append(Spacer(1, 4*mm))

story.append(alert_box("NOTA IMPORTANTE", [
    "LightGBM NO es un modelo de predicción en nuestro sistema. Es una herramienta auxiliar que se usa",
    "DENTRO del proceso de calibración de intervalos de confianza (explicado en la página 9).",
    "Las predicciones las hacen Prophet y ARIMA. LightGBM solo ajusta qué tan amplios son los intervalos."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 3: ¿QUÉ MODELO USA EL PORTAL?
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("2. ¿QUÉ MODELO USA EL PORTAL ENERGÉTICO HOY?", styles["TitlePage"]))
story.append(Paragraph(
    "El Portal Energético del MME usa un modelo ENSEMBLE (pronunciado 'onsámbel', del francés 'conjunto'): combina las predicciones de Prophet y ARIMA estacional. No es un modelo 'preentrenado' como GPT-4. Se entrena desde cero con datos del Sistema Interconectado Nacional (SIN) de Colombia cada 3 días.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("DIFERENCIA CLAVE: PREENTRENADO vs REENTRENADO", [
    "¿Qué significa 'preentrenado'? GPT-4 es preentrenado: ya leyó internet antes de que usted lo use.",
    "Nuestro modelo NO es así. Cada 3 días 'olvida' lo anterior y vuelve a aprender desde cero",
    "con los datos más recientes de XM (2020-2026) y backfill histórico (2000-2019).",
    "Esto es una ventaja: se adapta a cambios. Y una desventaja: no acumula 'memoria' de eventos raros."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>2.1 ¿Qué datos usa el modelo?</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El modelo solo ve UNA cosa: la serie temporal de la variable que quiere predecir. Por ejemplo, para embalses solo ve los valores históricos de porcentaje de capacidad útil. No ve el índice ONI (El Niño), no ve precipitaciones del IDEAM, no ve caudales de ríos. Esto es intencional para mantenerlo simple, pero es una limitación que explicaremos en la página 7.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

datos_data = [
    ["<b>Datos de entrada actuales</b>"],
    ["• Serie temporal de la métrica a predecir (ej: PorcVoluUtilDiar para embalses)"],
    ["• Rango: últimos 365-730 días de datos históricos de la base PostgreSQL"],
    ["• Frecuencia: diaria (algunas métricas son horarias, pero el modelo agrupa a diario)"],
    ["• NO usa variables exógenas: ni ONI, ni precipitación, ni irradiancia solar, ni viento"],
]
t_datos = Table(datos_data, colWidths=[160*mm])
t_datos.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), C_NEAR_WHITE),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 9),
    ("BOX", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 9),
]))
story.append(t_datos)
story.append(Spacer(1, 4*mm))

story.append(Paragraph(
    "El modelo hace una predicción puntual (un número para cada día futuro) y un intervalo de confianza (un rango donde cree que estará el valor real). El intervalo se calibra con una técnica llamada 'predicción conformal' que explicamos en la página 9.",
    styles["Body"]
))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 4: PIPELINE DE ENTRENAMIENTO
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("3. ¿CÓMO SE ENTRENA Y CON QUÉ FRECUENCIA?", styles["TitlePage"]))
story.append(Paragraph(
    "El sistema se reentrena automáticamente cada 3 días (domingo, miércoles, sábado a las 2:00 AM) mediante Celery Beat (un programador automático de tareas que corre en el servidor sin intervención humana). El pipeline completo toma entre 18 y 25 minutos.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>3.1 Pasos del pipeline (del código real)</b>", styles["Subtitle"]))

pasos = [
    ["<b>Paso</b>", "<b>Descripción</b>"],
    ["PASO 1: CARGA DE DATOS (3-5 seg)", "Query a PostgreSQL: SELECT fecha, valor_gwh FROM metrics WHERE metrica = 'PorcVoluUtilDiar' AND entidad = 'Sistema'. Rango: últimos 365-730 días."],
    ["PASO 2: PREPARACIÓN (1-2 seg)", "Interpolación de fechas faltantes, winsorización (recorte de valores extremos que superan 3 desviaciones estándar), formateo para Prophet (columnas 'ds' y 'y') y ARIMA (índice temporal)."],
    ["PASO 3: ENTRENAMIENTO (3-5 min)", "Prophet: optimización MAP (30-60 segundos). ARIMA: búsqueda stepwise de parámetros (2-3 minutos). Validación hold-out: se reservan los últimos 30 días como 'prueba final' que el modelo NO ve durante entrenamiento, para medir qué tan bien generaliza."],
    ["PASO 4: COMBINACIÓN ENSEMBLE (segundos)", "Carga pesos dinámicos de predictions_quality_history. Si no hay historial, usa 50/50. Promedio ponderado de predicciones."],
    ["PASO 5: CALIBRACIÓN CONFORMAL (10-20 seg)", "Entrena LightGBM auxiliar sobre características del calendario (día del año, día de semana, mes). Calcula scores de calibración. Ajusta intervalos de confianza. Garantía: cobertura ≥ nivel de confianza."],
    ["PASO 6: ALMACENAMIENTO (segundos)", "INSERT 450 registros (90 días × 5 fuentes) con UPSERT en PostgreSQL. Invalidación automática de caché Redis (TTL 1 hora)."],
]
t_pasos = Table(pasos, colWidths=[55*mm, 105*mm])
t_pasos.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), C_TITLE),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ("TOPPADDING", (0, 0), (-1, 0), 6),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_NEAR_WHITE, colors.white]),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 1), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
]))
story.append(t_pasos)
story.append(Spacer(1, 4*mm))

story.append(highlight_box("FRECUENCIA DE REENTRENAMIENTO", [
    "¿Por qué cada 3 días y no cada día? Porque los datos de XM no cambian drásticamente",
    "diariamente y el reentrenamiento consume recursos del servidor. Cada 3 días es un",
    "balance entre frescura del modelo y eficiencia computacional."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 5: DATOS REALES DE ERROR
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("4. ¿QUÉ TAN BUENO ES? — DATOS REALES DE ERROR", styles["TitlePage"]))
story.append(Paragraph(
    "A continuación presentamos los errores reales del sistema, extraídos de la base de datos de producción (tabla predictions_quality_history) en junio de 2026. El error se mide con MAPE: Error Porcentual Absoluto Medio. Un MAPE de 5% significa que, en promedio, el modelo se equivoca en 5% del valor real.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>4.1 MAPE real por fuente energética (datos de producción)</b>", styles["Subtitle"]))

mape_data = [
    ["<b>Fuente</b>", "<b>MAPE promedio</b>", "<b>MAPE mínimo</b>", "<b>MAPE máximo</b>", "<b>Evaluaciones</b>"],
    ["Embalses (%)", f"{REAL_MAPE_EMB_PCT_AVG}%", f"{REAL_MAPE_EMB_PCT_MIN}%", f"{REAL_MAPE_EMB_PCT_MAX}%", "31"],
    ["Demanda", f"{REAL_MAPE_DEMANDA_AVG}%", "0.6%", "26.4%", "20"],
    ["Solar", f"{REAL_MAPE_SOLAR_AVG}%", "1.8%", "62.9%", "18"],
    ["Hidráulica", f"{REAL_MAPE_HIDRAULICA_AVG}%", "2.5%", "48.1%", "135"],
    ["Eólica", f"{REAL_MAPE_EOLICA_AVG}%", "9.1%", "91.1%", "17"],
    ["Precio Bolsa", f"{REAL_MAPE_PRECIO_AVG}%", "9.2%", "58.5%", "17"],
]
t_mape = build_table(mape_data[0], mape_data[1:], [50*mm, 28*mm, 28*mm, 28*mm, 26*mm])
story.append(t_mape)
story.append(Spacer(1, 4*mm))

story.append(highlight_box("INTERPRETACIÓN HONESTA DE LOS DATOS", [
    "¿Qué significa esto? Los embalses tienen un MAPE promedio de 7.3%, pero ha llegado",
    f"hasta {REAL_MAPE_EMB_PCT_MAX}% en momentos de crisis (probablemente El Niño 2023-2024). La demanda",
    "parece tener buen MAPE (4.1%), pero tiene outliers extremos que filtramos porque",
    "indican problemas de datos, no del modelo. La eólica es la más difícil: 38.2% de error."
]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph(
    "El PDF anterior (V2) decía 'MAPE 3.2% para embalses' como si fuera un hecho estable. La realidad es que el MAPE varía según la época del año, la condición climática, y la calidad de los datos de entrada. Presentar un solo número es engañoso. Presentamos el rango completo.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(alert_box("TRANSPARENCIA", [
    "No tenemos un benchmark de validación cruzada temporal riguroso. Los MAPEs son ex-post:",
    "se calculan DESPUÉS de que pasa el día, comparando predicción vs valor real. Esto es útil pero no",
    "equivalente a un test de laboratorio controlado. Lo admitimos."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 6: ¿POR QUÉ ESTE MODELO?
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("5. ¿POR QUÉ ESTE MODELO Y NO OTRO?", styles["TitlePage"]))
story.append(Paragraph(
    "La elección de Prophet + ARIMA ensemble no fue arbitraria. Se evaluaron múltiples modelos y se eligió este porque ofrece el mejor balance entre precisión, interpretabilidad, velocidad y robustez ante datos faltantes (comunes en datos de XM).",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>5.1 Comparativa honesta de modelos evaluados</b>", styles["Subtitle"]))

comp_data = [
    ["<b>Modelo</b>", "<b>MAPE real</b>", "<b>Tiempo</b>", "<b>Fortalezas</b>", "<b>Debilidades</b>"],
    ["Prophet", "3.5-7%", "30-60s", "Estacionalidad, changepoints, datos faltantes", "Cambios abruptos no previstos"],
    ["ARIMA est.", "4-32%", "2-3min", "Autocorrelación, IC estadísticos", "Requiere estacionariedad: que la serie no cambie de comportamiento drásticamente con el tiempo (ej: si antes variaba entre 70-80% y ahora varía entre 40-50%, no es estacionaria)"],
    ["Ensemble", "1.4-32%", "3-5min", "Combina fortalezas, pesos dinámicos", "Más complejo de mantener"],
    ["LSTM", "No probado", "30-60min", "Patrones complejos teóricos", "Requiere 10,000+ datos, GPU"],
    ["XGBoost", "No probado", "45-90s", "Robusto a outliers teórico", "No captura temporalidad"],
]
t_comp = Table(comp_data, colWidths=[28*mm, 22*mm, 18*mm, 50*mm, 42*mm])
t_comp.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), C_TITLE),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ("TOPPADDING", (0, 0), (-1, 0), 6),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_NEAR_WHITE, colors.white]),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING", (0, 1), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
]))
story.append(t_comp)
story.append(Spacer(1, 3*mm))

story.append(Paragraph(
    "Nota: Los MAPEs de LSTM y XGBoost dicen 'No probado' porque el sistema actual no los ejecuta en producción para embalses. Han sido evaluados en experimentos locales pero no integrados al pipeline. El PDF anterior (V2) presentaba números teóricos como si fueran reales. Corregimos eso.",
    ParagraphStyle(name="ns", parent=styles["Body"], fontSize=9, textColor=C_ACCENT)
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>5.2 ¿Por qué la combinación funciona?</b>", styles["Subtitle"]))
story.append(Paragraph(
    "• <b>PROPHET aporta:</b> detección de tendencias de largo plazo, modelado de estacionalidad anual (ciclos de lluvias), manejo de changepoints (cambios de política), tolerancia a datos faltantes.<br/>"
    "• <b>ARIMA aporta:</b> captura de dependencias de corto plazo, intervalos de confianza con fundamentación estadística, modelado de estacionalidad semanal, corrección por errores previos.<br/>"
    "• <b>El ensemble aprende:</b> mediante pesos dinámicos inversos al MAPE reciente, da más peso al modelo que ha estado acertando más en los últimos días.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("CÓMO FUNCIONAN LOS PESOS DEL ENSEMBLE", [
    "Fórmula real del código: w_i = (1 / MAPE_i) / sum(1 / MAPE_j)",
    "Si Prophet tuvo MAPE 4% y ARIMA 6%, los pesos serían: Prophet 60%, ARIMA 40%.",
    "Estos pesos se recalculan en cada reentrenamiento. No son fijos."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 7: ERRORES DEL MODELO
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("6. ERRORES DEL MODELO: QUÉ NO PUEDE HACER HOY", styles["TitlePage"]))
story.append(Paragraph(
    "Es importante ser honestos: el modelo ensemble Prophet + ARIMA es funcional para condiciones normales, pero tiene limitaciones fundamentales que NO puede superar con la arquitectura actual. Estas limitaciones son inherentes al tipo de modelo y a los datos de entrada.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>6.1 Error 1: No captura eventos climáticos extremos</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El modelo aprende patrones ESTADÍSTICOS de los datos históricos. Si en los últimos 6 años no ha ocurrido un El Niño intenso comparable al de 2026, el modelo NO tiene información suficiente para anticipar cómo se comportarán los embalses. Asume que el futuro se parece al pasado reciente.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("EJEMPLO CONCRETO: EL NIÑO 2026-2027", [
    "El modelo predice 77.31% para agosto 2026 basándose en la estacionalidad histórica.",
    "PERO la proyección climática del IDEAM indica déficit de lluvias en cuencas clave.",
    "El modelo NO incluye el índice ONI (Niño Oscilación del Sur) como variable de entrada.",
    "Resultado: predicción que puede ser optimista y no reflejar el riesgo real del fenómeno."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>6.2 Error 2: No incorpora leyes físicas</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El modelo es puramente estadístico. No conoce la ecuación de potencia hidráulica P = ρgQHη, ni el efecto fotovoltaico, ni el límite de Betz para aerogeneradores. Esto significa que puede generar predicciones físicamente inconsistentes.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "• Puede predecir generación hidráulica alta sin considerar caudales reales.<br/>"
    "• No respeta el balance de potencia: suma de generaciones ≠ demanda + pérdidas.<br/>"
    "• No puede identificar configuraciones pre-crisis (umbrales de caudal, ONI, embalses).<br/>"
    "• Los intervalos de confianza se amplían excesivamente (>50%) para horizontes >90 días.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>6.3 Error 3: Datos de entrada limitados</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El modelo solo utiliza la serie temporal de la variable objetivo como entrada. No incorpora variables climáticas exógenas que mejorarían drásticamente la predicción ante condiciones anómalas.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "• Precipitación IDEAM (cuencas Magdalena, Cauca, Nechí)<br/>"
    "• Irradiancia solar NASA POWER (Costa Caribe, La Guajira)<br/>"
    "• Velocidad del viento IDEAM (Alta Guajira, parques eólicos)<br/>"
    "• Índice ONI (Niño Oscilación del Sur) de NOAA<br/>"
    "• Caudales afluentes reales (Q en la ecuación hidráulica)",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(alert_box("CONCLUSIÓN DE ESTA SECCIÓN", [
    "El modelo actual es ADECUADO para condiciones normales. Es INSUFICIENTE para eventos extremos.",
    "La siguiente sección propone una línea de investigación para superar estas limitaciones."
]))

story.append(PageBreak())

print("Páginas 2-7 construidas")

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 8: PROPUESTA PINN-LSTM
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("7. PROPUESTA DE INVESTIGACIÓN: PINN-LSTM (FUTURO)", styles["TitlePage"]))
story.append(Paragraph(
    "Esta sección describe una PROPUESTA DE INVESTIGACIÓN, no un sistema implementado. Está basada en la tesis de Melissa Cardona (Universidad del Atlántico, 2026) y representa un roadmap técnico para mejorar el sistema en el mediano plazo (12-24 meses).",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("PARA ENTENDERLO SIN SER EXPERTO", [
    "¿Qué es PINN-LSTM? Una red neuronal que combina dos ideas:",
    "• LSTM (Long Short-Term Memory): captura dependencias temporales de largo alcance.",
    "• PINN (Physics-Informed Neural Network): incorpora ecuaciones físicas como restricciones.",
    "La red aprende de los datos PERO también respeta las leyes de la física."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>7.1 Ecuaciones físicas que incorporaría</b>", styles["Subtitle"]))

ecuaciones = [
    ["<b>Fuente</b>", "<b>Ecuación</b>", "<b>Qué significa</b>"],
    ["HIDROELÉCTRICA", "P = ρ · g · Q · H · η", "ρ=1000 kg/m³, g=9.81 m/s², Q=caudal (m³/s), H=altura (m), η=eficiencia (~0.90). La red aprendería que sin caudal (Q≈0), la potencia no puede ser alta."],
    ["SOLAR FV", "P = η(T) · A · G", "η(T)=eficiencia por temperatura, A=área del panel (m²), G=irradiancia solar (W/m²). La red aprendería que sin irradiancia (G≈0 de noche), la potencia es cero."],
    ["EÓLICA", "P = Cp · 0.5 · ρ · A · v³", "Cp=coeficiente de potencia (≤0.593, límite de Betz), v=velocidad del viento (m/s). La red aprendería que la potencia crece con el CUBO del viento, no linealmente."],
]
t_ec = Table(ecuaciones, colWidths=[28*mm, 38*mm, 94*mm])
t_ec.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), C_TITLE),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ("TOPPADDING", (0, 0), (-1, 0), 6),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_NEAR_WHITE, colors.white]),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 1), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
]))
story.append(t_ec)
story.append(Spacer(1, 4*mm))

story.append(alert_box("ESTADO ACTUAL DE ESTA INVESTIGACIÓN", [
    "Esta propuesta es ACADÉMICA. No hay código implementado en el Portal Energético.",
    "Requiere: recolección de datos climáticos, desarrollo de modelo, validación histórica, integración.",
    "Tiempo estimado: 12-24 meses con un equipo de 2-3 investigadores."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 9: FUNCIÓN DE PÉRDIDA Y CALIBRACIÓN CONFORMAL
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("8. FUNCIÓN DE PÉRDIDA HÍBRIDA Y CALIBRACIÓN CONFORMAL", styles["TitlePage"]))
story.append(Paragraph(
    "Esta página explica dos conceptos técnicos que el PDF anterior (V2) omitió o confundió: (1) cómo una PINN aprende respetando la física, y (2) cómo el sistema actual calibra sus intervalos de confianza.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>8.1 Función de pérdida híbrida (propuesta PINN-LSTM)</b>", styles["Subtitle"]))
story.append(Paragraph(
    "En una red neuronal tradicional, la 'pérdida' mide qué tan lejos está la predicción del valor real. En una PINN, la pérdida tiene DOS componentes: error de predicción + error físico.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("DESGLOSE DE LA FUNCIÓN DE PÉRDIDA", [
    "L_total = L_datos + λ_hidráulico · L_hidráulica + λ_solar · L_solar + λ_eólica · L_eólica + L_regularización",
    "",
    "L_datos: ¿Qué tan lejos está mi predicción del valor real observado?",
    "L_hidráulica: ¿Respeta la ecuación P = ρgQHη? Si predigo P=100MW pero Q=0, hay error físico.",
    "L_regularización: Evita que la red 'memorice' en lugar de 'aprender' (overfitting: cuando el modelo aprende de memoria los datos de entrenamiento pero falla con datos nuevos).",
    "λ (lambda): Pesos que balancean qué tan estricto es cada término. Se ajustan automáticamente mediante gradientes (cambios pequeños en los parámetros que reducen el error)."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>8.2 Calibración conformal (SISTEMA ACTUAL)</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El sistema actual usa una técnica avanzada llamada Split Conformal Prediction para calibrar los intervalos de confianza. Esto garantiza que, en promedio, el valor real caiga dentro del intervalo al menos el % de veces que prometemos (ej: 90%).",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("PARA ENTENDERLO SIN SER EXPERTO: CALIBRACIÓN CONFORMAL", [
    "¿Cómo funciona? 1) Separa los últimos 60 días de datos como 'calibración'.",
    "2) Entrena un LightGBM auxiliar SOLO sobre características del calendario (día del año, día de semana).",
    "3) Calcula el error del LightGBM en esos 60 días: |real - predicho|.",
    "4) El percentil 90 de esos errores (el valor que supera al 90% de los errores, es decir, casi todos) se suma/resta a la predicción del ensemble.",
    "5) Resultado: intervalo [predicción - q, predicción + q] con garantía estadística."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph(
    "¿Por qué es importante? Sin calibración conformal, los intervalos de Prophet y ARIMA son 'optimistas': prometen 95% de cobertura pero en la práctica cubren menos. La calibración conformal corrige esto usando datos recientes. Es una de las características más técnicamente robustas del sistema actual.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(alert_box("CORRECCIÓN DEL PDF ANTERIOR", [
    "El PDF V2 decía que LightGBM predice 'demanda, precio, solar, eólica'. Eso era incorrecto.",
    "LightGBM es el modelo AUXILIAR de calibración conformal. No hace predicciones principales."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 10: ANÁLISIS DE SENSIBILIDAD INVERSA
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("9. ANÁLISIS DE SENSIBILIDAD INVERSA", styles["TitlePage"]))
story.append(Paragraph(
    "Esta sección describe una técnica propuesta en la investigación de Melissa Cardona para identificar qué combinaciones de variables llevan a crisis energética. Es conceptual: no está implementada en el sistema actual.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(highlight_box("PARA ENTENDERLO SIN SER EXPERTO", [
    "¿Qué es la sensibilidad inversa? En lugar de preguntar '¿qué pasará si llueve poco?',",
    "se pregunta: '¿qué condiciones de lluvia, viento, demanda y embalses producen",
    "un déficit de generación mayor al 10%?' Es como 'correr el modelo hacia atrás':",
    "dado un resultado de crisis, ¿qué entradas lo causaron?"
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>9.1 Definición de déficit relativo</b>", styles["Subtitle"]))
story.append(Paragraph(
    "Se define el déficit relativo δ como la diferencia entre demanda y generación total, dividida por la demanda. Un δ > 10% podría indicar riesgo de racionamiento. El umbral de crisis τ* se define como el percentil 90 de δ durante episodios históricos de racionamiento (2009-2010, 2015-2016).",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>9.2 Variables de entrada analizadas</b>", styles["Subtitle"]))
story.append(Paragraph(
    "• Caudales afluentes Q_t (IDEAM) — variable física determinante<br/>"
    "• Niveles de embalse agregado (XM)<br/>"
    "• Índice ONI (NOAA) — señal climática global<br/>"
    "• Demanda nacional P_dem,t (XM)<br/>"
    "• Precio de bolsa (XM) — proxy de estrés del sistema<br/>"
    "• Irradiancia solar G_t (NASA POWER)<br/>"
    "• Velocidad del viento v_t (IDEAM)",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>9.3 Ranking de sensibilidad</b>", styles["Subtitle"]))
story.append(Paragraph(
    "El ranking S_j mide cuánto cambia el déficit cuando cambia cada variable. Identifica los factores desencadenantes de mayor influencia. Por ejemplo, si S_caudal = 0.8 y S_viento = 0.1, el caudal es 8 veces más importante que el viento para predecir crisis.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(alert_box("ESTADO DE IMPLEMENTACIÓN", [
    "Este análisis de sensibilidad inversa es PROPUESTA ACADÉMICA. No está codificado en el Portal.",
    "Requiere: modelo PINN-LSTM entrenado, datos multivariados, optimizador L-BFGS-B."
]))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 11: RESULTADOS ESPERADOS
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("10. RESULTADOS ESPERADOS Y BENEFICIOS", styles["TitlePage"]))
story.append(Paragraph(
    "Esta sección presenta PROYECCIONES TEÓRICAS de lo que podría lograrse si se implementa la investigación PINN-LSTM. Estos números NO son garantías: son objetivos basados en la literatura científica y la tesis de Melissa Cardona.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(alert_box("ADVERTENCIA SOBRE ESTIMACIONES", [
    "IMPORTANTE: Los números de esta sección son PROYECCIONES TEÓRICAS.",
    "No provienen de ejecuciones reales del sistema. Son metas de investigación",
    "basadas en resultados publicados en literatura científica sobre PINNs."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>10.1 Mejoras cuantitativas proyectadas</b>", styles["Subtitle"]))

proj_data = [
    ["<b>Métrica</b>", "<b>Sistema actual</b>", "<b>Proyección PINN-LSTM</b>", "<b>Nota</b>"],
    ["MAPE embalses", "1.4% - 31.9%", "< 2.5% (estable)", "Incorporando ONI y caudales"],
    ["MAPE demanda", "0.6% - 26.4%", "< 3% (estable)", "Modelo físico + climático"],
    ["Cobertura IC", "85-90% (estimado)", "90-95% (garantizado)", "Monte Carlo Dropout"],
    ["Horizonte", "90 días (moderado)", "365 días (experimental)", "Con confianza moderada"],
    ["Alerta pre-crisis", "No disponible", "30-90 días", "Umbral configurable"],
]
t_proj = build_table(proj_data[0], proj_data[1:], [38*mm, 38*mm, 44*mm, 40*mm])
story.append(t_proj)
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>10.2 Mejoras cualitativas</b>", styles["Subtitle"]))
story.append(Paragraph(
    "• Predicciones físicamente consistentes: respetan leyes de conservación de energía y masa.<br/>"
    "• Cuantificación de incertidumbre ante eventos extremos: intervalos bien calibrados para El Niño.<br/>"
    "• Alertas tempranas basadas en umbrales de variables de entrada (no solo de salida).<br/>"
    "• Interpretabilidad: el modelo 'sabe' por qué predice lo que predice (gracias a las ecuaciones físicas).<br/>"
    "• Replicabilidad en sistemas similares: Brasil, Perú, Ecuador, Centroamérica.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>10.3 Impacto en la toma de decisiones</b>", styles["Subtitle"]))
story.append(Paragraph(
    "• Planificación del despacho económico con mayor horizonte temporal (de 30 a 90+ días).<br/>"
    "• Gestión proactiva de reservas hidráulicas: protocolos de conservación antes de la crisis.<br/>"
    "• Activación temprana de generación térmica de respaldo (menor costo de oportunidad).<br/>"
    "• Información para políticas públicas de seguridad energética basada en evidencia física.<br/>"
    "• Reducción del riesgo de racionamiento y sus costos socioeconómicos.",
    styles["Body"]
))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 12: CONCLUSIONES
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("11. CONCLUSIONES Y RECOMENDACIONES", styles["TitlePage"]))
story.append(Paragraph(
    "El sistema actual de predicciones ML del Portal Energético (Prophet + ARIMA ensemble con calibración conformal) es funcional y cumple con los requisitos de planificación operativa para condiciones normales. Sin embargo, presenta limitaciones críticas ante eventos climáticos extremos como El Niño, debido a su naturaleza puramente estadística y la ausencia de variables climáticas exógenas.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>Conclusiones clave</b>", styles["Subtitle"]))
story.append(Paragraph(
    "• El modelo actual es ADECUADO para condiciones normales (MAPE embalses 1.4-31.9%, promedio 7.3%).<br/>"
    "• El modelo actual es INSUFICIENTE para eventos extremos (no captura El Niño, no usa ONI).<br/>"
    "• La calibración conformal es una fortaleza técnica subestimada del sistema actual.<br/>"
    "• La propuesta PINN-LSTM es INVESTIGACIÓN FUTURA: requiere 12-24 meses de desarrollo.<br/>"
    "• La inversión en este modelo representa un seguro contra racionamientos futuros.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("<b>Recomendaciones inmediatas (bajo costo, alto impacto)</b>", styles["Subtitle"]))
story.append(Paragraph(
    "• <b>INTEGRAR</b> el índice ONI como regresor en el modelo actual de embalses (costo: bajo, impacto: medio).<br/>"
    "• <b>INCORPORAR</b> precipitación IDEAM y caudales como variables de entrada (costo: medio, impacto: alto).<br/>"
    "• <b>DESARROLLAR</b> prototipo PINN-LSTM para una métrica piloto: embalses (costo: alto, impacto: muy alto).<br/>"
    "• <b>VALIDAR</b> contra episodios históricos: 2009-2010 (racionamiento), 2015-2016 (El Niño fuerte).<br/>"
    "• <b>ESTABLECER</b> alianza con Universidad del Atlántico (Melissa Cardona) para implementación colaborativa.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

story.append(alert_box("MENSAJE FINAL", [
    "No necesitamos el modelo perfecto. Necesitamos un modelo que sea honesto sobre sus limitaciones",
    "y que mejore continuamente. El sistema actual cumple el primer requisito. La propuesta PINN-LSTM",
    "apunta al segundo. Juntos, representan una estrategia de predicción energética robusta y transparente."
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("<b>Referencias técnicas</b>", styles["Subtitle"]))
story.append(Paragraph(
    "• Cardona Navarro, M. (2026). Estudio de la generación de potencia del SIN mediante redes neuronales profundas y validación Monte Carlo. Trabajo de Grado, Programa de Física, Universidad del Atlántico.<br/>"
    "• Código fuente: server/domain/services/predictions_service_extended.py<br/>"
    "• Configuración de tareas: server/tasks/__init__.py (Celery Beat schedule)<br/>"
    "• Vovk, V., Gammerman, A., & Shafer, G. (2005). Algorithmic Learning in a Random World. Springer. (Conformal Prediction)",
    ParagraphStyle(name="ref", parent=styles["Body"], fontSize=8, leading=12)
))

story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 13: GLOSARIO
# ═══════════════════════════════════════════════════════════════════════════
story.append(Paragraph("APÉNDICE: GLOSARIO DE TÉRMINOS TÉCNICOS", styles["TitlePage"]))
story.append(Paragraph(
    "Este glosario explica cada término técnico usado en el documento para que un lector sin conocimiento previo de machine learning o energía pueda entenderlo todo.",
    styles["Body"]
))
story.append(Spacer(1, 3*mm))

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
    story.append(Paragraph(f"<b>{termino}:</b> {definicion}", ParagraphStyle(name="glosario", parent=styles["Body"], fontSize=8, leading=11, spaceAfter=4)))

# ═══════════════════════════════════════════════════════════════════════════
# GUARDAR PDF
# ═══════════════════════════════════════════════════════════════════════════
def header_footer_simple(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(C_GRAY)
    canvas.drawString(20*mm, 280*mm, "PORTAL ENERGÉTICO MME — SISTEMA DE PREDICCIONES ML")
    canvas.drawRightString(190*mm, 280*mm, f"Página {doc.page}")
    canvas.setStrokeColor(C_LIGHT)
    canvas.line(20*mm, 278*mm, 190*mm, 278*mm)
    canvas.restoreState()

doc_template = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    rightMargin=20*mm,
    leftMargin=20*mm,
    topMargin=25*mm,
    bottomMargin=20*mm,
)

doc_template.build(story, onFirstPage=header_footer_simple, onLaterPages=header_footer_simple)

print(f"\n✅ PDF generado exitosamente: {OUTPUT}")
print(f"   Tamaño archivo: {OUTPUT.stat().st_size / 1024:.1f} KB")


