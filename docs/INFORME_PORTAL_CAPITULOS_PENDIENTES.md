# Capítulos portal — suspendidos del Informe Ejecutivo

Desde **junio 2026**, los capítulos de dashboards del portal **no se incluyen**
en el Informe Ejecutivo diario (`send_daily_generate`). Se reservan para un
**informe portal separado** que se construirá de forma incremental.

El informe ejecutivo diario conserva solo el sector eléctrico + gestión de riesgos + noticias.
Ver [`INFORME_EJECUTIVO_CONTENIDO.md`](INFORME_EJECUTIVO_CONTENIDO.md).

---

## Capítulos suspendidos

| Capítulo | Builder HTML | Fetch SQL | Gráficos Plotly |
|----------|--------------|-----------|-----------------|
| Comunidades energéticas | `domain/services/report_chapters/chapter_comunidades.build_chapter_comunidades` | `whatsapp_bot/services/informe_portal_data.fetch_comunidades_full` | `com_mapa`, `com_barras_ces`, `com_inversion` |
| Contratos OR | `build_chapter_contratos_or` | `fetch_contratos_or_full` | `or_gauge_fin`, `or_gauge_gen`, `or_gauge_fis`, `or_proyectos` |
| FENOGÉ | `build_chapter_fenoge` | `fetch_fenoge_full` | `fen_deptos`, `fen_inversion`, `fen_seguimiento` |
| Colombia Solar (curvas S) | `build_chapter_colombia_solar` | `fetch_curva_s` | `curva_obras`, `curva_usuarios`, `curva_potencia`, `curva_internas` |
| Subsidios | `chapter_subsidios.build_chapter_subsidios` | `fetch_subsidios_full` | `sub_subsidios_contrib`, `sub_deficit_combo`, `sub_apropiacion`, `sub_trimestres`, `sub_gauge_pagado`, `sub_prestadores`, `sub_valid_sin`, `sub_valid_zni` |
| Supervisión | `chapter_supervision.build_chapter_supervision` | `fetch_supervision_full` | `sup_gauge_pf`, `sup_gauge_pfin`, `sup_gauge_ef`, `sup_gauge_efin`, `sup_pie_fondos`, `sup_evolucion`, `sup_fondo_estado` |
| Presupuesto DEE | `chapter_presupuesto.build_chapter_presupuesto` | `fetch_presupuesto_full` | `pre_gauge_comp`, `pre_gauge_obl`, `pre_gauge_disp`, `pre_ejecucion`, `pre_proyectos` |

---

## Esquemas PostgreSQL

| Capítulo | Esquema / tablas principales |
|----------|------------------------------|
| Comunidades | `comunidades.base` |
| Contratos OR | esquema comunidades + tablas OR |
| FENOGÉ | `fenoge.*` |
| Colombia Solar | `colombia_solar.*` (proyectado/reportado por categoría) |
| Subsidios | `subsidios.deficit_historico`, `subsidios.subsidios_pagos`, `subsidios.subsidios_validaciones` |
| Supervisión | `supervision.contratos` |
| Presupuesto DEE | `presupuesto.resumen` |

---

## Código reutilizable (sin borrar)

Para el futuro informe portal, reutilizar tal cual:

```
whatsapp_bot/services/informe_portal_data.py    → fetch_all_portal_dashboards()
whatsapp_bot/services/informe_portal_charts.py  → generate_all_portal_charts()
domain/services/report_chapters/                → builders HTML por capítulo
```

Ensamblado previo (retirado de `generar_pdf_informe`):

```python
from domain.services.report_chapters import (
    build_chapter_comunidades,
    build_chapter_contratos_or,
    build_chapter_fenoge,
    build_chapter_colombia_solar,
    build_chapter_subsidios,
    build_chapter_supervision,
    build_chapter_presupuesto,
)

portal_data = fetch_all_portal_dashboards()
portal_chart_paths = generate_all_portal_charts(portal_data)

# pages = [build_chapter_*() for each dashboard...]
```

---

## Notas para el informe portal futuro

- Los tableros Next.js del portal ya consumen las mismas fuentes SQL; este informe sería la versión PDF periódica de esos dashboards.
- Generar ~34 PNG adicionales por ejecución; considerar tarea Celery independiente con schedule distinto al informe ejecutivo (8:30 AM).
- No mezclar con el informe del sector eléctrico: audiencias y cadencia pueden diferir.

---

*Suspendido: junio 2026 · Informe ejecutivo diario = sector + riesgos + noticias únicamente.*
