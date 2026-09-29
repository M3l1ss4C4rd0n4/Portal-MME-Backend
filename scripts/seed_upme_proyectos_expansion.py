#!/usr/bin/env python3
"""
Siembra sector_energetico.upme_proyectos_expansion con datos REALES y
verificables de proyectos de generación y transmisión eléctrica en Colombia,
priorizando capacidad (MW) y retraso documentado — evidencia de base para
evaluar la hipótesis de que la crisis de suministro fue causada por atrasos
en la ejecución del Plan de Expansión de Referencia Generación-Transmisión
de la UPME.

No existe una API estructurada de UPME para esta información: cada fila fue
curada manualmente cruzando la fuente primaria (informes de seguimiento de
obras/proyectos publicados por UPME) con cobertura de prensa especializada,
y cada una trae su propio campo `fuente` trazable. Cuando la fuente no
permitía sustentar con confianza razonable una fecha, un MW o un estado,
ese campo se dejó en NULL en vez de inventarlo.

FUENTES PRINCIPALES CONSULTADAS (fecha de consulta: 2026-09-23):

1. UPME, "Informe de avance proyectos de generación – Junio 2025"
   (Subdirección de Energía Eléctrica, Grupo de Generación), PDF oficial:
   https://docs.upme.gov.co/SIMEC/Energia%20Electrica/Seguimiento_proyectos_generacion/Informe_avance_proyectos_generacion_Junio_2025.pdf
   — fuente primaria para la mayoría de proyectos de GENERACIÓN de este
   script: trae, por proyecto, la Fecha de Puesta en Operación (FPO)
   declarada/vigente y, cuando aplica, la FPO originalmente declarada ante
   CREG/UPME, más el resultado de auditoría externa independiente (INGETEC
   y otros) con días de atraso explícitos frente al cronograma de
   construcción y curva "S" reportados. Es la evidencia más sólida y
   trazable de todo el dataset porque compara explícitamente fecha
   originalmente comprometida vs. fecha vigente/auditada para el MISMO
   proyecto.

2. UPME, "Plan de Expansión de Transmisión 2025-2039" (documento vigente
   más reciente del Plan de Expansión de Referencia Generación-Transmisión,
   componente de transmisión), publicado por el Ministerio de Minas y
   Energía:
   https://www.minenergia.gov.co/documents/15647/Plan-expansion-2025-2039.pdf
   — fuente primaria para las Fechas de Puesta en Operación (FPO)
   planeadas de los proyectos de transmisión en ejecución (tablas de obras
   consideradas en las evaluaciones de compensadores síncronos del Área
   Caribe, sección 3.1.3).

3. Portafolio, "El 85% de proyectos de líneas de transmisión presentan
   atrasos": https://www.portafolio.co/economia/el-85-de-proyectos-de-lineas-de-transmision-presentan-atrasos-535052
   — cobertura de prensa especializada citando cifras de UPME/CREG sobre
   proyectos de transmisión con más de 5 años de atraso acumulado
   (incluye Chivor II, La Virginia-Nueva Esperanza, entre otros).

4. El Colombiano, "Colectora contra reloj: tras 235 consultas, la gran
   'autopista' de la energía solar y eólica de Colombia verá la luz este
   año": https://www.elcolombiano.com/negocios/colectora-energia-renovable-guajira-colombia-operacion-2026-AI35869687
   y El Tiempo, "Colectora se retrasa 8 meses porque exigen más consultas
   previas": https://www.eltiempo.com/economia/sectores/colectora-se-retrasa-8-meses-porque-exigen-mas-consultas-previas-no-pueden-aparecer-nuevas-comunidades-infinitamente-3583138
   y Diario La Libertad, "Colectora vuelve a retrasarse... ahora exigen
   nuevas consultas" (03-sep-2026): https://diariolalibertad.com/2026/09/03/colectora-vuelve-a-retrasarse-y-queda-en-vilo-la-energia-eolica-de-la-guajira-ahora-exigen-nuevas-consultas/
   — cobertura del caso de mayor perfil público sobre retraso de
   transmisión asociado a consulta previa con comunidades indígenas Wayuu.

5. El Colombiano, "'Tenemos más de cinco años de retrasos en la cobertura
   de energía': Upme" (entrevista al director de UPME):
   https://www.elcolombiano.com/negocios/director-de-la-upme-habla-sobre-los-nuevos-proyectos-de-transmision-y-crisis-de-energia-en-colombia-MN25281805

6. El Colombiano, "Cronograma de generación de las unidades de Hidroituango
   entre 2022 y 2025": https://www.elcolombiano.com/antioquia/cronograma-de-generacion-de-las-unidades-de-hidroituango-entre-2022-y-2025-LD14534807
   y El Colombiano, "Hidroituango superó el 93,4% de ejecución y avanza
   para encenderse del todo en 2028": https://www.elcolombiano.com/antioquia/hidroituango-ejecucion-avances-obras-recuperacion-casa-de-maquinas-MF31613359

7. BNamericas, ficha de proyecto "Segundo Refuerzo de Red en el Área
   Oriental — Línea de Transmisión La Virginia - Nueva Esperanza 500kV
   (UPME 07-2016)": https://www.bnamericas.com/es/perfil-proyecto/linea-de-transmision-la-virignia---nueva-esperanza-500kv

8. Portafolio, "ANLA da vía libre a tramo final de Chivor II, proyecto que
   llevará más capacidad eléctrica hacia Bogotá y al centro":
   https://www.portafolio.co/energia/anla-da-via-libre-a-tramo-final-de-chivor-ii-proyecto-que-llevara-mas-capacidad-electrica-hacia-bogota-y-al-centro-499608

9. El Tiempo, "'Si nos va bien, arrancamos en 2027': Parques eólicos de AES
   Colombia y Ecopetrol en La Guajira sufren otro retraso":
   https://www.eltiempo.com/economia/sectores/si-nos-va-bien-arrancamos-en-2027-parques-eolicos-de-aes-colombia-y-ecopetrol-en-la-guajira-sufren-otro-retraso-3586901
   (contexto adicional sobre Windpeshi/Jemeiwaa Ka'i, complementa el
   informe UPME de la fuente 1).

10. El Tiempo, "El parque solar más grande de Colombia entrará en
    operación en 2026..." y Bloomberg Línea, "El parque solar más grande
    de Colombia cambia de manos..." (21-sep-2026) — Parque Solar Puerta de
    Oro (Cundinamarca), incluido como contraste de un proyecto grande que
    SÍ cumplió cronograma, para no sesgar el dataset solo hacia atrasos.

LIMITACIONES IMPORTANTES (léase antes de usar este dataset para conclusiones):

- La fuente 1 (informe UPME de generación) es, en sí misma, la comparación
  más rigurosa disponible entre fecha originalmente declarada y fecha
  vigente/auditada para un mismo proyecto — pero UPME solo publica ese
  detalle completo (ambas fechas) para una parte de los proyectos que
  reporta; para varios (p. ej. Parque Eólico Alpha, Beta, JK1, Camelias)
  el informe solo trae la fecha vigente/auditada y el % o días de atraso
  acumulado frente a la curva "S" interna del proyecto, SIN indicar la
  fecha calendario originalmente comprometida. En esos casos
  `fecha_entrada_planeada_original` se dejó en NULL a propósito en vez de
  derivarla por aritmética hacia atrás — solo se completó cuando el
  informe citaba explícitamente ambas fechas en el texto (p. ej. Windpeshi:
  FPO original declarada ante CREG el 08-nov-2021 vs. FPO estimada por el
  auditor el 30-sep-2026).
- No se logró acceder al contenido navegable de una versión ANTERIOR
  completa del Plan de Expansión de Referencia Generación-Transmisión
  (p. ej. 2022-2036 o 2023-2037) con el mismo nivel de detalle por
  proyecto que el Plan 2025-2039 vigente, así que la comparación
  "primera versión del Plan vs. versión vigente" no se pudo hacer para los
  proyectos de TRANSMISIÓN de este script; para esos, `fuente` documenta
  en su lugar la fecha declarada en el Plan de Expansión de Transmisión
  2025-2039 (única versión con acceso verificado) más cobertura de prensa
  sobre el atraso frente a esa fecha.
- Varios proyectos eólicos de La Guajira (Irraipa, Arrizal, Camelias) NO
  tienen actualización de avance en el informe UPME de junio 2025 pese a
  que su FPO declarada ya venció — eso en sí mismo es evidencia indirecta
  de atraso, documentada en `notas`, aunque no exista una FPO vigente
  reformulada para citar.
- `capacidad_mw` se deja NULL en todos los proyectos de TRANSMISIÓN de
  este script (líneas/subestaciones): la capacidad real se documenta en
  `notas` en kV y, cuando la fuente la reporta, en MW de generación que la
  línea evacúa (no es una magnitud directamente comparable a capacidad
  instalada de generación).
- `area_operativa` solo se completó para departamentos donde la
  clasificación en las 6 áreas operativas de XM es inequívoca a partir del
  conocimiento general del sistema (La Guajira/Atlántico/Cesar/Bolívar/
  Córdoba/Magdalena/Sucre → Caribe; Antioquia → Antioquia). Para el resto
  de departamentos (Huila, Santander, Cundinamarca, Boyacá, Meta,
  Risaralda, Tolima, etc.) se dejó NULL por no tener certeza suficiente
  sobre el límite exacto de área operativa que usa XM.

Uso:
    venv/bin/python3 scripts/seed_upme_proyectos_expansion.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.database.repositories.upme_proyectos_repository import (  # noqa: E402
    UpmeProyectosRepository,
)

PROYECTOS = [
    # ------------------------------------------------------------------
    # GENERACIÓN — EÓLICA, La Guajira (complejo eólico más retrasado y
    # documentado del país; fuente principal: UPME, Informe de avance
    # proyectos de generación – Junio 2025, corte 31-dic-2024 salvo
    # donde se indique otro corte)
    # ------------------------------------------------------------------
    {
        "nombre_proyecto": "Parque Eólico Windpeshi",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 200,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2021, 11, 8),
        "fecha_entrada_planeada_vigente": date(2026, 9, 30),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.14, corte 31-dic-2024): retraso de "
            "965 días en el avance físico de construcción (64% ejecutado "
            "vs. 100% programado) y de 1.787 días frente a la FPO "
            "declarada ante la CREG para el 08-nov-2021; el auditor "
            "estima la nueva FPO en el 30-sep-2026."
        ),
        "notas": (
            "Promotor original Enel Colombia (dejó el proyecto en 2023); "
            "Ecopetrol entró como socio en 2025 con USD 50 millones. A "
            "sep-2026 solo estaban en pie las estructuras de las torres "
            "(las2orillas.co). 45 aerogeneradores GE Cypress, 5.3 MW c/u."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico Beta",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 280,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2027, 11, 30),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.14, corte 31-dic-2024): avance real "
            "verificado 41,14% vs. 100% programado en curva S declarada "
            "ante la CREG — retraso del 58,86%, equivalente a 982 días. "
            "El informe no cita la fecha calendario originalmente "
            "declarada, solo el % de atraso y la FPO vigente estimada por "
            "el auditor (30-nov-2027)."
        ),
        "notas": (
            "Promotor Eolos Energía S.A. ESP (EDPR). 51 aerogeneradores de "
            "5,6 MW. Ubicado en Uribia y Maicao, La Guajira."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico Alpha",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 218.4,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2027, 11, 30),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.14, corte 31-dic-2024): avance real "
            "acumulado 25,86% frente a un retraso equivalente al 74,14% "
            "del cronograma de construcción y curva S declarados ante la "
            "CREG. El auditor proyecta la FPO en 30-nov-2027."
        ),
        "notas": (
            "Promotor Vientos del Norte S.A.S. ESP (EDPR), Maicao, La "
            "Guajira. 39 aerogeneradores VESTAS V162-5.6MW. El propio "
            "informe UPME menciona una posible venta del proyecto por "
            "parte del promotor, en evaluación por el auditor."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico Camelias",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 250,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2023, 11, 30),
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.8, corte 31-dic-2022 — la última "
            "auditoría disponible en el reporte de junio-2025, sin "
            "actualización posterior reportada por el promotor): retraso "
            "de 114 días (10,66%) entre la curva S de ejecución real y la "
            "declarada ante UPME; FPO declarada 30-nov-2023."
        ),
        "notas": (
            "Promotor Begonia Power, 250 MW, Uribia y Maicao (La Guajira). "
            "La FPO declarada (30-nov-2023) ya está vencida hace más de un "
            "año y medio a la fecha del informe UPME (jun-2025) sin que "
            "exista un informe de auditoría más reciente en el documento "
            "consultado — posible indicio de atraso mayor al "
            "explícitamente reportado."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico JK1 (antes Casa Eléctrica)",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 180,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2026, 8, 18),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.13, corte 31-dic-2024): avance en "
            "cronograma de construcción y curva S del 30,28% frente a un "
            "programado del 100%, retraso del 69,72% (1.357 días). FPO "
            "estimada por el auditor: 18-ago-2026."
        ),
        "notas": (
            "Complejo Jemeiwaa Ka'i de AES Colombia & Cía. S.C.A. E.S.P. "
            "(hasta 360 aerogeneradores, rango 180-360 MW). Condicionado a "
            "la subestación Colectora 1 AC 500 kV y su línea de "
            "transmisión asociada — el propio informe UPME identifica el "
            "atraso de esa obra de transmisión (ver 'Línea Colectora' en "
            "este mismo dataset) como una amenaza real para este proyecto."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico JK2 (antes Apotolorru)",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 75,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2023, 2, 28),
        "fecha_entrada_planeada_vigente": date(2026, 8, 18),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.10, corte 31-dic-2024): 1.200 días "
            "de atraso frente al 28-feb-2023, fecha de terminación "
            "declarada en el cronograma de construcción y curva S; nueva "
            "FPO estimada 18-ago-2026."
        ),
        "notas": (
            "Complejo Jemeiwaa Ka'i de AES Colombia. Capacidad efectiva "
            "neta declarada 74,59 MW (columna MW del informe: 75). El "
            "auditor advierte que los riesgos de la subestación Colectora "
            "1 AC 500 kV y su línea asociada son una 'amenaza real' para "
            "este proyecto; se espera que ambos estén operando hacia el "
            "18-may-2026."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico Irraipa",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 99,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2024, 10, 31),
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025: "
            "FPO declarada 31-oct-2024; el informe indica explícitamente "
            "'No se ha recibido información' de avance del promotor."
        ),
        "notas": (
            "Promotor Jemeiwaa Ka'i (complejo AES Colombia), Uribia, La "
            "Guajira. 99 MW con aerogeneradores síncronos ~3MW c/u. FPO "
            "declarada ya vencida al momento del informe (jun-2025) sin "
            "reporte de avance."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico Arrizal",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 195,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2024, 10, 31),
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025: "
            "FPO declarada 31-oct-2024; el informe indica explícitamente "
            "'No se ha recibido información' de avance del promotor."
        ),
        "notas": (
            "Promotor Jemeiwaa Ka'i (complejo AES Colombia), Uribia, La "
            "Guajira. 195 MW con aerogeneradores síncronos entre 3 y 5 MW "
            "c/u. FPO declarada ya vencida al momento del informe "
            "(jun-2025) sin reporte de avance."
        ),
    },
    {
        "nombre_proyecto": "Parque Eólico Acacia 2",
        "tipo": "GENERACION",
        "tecnologia": "EOLICA",
        "capacidad_mw": 80,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2023, 12, 1),
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": date(2024, 6, 1),
        "estado": "OPERANDO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.6, corte 31-dic-2022): declara "
            "entrada en operación en junio de 2024, 3 meses después de la "
            "línea Copey-Cuestecitas 500kV, con 6 meses de atraso frente "
            "al Inicio del Período de Vigencia de la Obligación (IPVO, "
            "dic-2023)."
        ),
        "notas": (
            "Promotor Begonia Power. El informe UPME cita el mes exacto "
            "de entrada (junio de 2024) e IPVO (diciembre de 2023) sin "
            "precisar el día calendario; se usa el día 1 de cada mes como "
            "convención. Dependía de la línea UPME 09-2016 Copey-"
            "Cuestecitas 500 kV."
        ),
    },
    # ------------------------------------------------------------------
    # GENERACIÓN — SOLAR
    # ------------------------------------------------------------------
    {
        "nombre_proyecto": "Planta Solar La Orquídea",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 200,
        "departamento": "Bolívar",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2027, 5, 17),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.2, corte 31-dic-2024): avance real "
            "26,8% vs. 55% programado (retraso 28,2%); 137 días de atraso "
            "frente al 31-dic-2026 declarado en cronograma y curva S. FPO "
            "estimada por auditoría: 17-may-2027."
        ),
        "notas": (
            "Promotor La Orquídea Solar S.A.S. Municipios Santa Catalina y "
            "Clemencia, Bolívar. Se conecta a la SE Bolívar 220 kV vía "
            "línea de 18-20 km."
        ),
    },
    {
        "nombre_proyecto": "Parque Solar Villavieja",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 200,
        "departamento": "Huila",
        "area_operativa": None,
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2026, 11, 30),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.2, corte 31-dic-2024): avance real "
            "32% vs. 43% programado (retraso 11%); 93 días de atraso "
            "frente al 31-ago-2026 declarado. FPO estimada: 30-nov-2026."
        ),
        "notas": (
            "Promotor Solar Villavieja S.A.S ESP, municipio de Villavieja, "
            "Huila. Depende de obras de la nueva subestación Huila "
            "(Norte) 230 kV y obras adicionales en el STR."
        ),
    },
    {
        "nombre_proyecto": "Parque Solar Las Palmeras",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 200,
        "departamento": "Cesar",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2026, 6, 27),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.2, corte 31-dic-2024): avance real "
            "42,59% vs. 48% programado; 178 días de atraso frente al "
            "31-dic-2025 declarado. FPO estimada: 27-jun-2026."
        ),
        "notas": "Promotor Generadora San Joaquín S.A.S., municipio El Copey, Cesar.",
    },
    {
        "nombre_proyecto": "Parque Solar Fotovoltaico Cimitarra",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 200,
        "departamento": "Santander",
        "area_operativa": None,
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2027, 11, 12),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.2, corte 31-dic-2024): avance real "
            "20,79% vs. 27,97% programado; 135 días de atraso. FPO "
            "estimada aplicando plan de contingencia: 12-nov-2027."
        ),
        "notas": (
            "Promotor Proyecto Solar Cimitarra S.A.S., municipio "
            "Cimitarra, Santander. La auditoría indica que las "
            "actividades tuvieron que reiniciarse desde la fase de "
            "búsqueda y negociación de predios."
        ),
    },
    {
        "nombre_proyecto": "Parque Solar Fotovoltaico Valledupar",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 100,
        "departamento": "Cesar",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2027, 6, 30),
        "fecha_entrada_real": None,
        "estado": "EN_CONSTRUCCION",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.2, corte 31-dic-2024): el proyecto "
            "'se encuentra al día' frente al cronograma declarado "
            "(30-jun-2027), sin atraso reportado."
        ),
        "notas": (
            "Promotor Enel Colombia S.A. E.S.P., Valledupar, Cesar. "
            "Incluido como contraste: proyecto solar grande en la Costa "
            "Caribe que, a la fecha del informe, no registra atraso."
        ),
    },
    {
        "nombre_proyecto": "Atlántico Photovoltaic",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 199.5,
        "departamento": "Atlántico",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2026, 10, 13),
        "fecha_entrada_planeada_vigente": date(2026, 10, 19),
        "fecha_entrada_real": None,
        "estado": "EN_CONSTRUCCION",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.2, corte 31-dic-2024): avance real "
            "14,3% vs. 14,9% programado (retraso de solo 0,6%); 6 días de "
            "atraso frente al 13-oct-2026 declarado en cronograma y curva "
            "S. Auditoría concluye que no hay condición de atraso grave."
        ),
        "notas": (
            "Promotor Enel Colombia S.A. ESP, municipios Sabanalarga y "
            "Usiacurí, Atlántico. Incluido como ejemplo de atraso menor, "
            "no estructural, para contraste con los casos de La Guajira."
        ),
    },
    {
        "nombre_proyecto": "Parque Solar Guayepo I-II",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 400,
        "departamento": "Atlántico",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": date(2024, 11, 30),
        "estado": "OPERANDO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.12, corte 18-feb-2025): 604 días de "
            "atraso frente a la fecha programada en cronograma/curva S "
            "declarada por el promotor; en el Acuerdo CNO 1612, Enel "
            "Colombia declaró la entrada en operación del proyecto a "
            "partir del 30-nov-2024."
        ),
        "notas": (
            "Promotor Enel Colombia S.A. E.S.P., municipios Ponedera y "
            "Sabanalarga, Atlántico. Capacidad efectiva neta declarada 370 "
            "MW (columna MW del informe: 400 MWdc/486.7 MWp). Ejemplo de "
            "proyecto grande que entró en operación con más de año y medio "
            "de atraso documentado frente a su cronograma original."
        ),
    },
    {
        "nombre_proyecto": "Bosques Solares de los Llanos 6",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 79.6,
        "departamento": "Meta",
        "area_operativa": None,
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2026, 5, 31),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.2, corte 31-dic-2024): avance real "
            "45% vs. 47,5% programado; 151 días de atraso frente al "
            "31-dic-2025 declarado. FPO estimada: 31-may-2026."
        ),
        "notas": "Promotor Bosques Solares de los Llanos 6 S.A.S. E.S.P., Villavicencio, Meta.",
    },
    {
        "nombre_proyecto": "Parque Solar Puerta de Oro",
        "tipo": "GENERACION",
        "tecnologia": "SOLAR",
        "capacidad_mw": 360,
        "departamento": "Cundinamarca",
        "area_operativa": None,
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2026, 3, 31),
        "fecha_entrada_real": date(2026, 9, 1),
        "estado": "OPERANDO",
        "fuente": (
            "El Tiempo, 'El parque solar más grande de Colombia entrará "
            "en operación en 2026, aseguró el gobernador de Cundinamarca, "
            "Jorge Rey'; Bloomberg Línea, 'El parque solar más grande de "
            "Colombia cambia de manos' (21-sep-2026, confirma entrada en "
            "operación comercial y venta de Patria Investments a Isagen)."
        ),
        "notas": (
            "Municipios de Guaduas y Chaguaní, Cundinamarca. 360 MWp, "
            "inversión de USD 280 millones, 530 ha, más de 511.000 "
            "módulos. Incluido como CONTRASTE: mayor planta solar del "
            "país, sin retraso estructural mayor documentado en prensa — "
            "el día exacto de entrada en operación comercial dentro de "
            "septiembre de 2026 no se precisó en la fuente, se usa el "
            "día 1 como convención."
        ),
    },
    # ------------------------------------------------------------------
    # GENERACIÓN — TÉRMICA
    # ------------------------------------------------------------------
    {
        "nombre_proyecto": "Termocaribe 3",
        "tipo": "GENERACION",
        "tecnologia": "TERMICA",
        "capacidad_mw": 42,
        "departamento": "Bolívar",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2023, 11, 30),
        "fecha_entrada_real": None,
        "estado": "EN_CONSTRUCCION",
        "fuente": (
            "UPME, Informe de avance proyectos de generación – Junio 2025 "
            "(Informe de auditoría No.11, corte 30-sep-2024): curva S "
            "muestra 100% de obras ejecutadas al 21-mar-2024; capacidad de "
            "transporte reasignada por UPME hasta 52 MW."
        ),
        "notas": (
            "Promotor Termocaribe S.A.S., Santa Rosa de Lima (Cartagena), "
            "Bolívar. Turbina Siemens SGT-800 a GLP/gas natural. El "
            "informe no trae una declaración explícita de entrada en "
            "operación comercial pese al 100% de avance físico, por lo que "
            "se deja fecha_entrada_real en NULL y estado EN_CONSTRUCCION."
        ),
    },
    # ------------------------------------------------------------------
    # GENERACIÓN — HIDRÁULICA
    # ------------------------------------------------------------------
    {
        "nombre_proyecto": "Hidroituango — Unidades de generación 5 a 8",
        "tipo": "GENERACION",
        "tecnologia": "HIDRAULICA",
        "capacidad_mw": 1200,
        "departamento": "Antioquia",
        "area_operativa": "Antioquia",
        "fecha_entrada_planeada_original": date(2025, 6, 30),
        "fecha_entrada_planeada_vigente": date(2028, 3, 31),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "El Colombiano, 'Cronograma de generación de las unidades de "
            "Hidroituango entre 2022 y 2025' (cronograma original EPM "
            "2022: última unidad en el primer semestre de 2025); El "
            "Colombiano, 'Hidroituango superó el 93,4% de ejecución y "
            "avanza para encenderse del todo en 2028' (unidades 5-7 "
            "esperadas 2do semestre 2027, unidad 8 en el 1er trimestre "
            "2028)."
        ),
        "notas": (
            "Central hidroeléctrica de EPM, río Cauca, Antioquia. Las "
            "unidades 1-4 (1.200 MW) ya operan; esta fila cubre solo la "
            "capacidad de las 4 unidades restantes (5-8), aún no operando "
            "a la fecha de consulta. Retraso originado en la contingencia "
            "de 2018 (taponamiento de túneles de desviación) y ajustes "
            "constructivos posteriores. fecha_entrada_planeada_vigente usa "
            "el 31-mar-2028 como aproximación del 'primer trimestre de "
            "2028' citado por la fuente."
        ),
    },
    # ------------------------------------------------------------------
    # TRANSMISIÓN
    # ------------------------------------------------------------------
    {
        "nombre_proyecto": "Línea Colectora 500 kV (UPME 06-2017, tramos Cuestecitas-La Loma y Colectora-Cuestecitas)",
        "tipo": "TRANSMISION",
        "tecnologia": "LINEA",
        "capacidad_mw": None,
        "departamento": "La Guajira",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2025, 12, 31),
        "fecha_entrada_planeada_vigente": date(2027, 4, 30),
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "UPME, Plan de Expansión de Transmisión 2025-2039 (tabla de "
            "proyectos de transmisión, sección 3.1.3): FPO declarada 2025 "
            "para ambos tramos (UPME 06-2017); El Colombiano, 'Colectora "
            "contra reloj: tras 235 consultas, la gran autopista de la "
            "energía solar y eólica de Colombia verá la luz este año': "
            "tras 4 años de retrasos, la nueva fecha proyectada por Enlaza "
            "es abril de 2027."
        ),
        "notas": (
            "500 kV, La Guajira/Cesar. Operador Enlaza (subsidiaria de "
            "Grupo Energía Bogotá). Transporta ~1.050 MW de generación "
            "solar y eólica de La Guajira, incluyendo los parques del "
            "complejo Jemeiwaa Ka'i (JK1, JK2, Irraipa, Arrizal) y Alpha/"
            "Beta/Camelias/Windpeshi de este mismo dataset. Retraso "
            "atribuido a exigencia de consultas previas: El Tiempo (sep-"
            "2026) reporta 267 comunidades consultadas en total y 18 "
            "nuevas comunidades identificadas en 2025 más 4 en 2026; "
            "Diario La Libertad (03-sep-2026) reporta un nuevo retraso por "
            "18 comunidades adicionales. fecha_entrada_planeada_original "
            "corresponde a la FPO 2025 del Plan de Transmisión "
            "2025-2039 (no se logró acceder a una versión anterior del "
            "Plan con la FPO originalmente comprometida en el contrato de "
            "adjudicación, por lo que esta fecha podría no ser la primera "
            "jamás declarada)."
        ),
    },
    {
        "nombre_proyecto": "UPME 09-2016 Copey-Cuestecitas 500 kV y Copey-Fundación 220 kV",
        "tipo": "TRANSMISION",
        "tecnologia": "LINEA",
        "capacidad_mw": None,
        "departamento": "Cesar",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": date(2025, 12, 31),
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": date(2025, 8, 6),
        "estado": "OPERANDO",
        "fuente": (
            "UPME, Plan de Expansión de Transmisión 2025-2039 (FPO "
            "declarada 2025); cobertura de intervención/seguimiento UPME "
            "citada en prensa especializada: el proyecto entró en "
            "operación comercial el 06-ago-2025."
        ),
        "notas": (
            "500 kV / 220 kV, Cesar/La Guajira/Magdalena. Obra clave para "
            "evacuar generación eólica de La Guajira; entró en operación "
            "antes de lo declarado en el Plan 2025-2039 (dic-2025), por lo "
            "que se marca OPERANDO sin atraso frente a esa fecha de "
            "referencia. Sirve de insumo directo para el Parque Eólico "
            "Acacia 2 de este mismo dataset."
        ),
    },
    {
        "nombre_proyecto": "UPME 07-2016 Línea de Transmisión La Virginia - Nueva Esperanza 500 kV",
        "tipo": "TRANSMISION",
        "tecnologia": "LINEA",
        "capacidad_mw": None,
        "departamento": "Risaralda",
        "area_operativa": None,
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "Portafolio, 'El 85% de proyectos de líneas de transmisión "
            "presentan atrasos' (incluye este proyecto entre los que "
            "acumulan 5 o más años de atraso); BNamericas, ficha de "
            "proyecto 'Segundo Refuerzo de Red en el Área Oriental — "
            "Línea de Transmisión La Virginia - Nueva Esperanza 500kV "
            "(UPME 07-2016)': a corte 30-sep-2024 registraba 96,1% de "
            "avance en fase de construcción."
        ),
        "notas": (
            "500 kV, conecta la subestación La Virginia (Risaralda, "
            "Pereira) con Nueva Esperanza (Cundinamarca), atravesando "
            "también Caldas y Tolima. Adjudicado el 22-nov-2016 a "
            "Transmisora Colombiana de Energía (TCE, filial de ISA). No "
            "se encontró en las fuentes consultadas una fecha calendario "
            "explícita de FPO originalmente comprometida ni una fecha "
            "vigente reformulada con precisión de día — se dejan ambos "
            "campos en NULL en vez de aproximarlos."
        ),
    },
    {
        "nombre_proyecto": "UPME 03-2010 Subestación Chivor II y Norte 230 kV",
        "tipo": "TRANSMISION",
        "tecnologia": "SUBESTACION",
        "capacidad_mw": None,
        "departamento": "Boyacá",
        "area_operativa": None,
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": None,
        "fecha_entrada_real": None,
        "estado": "RETRASADO",
        "fuente": (
            "Portafolio, 'El 85% de proyectos de líneas de transmisión "
            "presentan atrasos' (agrupa este proyecto junto con Suria, "
            "Montería, Armenia y Tesalia como 'programados desde el 2009 "
            "al 2013'); Portafolio, 'ANLA da vía libre a tramo final de "
            "Chivor II, proyecto que llevará más capacidad eléctrica "
            "hacia Bogotá y al centro' (aprobación del tramo final "
            "Norte-Bacatá)."
        ),
        "notas": (
            "230 kV, subestaciones Chivor II y Norte más líneas asociadas "
            "de ~162 km entre Boyacá (7 municipios) y Cundinamarca (13 "
            "municipios). Adjudicado por UPME en 2010. Desarrollador "
            "Grupo Energía Bogotá (GEB). La fuente agrupa el proyecto con "
            "otros 4 sin dar una fecha original específica por proyecto, "
            "por lo que no se completan las fechas planeadas: son más de "
            "una década de atraso acumulado según la cobertura consultada, "
            "pero sin un dato de fecha exacta atribuible solo a este "
            "proyecto."
        ),
    },
    {
        "nombre_proyecto": "UPME 04-2019 Línea de Transmisión La Loma - Sogamoso 500 kV",
        "tipo": "TRANSMISION",
        "tecnologia": "LINEA",
        "capacidad_mw": None,
        "departamento": "Cesar",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2026, 12, 31),
        "fecha_entrada_real": None,
        "estado": "EN_CONSTRUCCION",
        "fuente": (
            "UPME, Plan de Expansión de Transmisión 2025-2039 (tabla de "
            "proyectos de transmisión considerados para la evaluación de "
            "compensadores síncronos del Área Caribe, sección 3.1.3): FPO "
            "declarada 2026."
        ),
        "notas": (
            "500 kV, parte del refuerzo de evacuación de generación de "
            "Cesar/La Guajira hacia el interior del país. No se encontró "
            "cobertura de prensa con evidencia específica de atraso para "
            "este proyecto puntual (a diferencia de Colectora o La "
            "Virginia-Nueva Esperanza); se deja estado EN_CONSTRUCCION en "
            "vez de RETRASADO por no tener esa evidencia directa, aunque "
            "el director de UPME ha señalado en prensa que el 60% de los "
            "proyectos del STN registran algún atraso en general."
        ),
    },
    {
        "nombre_proyecto": "Segundo circuito Cerromatoso - Sahagún - Chinú 500 kV",
        "tipo": "TRANSMISION",
        "tecnologia": "LINEA",
        "capacidad_mw": None,
        "departamento": "Córdoba",
        "area_operativa": "Caribe",
        "fecha_entrada_planeada_original": None,
        "fecha_entrada_planeada_vigente": date(2026, 6, 30),
        "fecha_entrada_real": None,
        "estado": "EN_CONSTRUCCION",
        "fuente": (
            "Cobertura de prensa especializada sobre refuerzo de "
            "transmisión de la Costa Caribe (búsqueda web, sep-2026): "
            "proyecto de refuerzo del área Caribe con entrada programada "
            "en junio de 2026."
        ),
        "notas": (
            "500 kV, Córdoba. Parte del paquete de refuerzos de la Costa "
            "Caribe mencionados junto a Colectora y compensadores "
            "síncronos en la entrevista al director de UPME (El "
            "Colombiano). La fuente consultada es un resumen de búsqueda "
            "web, no un documento primario con URL verificada línea por "
            "línea — se recomienda confirmar contra el próximo informe "
            "UPME de seguimiento de obras de transmisión antes de usar "
            "este dato en un análisis publicado."
        ),
    },
]


if __name__ == "__main__":
    repo = UpmeProyectosRepository()
    insertados = 0
    for proyecto in PROYECTOS:
        repo.upsert_proyecto(proyecto)
        insertados += 1
    print(f"Procesados {insertados} proyectos de {len(PROYECTOS)} en PROYECTOS "
          f"(upsert por nombre_proyecto+tipo: nuevos se insertan, existentes se actualizan).")
