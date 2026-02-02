# Plan de Refactorización Gradual - Módulo Hidrología y Generación (2026)

## Estado Actual (Diagnóstico)
El módulo de Hidrología (`generacion_hidraulica_hidrologia.py`) es un "God Script" de >7,500 líneas que mezcla:
-   **Presentación**: Layouts de Dash, callbacks, gráficos Plotly.
-   **Lógica de Negocio**: Cálculos de reservas, aportes, medias históricas.
-   **Infraestructura**: Llamadas directas a API XM, PyDataXM, caché manual con SQLite.
-   **Utilidades**: Formateo de fechas, manejo de geojson.

Esto hace que el mantenimiento sea riesgoso y lento.

## Estrategia de Migración (Patrón Strangler Fig)
No reescribiremos todo de cero. Migraremos funcionalidad pieza por pieza a la nueva arquitectura limpia (`domain/services` -> `interface`).

### Fase 1: Capa de Dominio (HydrologyService)
**Objetivo**: Centralizar la lógica de negocio y acceso a datos.

1.  **Crear `domain/services/hydrology_service.py`**:
    -   Este servicio actuará como fachada para todas las operaciones de hidrología.
2.  **Migrar Consultas Básicas**:
    -   Mover `get_reservas_hidricas(fecha)` y `get_aportes_hidricos(fecha)` al servicio.
    -   El servicio usará internamente `MetricsService` o `XMService` (infrastructure), desacoplando la vista de la fuente de datos.
3.  **Refactorizar Dash (Paso Seguro)**:
    -   En el archivo Dash, reemplazar la implementación local de `get_reservas_hidricas` por `hydrology_service.get_reservas_hidricas()`.
    -   **Beneficio inmediato**: Se eliminan ~500 líneas de código del archivo UI.

### Fase 2: Lógica de Negocio Compleja
**Objetivo**: Sacar la lógica de cálculo de medias y KPIs.

1.  **Migrar Cálculos**:
    -   Mover lógica de "Media Histórica" y "Porcentajes vs Histórico" al servicio.
    -   El servicio debe devolver DataFrames listos para graficar o diccionarios (DTOs), no objetos gráficos.
2.  **Normalización de Datos**:
    -   Unificar la limpieza de nombres de embalses/ríos dentro del servicio.

### Fase 3: Desacoplamiento de Vista
**Objetivo**: Que el archivo Dash solo contenga Layout y Callbacks.

1.  **Separar Gráficos**:
    -   Mover funciones `crear_grafica_...` a `interface/components/charts/hydrology_charts.py`.
2.  **Simplificar Callbacks**:
    -   Los callbacks en Dash deben ser de <50 líneas:
        ```python
        def update_graph(fecha):
            data = hydrology_service.get_data(fecha)
            return hydrology_charts.create_main_chart(data)
        ```

### Hoja de Ruta Sugerida

| Sprint | Tarea | Impacto (Líneas reducidas) | Riesgo |
| :--- | :--- | :--- | :--- |
| **1** | Limpieza de Logs y Imports (Completado) | ~100 | Bajo |
| **2** | Implementar `HydrologyService` básico | ~800 | Medio |
| **3** | Migrar lógica de Mapas/GeoJSON a `GeoService` | ~1,200 | Bajo |
| **4** | Extraer componentes gráficos a `charts/` | ~2,500 | Medio |
| **5** | Refactor final de Callbacks | ~500 | Alto |

## Recomendaciones Técnicas
-   **No usar `print`**, usar siempre `logger` inyectado.
-   **Tipado**: Usar `Type Hints` en el nuevo servicio desde el día 0.
-   **Tests**: Crear test unitario para `HydrologyService` antes de conectarlo a la UI.
