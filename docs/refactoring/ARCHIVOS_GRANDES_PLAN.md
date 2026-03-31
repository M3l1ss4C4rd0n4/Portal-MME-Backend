# Plan de División de Archivos Grandes

## Archivos Identificados (>1000 líneas)

### 1. report_service.py (1,850 líneas) → 4 archivos

**Estructura propuesta:**
```
domain/services/reports/
├── __init__.py                    # Exporta ReportService
├── base.py                        # Clases base y utilidades (200 líneas)
├── generators.py                  # Generadores de reportes (600 líneas)
├── exporters.py                   # Exportadores (PDF, Excel, etc) (500 líneas)
└── report_service.py              # Fachada principal (550 líneas)
```

### 2. executive_report_service.py (1,636 líneas) → 3 archivos

**Estructura propuesta:**
```
domain/services/executive/
├── __init__.py                    # Exporta ExecutiveReportService
├── data_collectors.py             # Recolectores de datos (500 líneas)
├── formatters.py                  # Formateadores (400 líneas)
└── executive_report_service.py    # Orquestador (736 líneas)
```

### 3. losses_nt_service.py (1,204 líneas) → 2 archivos

**Estructura propuesta:**
```
domain/services/losses/
├── __init__.py                    # Exporta LossesNTService
├── calculations.py                # Cálculos y fórmulas (500 líneas)
└── losses_nt_service.py           # API pública (704 líneas)
```

### 4. notification_service.py (1,154 líneas) → 2 archivos

**Estructura propuesta:**
```
domain/services/notifications/
├── __init__.py                    # Exporta NotificationService
├── channels.py                    # Canales de notificación (500 líneas)
└── notification_service.py        # Gestor principal (654 líneas)
```

### 5. cu_service.py (1,021 líneas) → 2 archivos

**Estructura propuesta:**
```
domain/services/cu/
├── __init__.py                    # Exporta CUService
├── calculations.py                # Cálculos de costos (450 líneas)
└── cu_service.py                  # API pública (571 líneas)
```

## Beneficios Esperados

1. **Mantenibilidad:** Archivos más pequeños son más fáciles de entender
2. **Testing:** Mejor cobertura de tests por módulo
3. **Colaboración:** Menos conflictos de merge
4. **Reusabilidad:** Componentes más modulares

## Nota de Implementación

La división completa de estos archivos requiere:
1. Análisis detallado de dependencias internas
2. Actualización de todas las importaciones
3. Tests de regresión exhaustivos
4. Coordinación con el equipo de desarrollo

Por lo tanto, se recomienda realizar esta refactorización en un sprint dedicado.
