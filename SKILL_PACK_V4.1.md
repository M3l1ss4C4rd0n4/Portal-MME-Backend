# SKILL_PACK_V4.1.md — "Field Medic Framework"

> **Versión:** 4.1 — Definitiva (Física de hardware validada. Límites del LLM mitigados.)
>
> **Filosofía:** Un marco teórico perfecto que mata la base de datos en producción no es un marco perfecto.
> La física del hardware manda, y la aritmética de los LLMs miente.
>
> **Aplicable a:** Portal Dirección MME Backend (Python 3.11 + FastAPI, 48GB PostgreSQL, 64M+ rows, 0 FKs, god container 575 nodos)
> **Frontend referencia:** `/home/admonctrlxm/portal-direccion-mme/SKILL_PACK_V4.1.md`

---

## PRINCIPIO FUNDAMENTAL: Jerarquía de Verdad (con Pesos)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    JERARQUÍA DE VERDAD — SISTEMA DE PESOS              │
│                    (Decisiones se basan en PESO ACUMULADO ≥ 0.7)       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  NIVEL 1: ESTADO OBSERVABLE (Runtime)                                  │
│  ├── pytest PASA con el cambio propuesto              +0.40            │
│  ├── pytest FALLA con el cambio propuesto            -0.40            │
│  ├── curl /health retorna 200                        +0.25            │
│  ├── SELECT COUNT(*) coincide pre/post               +0.25            │
│  ├── pm2 logs sin errores en últimos 5 min           +0.10            │
│  └── SELECT pg_size_pretty ejecuta sin timeout       +0.15            │
│                                                                         │
│  NIVEL 2: ANÁLISIS ESTÁTICO VERIFICABLE (AST)                         │
│  ├── grep -B5 -A5 confirma uso real                  +0.30            │
│  ├── python -c "import X; print(dir(X))" verifica export  +0.30       │
│  ├── python -m py_compile verifica sintaxis          +0.25            │
│  └── No ImportError al hacer cyclic import test      +0.25            │
│                                                                         │
│  NIVEL 3: INFERENCIA ESTRUCTURAL (Graphify)                            │
│  ├── graphify query (aristas EXTRACTED)              +0.20            │
│  ├── graphify query (aristas INFERRED)               +0.08            │
│  ├── GRAPH_REPORT.md zona >50% INFERRED              +0.03            │
│  ├── graphify path (navegación de dependencias)      +0.15            │
│  └── GRAPH_REPORT.md hubs y comunidades (orientación)  +0.10          │
│                                                                         │
│  NIVEL 4: SUPUESTOS (Lo que NO es verdad hasta verificado)             │
│  ├── "Este servicio probablemente no se usa"         0.00             │
│  ├── "Esta función hace lo que el nombre sugiere"    0.00             │
│  ├── "La multiplicación que hice en mi cabeza"       0.00             │
│  └── "Confío en mi memoria de 20 segundos atrás"     0.00             │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                         REGLA DE ORO DE DECISIÓN                       │
│                                                                         │
│  PESO_ACUMULADO = Σ(pesos de todas las fuentes consultadas)           │
│                                                                         │
│  ├─ PESO ≥ 0.7  → EJECUTAR sin aprobación adicional                   │
│  ├─ PESO 0.5-0.69 → EJECUTAR + verificación extra en Fase 3          │
│  ├─ PESO 0.3-0.49 → INVESTIGAR más (buscar N1 adicional)             │
│  ├─ PESO 0.1-0.29 → HIPÓTESIS (documentar, NO ejecutar)               │
│  └─ PESO < 0.1 → IGNORAR, solicitar contexto al humano                │
│                                                                         │
│  NUNCA tomar decisión de cambio basada exclusivamente en Nivel 3 o 4.  │
│  SIEMPRE buscar AL MENOS UNA confirmación en Nivel 1 o 2.             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## META-SKILL 0: Ciclo de Diagnóstico del Agente (CDA)

### 0.1 Las 7 Fases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   CICLO DE DIAGNÓSTICO DEL AGENTE (CDA)                │
│                    7 FASES — Una por una, sin saltar                   │
├─────────────────────────────────────────────────────────────────────────┤

FASE 1: OBSERVAR → ¿Qué ESTADO observable tengo?
├─ Ejecutar NIVEL 1: pytest, curl, psql COUNT, systemctl status
├─ REGISTRAR baseline en archivo (no en memoria)
├─ Ejemplo:
│  ├─ pytest tests/ -q --tb=no > /tmp/baseline_tests.txt
│  ├─ curl -s http://localhost:8000/health | head -1 > /tmp/baseline_health.txt
│  ├─ psql -d portal_energetico -c "SELECT COUNT(*) FROM tabla" > /tmp/baseline_count.txt
│  └─ pg_size_pretty(pg_relation_size('tabla')) → /tmp/baseline_size.txt
└─ SIN este baseline escrito, las fases 6-7 fallarán (no hay qué comparar)

FASE 2: PALPAR → ¿Qué puedo verificar con NIVEL 2 (AST)?
├─ grep -rn "NombreServicio" /home/admonctrlxm/server/ --include="*.py" -B5 -A5
├─ python -c "from modulo import Clase; print(dir(Clase))" → /tmp/palpar_exports.txt
├─ python -m py_compile archivo.py
├─ Si toca imports: python -c "from A import X; from B import Y; print('OK')"
│  └─ Si falla ImportError → CICLO ESTÁTICO (ir a Fase 2.5)
└─ Registrar: grep hallazgos en /tmp/palpar_*.txt

FASE 3: MAPEAR → ¿Qué me dice el GRAFO como MAPA (no como VERDAD)?
├─ cat /home/admonctrlxm/server/graphify-out/GRAPH_REPORT.md | head -80
├─ Identificar:
│  ├─ Hubs (nodos con >20 aristas) — probable god file o god service
│  ├─ Comunidades (clusters de nodos altamente acoplados)
│  ├─ Porcentaje de aristas EXTRACTED vs INFERRED en GRAPH_REPORT
│  └─ Si >50% INFERRED en zona de interés → DESCONFIANZA ELEVADA (peso 0.03)
├─ graphify query "dependencias de X" --budget 3000
└─ NUNCA confundir: "El grafo dice que A depende de B" ≠ "A efectivamente depende de B"

FASE 4: DIAGNOSTICAR → ¿Cuál es la ENFERMEDAD real?
├─ Distinguir SÍNTOMA vs CAUSA
│  ├─ Síntoma: "Este archivo tiene 575 nodos"
│  ├─ Causa: "El container acopla 40 servicios sin factories ni interfaces"
│  └─ Tratamiento debería atacar la CAUSA, no el síntoma
├─ Si hay ciclos:
│  ├─ Tipo ESTÁTICO (python -c falló) → Extraer interfaz (Skill 1.3a)
│  ├─ Tipo LÓGICO (Container inyecta A→B→A) → Dependency Inversion (Skill 1.3b)
│  └─ Registrar AMBOS tipos en /tmp/diag_[tarea].md
├─ Si afecta datos (DB/ETL): Ir a Skill 9 (seleccionar Método A/B/C/D por tamaño)
└─ Si es god service: Registrar líneas y output canónico

FASE 5: TRATAR → ¿Cuál es la intervención MÍNIMA?
├─ NUNCA: "Voy a refactorizar todo el servicio de una vez"
├─ SÍ: "Voy a crear una interfaz, migrar 1 consumidor, verificar, commit, repetir"
├─ Si la causa es un ciclo → ROMPER EL CICLO PRIMERO (antes de cualquier extracción)
├─ Si la causa es data corruption → VERIFICAR CON MÉTODO CORRECTO PRIMERO
├─ Crear SOLAMENTE archivos nuevos (<500 líneas cada uno)
│  └─ NO modificar god files sin plan escrito
└─ Registrar pasos en /tmp/diag_[tarea].md

FASE 6: PERSISTIR → Guardar estado en ARCHIVO, NO en memoria
├─ ESCRIBIR /tmp/diag_[tarea].md (ver formato exacto en 0.2)
├─ INCLUIR: Timestamp, Baseline, Ciclos, Archivos, Decisión, Rollback
└─ GUARDAR INMEDIATAMENTE tras completar Fase 5 (no esperar a Fase 7)

FASE 7: MONITOREAR → ¿El tratamiento funcionó?
├─ PASO 1: LEER /tmp/diag_[tarea].md (obtener baseline original)
│  └─ Si el archivo fue borrado o no existe → PAUSAR y PEDIR baseline al humano
├─ PASO 2: Re-ejecutar comandos de Fase 1 + comparar
├─ PASO 3: Comparar BYTE POR BYTE contra baseline
│  ├─ diff /tmp/baseline_tests.txt /tmp/post_tests.txt
│  ├─ diff /tmp/baseline_count.txt /tmp/post_count.txt
│  └─ diff /tmp/baseline_health.txt /tmp/post_health.txt
├─ PASO 4: Si datos (aplica Skill 9 Método correspondiente)
│  ├─ Comparar checksum/proxy contra baseline
│  ├─ Si tabla >10GB: Pedir permiso para ANALYZE antes de re-verificar pg_stats
│  └─ Si hay discrepancia: NO entrar en pánico, investigar si >10% en proxies
├─ PASO 5: Decisión
│  ├─ Si TODO coincide → Finalizar. El tratamiento funcionó. ✅
│  ├─ Si algo cambió pero es ESPERADO → Documentar por qué es aceptable. ✅
│  ├─ Si algo cambió y NO es esperado → ❌ REVERTIR Y REDIAGNOSTICAR
│  │  └─ git revert [hash de Fase 5]
│  │  └─ Volver a Fase 4 (diagnóstico)
│  └─ Actualizar /tmp/diag_[tarea].md con resultado
├─ PASO 6: Limpiar
│  ├─ Si tarea EXITOSA: rm /tmp/diag_[tarea].md /tmp/baseline_* /tmp/post_*
│  └─ Si tarea FALLÓ: CONSERVAR /tmp/diag_[tarea].md para análisis post-mortem
└─ FIN CDA
```

### 0.2 Paso 6 en Detalle: Persistencia de Contexto (Anti-Agotamiento)

```
PROBLEMA: Un LLM ejecutando tool calls agota su ventana de contexto.
Si el agente ejecuta 15 comandos bash en Fase 0-5, al llegar a
Fase 7 (Monitoreo) habrá "olvidado" los valores exactos del baseline.

SOLUCIÓN: El agente DEBE externalizar su memoria de trabajo a disco.

FORMATO DE /tmp/diag_[TAREA].md:

  # Diagnóstico: [Nombre de Tarea]
  ## Timestamp
  [YYYY-MM-DD HH:MM:SS]

  ## Baseline Pre-Intervención
  ### Tests
  - pytest: [output de pytest -q --tb=no]

  ### Datos (solo si aplica)
  | Tabla | COUNT | Stat Proxy | Duplicados |
  |---|---|---|---|
  | [tabla] | [número] | [sum_proxy] | [número] |

  ### Health
  - API: [curl output]
  - Systemd: [systemctl status output]

  ## Ciclos Detectados
  - [lista de ciclos estáticos y lógicos]

  ## Archivos Afectados
  - [lista con hashes git si es posible]

  ## Decisión Tomada
  - [qué se va a hacer y por qué]

  ## Rollback
  - git revert [hash]
  - [otros pasos]

REGLAS DE PERSISTENCIA:
1. ESCRIBIR /tmp/diag_*.md INMEDIATAMENTE después del último comando
   de la Fase 5 (no esperar a Fase 7).
2. En Fase 7, LEER el archivo ANTES de ejecutar cualquier verificación.
3. Comparar valor leído del archivo vs valor obtenido en Fase 7.
4. Si el agente no puede leer el archivo (fue borrado, etc.),
   PAUSAR y PEDIR al humano que proporcione el baseline.
5. Al finalizar la tarea exitosamente, el archivo puede eliminarse.
6. Si la tarea FALLA y se hace rollback, mantener el archivo para
   análisis post-mortem.
```

### 0.3 Matriz de Diagnóstico por Tipo de Enfermedad

| Enfermedad | Síntoma observable | Diagnóstico confirmatorio | Tratamiento | CONTRAINDICACIÓN |
|---|---|---|---|---|
| **Ciclo estático** | `ImportError` al importar | `python -c "from A import B; from B import A"` falla | Extraer interfaz para romper import | NO intentar `if TYPE_CHECKING` como workaround permanente |
| **Ciclo lógico (DI)** | No hay ImportError pero Container inyecta A→B→A | grep de Container muestra inyección mutua | Extraer interfaz + inyectar interfaz en un lado | NO asumir que "no hay ImportError = no hay ciclo" |
| **God File (cableado)** | 575 nodos, cohesión 0.01 | grep muestra que TODO importa este archivo | Facade con delegación gradual | NO eliminar sin que todos los consumidores usen la facade |
| **God Service (lógica)** | >1000 líneas, >5 tipos de salida | grep muestra múltiples `return` de tipos distintos | Extraer output adapters primero | NO extraer lógica sin diff de output textual |
| **Data Ghost** | 0 FKs, duplicados en schemas | COUNT en dos schemas muestra discrepancia | Consolidar con stat proxies antes/después | NO hacer string_agg en tabla >1GB |
| **ETL Drift** | 3 funciones copy-paste | Diff muestra solo cambia nombre de tabla | Parametrizar con config dataclass | NO refactorizar sin dry-run en tabla de prueba |
| **DOM Entropy** | Componente 1663 líneas, 0 tests | Cambio de 1 línea cambia el layout visual | Extraer con verificación visual | NO refactorizar UI sin verificación post-cambio |

### 0.4 Señales de ALTO

```
🚨 SEÑALES DE ALTO ABSOLUTAS:

CÓDIGO:
1. No puedo leer el archivo completo antes de editarlo
2. grep muestra >10 archivos importando lo que voy a modificar
3. El cambio afecta un servicio >1000 líneas
4. Voy a crear un archivo resultado >500 líneas
5. No hay tests para lo que voy a cambiar Y afecta infrastructure/

DATOS:
6. Voy a tocar infrastructure/database/ o etl/
7. No sé el tamaño de la tabla que afecta (pg_relation_size)
8. No hay FK entre la tabla que toco y sus dependientes
9. El ETL que modifico se ejecuta en Celery Beat
10. La tabla afectada es >1GB y no tengo stat proxy

OPERATIVO:
11. No hay commit reciente (<1 hora) y el cambio es >3 archivos
12. Multi-equipo (bot compartido)
13. El cambio afecta un .service de systemd

DOCUMENTAL:
14. Voy a crear un archivo .md
    → ¿Es realmente necesario? ¿Qué información aporta que no
      existe en ningún otro lado? ¿Sobrevivirá más de 1 semana?

Si se activa CUALQUIERA de las señales 6-10 → PAUSAR Y OBTENER:
  - SELECT pg_relation_size('tabla');  → saber el tamaño
  - Stat proxy si >1GB
  - Última ejecución del ETL si aplica
```

---

## SKILL 1: Investigación — Runtime-First, Graphify-Second

### 1.1 Árbol de Decisión

```
INICIO INVESTIGACIÓN
        │
        ▼
¿Necesito VERDAD o NAVEGACIÓN?
    │
    ├── VERDAD (voy a tomar una decisión de cambio)
    │   │
    │   ├── ¿Afecta datos (DB/ETL)?
    │   │   ├── SÍ → NIVEL 1: pg_relation_size primero
    │   │   │        → Si <1GB: COUNT + checksum MD5
    │   │   │        → Si >1GB: COUNT + stat proxy + TABLESAMPLE
    │   │   │        → NIVEL 2: grep del SQL/ETL
    │   │   │        → Graphify: SOLO para saber quién más la toca
    │   │   │
    │   │   └── NO → NIVEL 2: grep con contexto (-B5 -A5)
    │   │            → NIVEL 1: pytest del módulo
    │   │            → Graphify: NO NECESARIO
    │   │
    │   └── ¿Afecta código puro (lib, components, hooks)?
    │       ├── SÍ → NIVEL 2: py_compile / tsc --noEmit
    │       │        → NIVEL 1: pytest / npm run build
    │       │        → Graphify: NO NECESARIO
    │       │
    │       └── NO → ¿Afecta imports cross-module?
    │                ├── SÍ → Skill 1.3 (Ciclos) primero
    │                │        → Graphify query + grep verificación
    │                └── NO → grep directo
    │
    └── NAVEGACIÓN (entender el sistema, no cambiarlo)
        ├── Panorámica → GRAPH_REPORT.md
        ├── Dependencias → graphify query
        └── Rutas → graphify path
```

### 1.2 Protocolo de Verificación Cruzada (con pesos)

```
PESOS DE CONFIANZA:
┌───────────────────────────────────────┬────────┐
│ Fuente                                │ Peso  │
├───────────────────────────────────────┼────────┤
│ pytest PASA con el cambio             │ 0.40   │
│ pytest FALLA con el cambio            │ -0.40  │
│ grep confirma uso real                │ 0.30   │
│ import dir() confirma export real     │ 0.30   │
│ curl /health retorna 200              │ 0.25   │
│ COUNT coincide pre/post               │ 0.25   │
│ Stat proxy coincide pre/post (>1GB)   │ 0.25   │
│ graphify query (EXTRACTED)            │ 0.20   │
│ graphify query (INFERRED)             │ 0.08   │
│ graphify query (zona >50% INFERRED)   │ 0.03   │
│ "Parece que sí" sin verificación     │ 0.00   │
└───────────────────────────────────────┴────────┘

REGLA: Peso acumulado ≥ 0.7 para proceder sin aprobación adicional.
```

### 1.3 Detección de Ciclos de Dependencia (Estáticos Y Lógicos)

HAY DOS TIPOS DE CICLOS. DETECTAR AMBOS. SON ENFERMEDADES DIFERENTES
CON DIAGNÓSTICOS Y TRATAMIENTOS DIFERENTES.

═══ CICLO ESTÁTICO (Import Cycle) ═══

¿Qué es? El archivo A.py hace `from B import X` y B.py hace
`from A import Y`. Python falla inmediatamente con ImportError.

Detección:
  python3 -c "from domain.services.generation_service import GenerationService; \
             from domain.services.commercial_service import CommercialService; print('OK')"
  → Si falla con ImportError → CICLO ESTÁTICO CONFIRMADO

Tratamiento: Extraer la dependencia compartida a un tercer módulo
(o usar `if TYPE_CHECKING` solo si es estrictamente necesario
para type hints, nunca para lógica de runtime).

═══ CICLO LÓGICO (Dependency Injection Cycle) ═══

¿Qué es? A.py y B.py se importan correctamente (no hay ImportError).
PERO el Container inyecta B dentro de A, y A dentro de B.
El ciclo existe en el grafo de dependencias LÓGICAS, no en el
grafo de imports de Python. El código funciona, pero la arquitectura
está rota: no puedes extraer A o B a un archivo separado porque
el Container los amarra.

Detección (3 pasos):
  PASO 1: Verificar que NO hay ciclo estático
    python3 -c "from A import A; from B import B; print('No static cycle')"
    → Debe pasar OK

  PASO 2: Buscar inyección mutua en el Container
    grep -n "GenerationService" core/container.py
    grep -n "CommercialService" core/container.py
    → Si Container.creation_of_A() usa B, Y Container.creation_of_B() usa A
      → CICLO LÓGICO CONFIRMADO

  PASO 3: Verificar la dirección del acoplamiento (REGEX AMPLIO)
    NO asumir convenciones de nombres (self._servicio).
    Buscar cualquier mención del otro servicio que no sea comentario ni import:
    grep -in "commercial" domain/services/generation_service.py | grep -v "^\s*#" | grep -v "import"
    grep -in "generation" domain/services/commercial_service.py | grep -v "^\s*#" | grep -v "import"
    → Si GenerationService usa 1 método de CommercialService
      pero CommercialService usa 5 métodos de GenerationService
      → Romper el ciclo por el lado más débil (1 método = interfaz fácil)

Tratamiento: Dependency Inversion en el lado más débil del ciclo.

  PASO A: Crear interfaz minimal para el lado débil
    # domain/interfaces/iprecio_provider.py
    from abc import ABC, abstractmethod
    class IPrecioProvider(ABC):
        @abstractmethod
        def get_precio_bolsa(self, fecha: str) -> float: ...

  PASO B: Hacer que el servicio concreto implemente la interfaz
    # En commercial_service.py
    class CommercialService(IPrecioProvider): ...

  PASO C: Hacer que el otro servicio dependa de la interfaz
    # En generation_service.py
    class GenerationService:
        def __init__(self, precio_provider: IPrecioProvider, ...):
            self._precio = precio_provider  # NO es CommercialService

  PASO D: Actualizar Container para inyectar la implementación concreta
    # En container
    gen = GenerationService(precio_provider=commercial_instance, ...)

  PASO E: Verificar que el ciclo se rompió
    grep -n "GenerationService" core/container.py  # ya no usa CommercialService directamente en init
    python3 -c "from domain.services.generation_service import GenerationService; print('OK')"

═══ CHECKLIST ANTES DE EXTRAER MÓDULOS DEL CONTAINER ═══

Para cada par de servicios que voy a mover al mismo archivo nuevo:
  □ python -c: No hay ciclo estático
  □ grep container.py: No hay inyección mutua (ciclo lógico)
  □ Si hay ciclo lógico: Ya se aplicó Dependency Inversion
  □ Solo después de las 3 checks anteriores: proceder a extraer


---

## SKILL 2: Refactorización

### 2.1 Matriz de Riesgo No-Lineal

CÁLCULO DE PROBABILIDAD (factores se MULTIPLICAN entre sí):

⚠️ REGLA DE ORO ARITMÉTICA: LOS LLMs SON MALOS MULTIPLICANDO MÁS DE 3 FACTORES DE PUNTO FLOTANTE.
NUNCA intentes calcular este valor en tu memoria interna. Siempre delega la matemática
al sistema operativo usando el comando `bc`.

FACTORES A MULTIPLICAR (ejemplo de cómo construir el comando bash):
  Sin tests unitarios:        1.8
  Sin tests de integración:   2.0 (solo si afecta infrastructure/ o ETL)
  0 FKs en tablas afectadas:  2.0
  God file involucrado:       2.2
  God SERVICE involucrado:    2.5 (>1000 líneas)
  Ciclos de dependencia:      1.8
  Multi-equipo:               1.4
  ETL en Celery Beat:         3.0
  Tabla >1GB:                 1.5
  Producción activa:          1.3
  Código sin documentar:      1.4

EJECUCIÓN OBLIGATORIA POR EL AGENTE:
Ejemplo si aplica: Sin tests (1.8), 0 FKs (2.0), ETL Beat (3.0):
  bash: echo "1.8 * 2.0 * 3.0" | bc -l
  Output esperado del sistema: 10.8

LÍMITES (Evaluar contra el OUTPUT de `bc`, no contra tu suposición):
→ Si el output de bc es > 8.0 → ROJO ABSOLUTO → NO ejecutar sin plan escrito + aprobación.
→ Si el output de bc es > 15.0 → REQUIERE subdivisión en tareas ≤4 horas cada una.

### 2.2 Protocolo de Refactorización

FASE 0: DIAGNÓSTICO
├── 0.1 NIVEL 1: Baseline (tests, counts, health)
├── 0.2 NIVEL 2: grep dependencias con contexto
├── 0.3 NIVEL 3: Graphify para navegación
├── 0.4 Leer archivos afectados COMPLETOS
├── 0.5 DETECCIÓN DE CICLOS (estáticos Y lógicos — Skill 1.3)
├── 0.6 Calcular probabilidad usando `echo "X * Y * Z" | bc -l`
└── 0.7 PERSISTIR: Escribir /tmp/diag_[tarea].md con TODO lo anterior

FASE 0.5b: RUPTURA DE CICLOS (solo si 0.5 detectó ciclos)
├── Identificar tipo: estático vs lógico
├── Aplicar tratamiento correspondiente (Skill 1.3)
├── Verificar: python -c "import ..." + grep container.py
├── Commit: "refactor: break [static|logical] cycle between A and B"
├── PERSISTIR: Actualizar /tmp/diag_[tarea].md con resultado
└── Volver a 0.5 para re-verificar

FASE 1: PREPARACIÓN
├── 1.1 Git: commit + push "chore: pre-refactor snapshot"
├── 1.2 DATA: Si afecta DB/ETL → snapshot con método correcto (Skill 9)
├── 1.3 Crear: archivos nuevos (NO modificar existentes)
├── 1.4 Ningún archivo nuevo >500 líneas
└── 1.5 PERSISTIR: Actualizar /tmp/diag_[tarea].md

FASE 2: MIGRACIÓN INCREMENTAL
├── 2.1 Crear fachada/adapter que delega
├── 2.2 Migrar un consumidor
├── 2.3 Verificar NIVEL 1
├── 2.4 Si afecta datos: verificar con método correcto (Skill 9)
├── 2.5 Commit separado
└── 2.6 PERSISTIR: Actualizar /tmp/diag_[tarea].md

FASE 3: LIMPIEZA
├── 3.1 LEER /tmp/diag_[tarea].md para obtener baseline
├── 3.2 Verificar: tests pasan (comparar contra baseline del archivo)
├── 3.3 Verificar: datos coinciden (comparar contra baseline del archivo)
├── 3.4 Eliminar código viejo
├── 3.5 Verificar de nuevo
├── 3.6 Commit final
└── 3.7 Limpiar /tmp/diag_[tarea].md (éxito) o conservar (fallo)

### 2.3 Patrón R1: Extracción de Container (con ciclos lógicos)

# ANTES de extraer, ejecutar Skill 1.3 completo.
# Si hay ciclos lógicos, aplicar Dependency Inversion primero.
# El código de abajo asume que los ciclos ya fueron rotos.

# container/services_energy.py
class EnergyServiceFactory:
    def __init__(self, repos, external_services):
        self._repos = repos
        self._external = external_services

    def create_generation(self) -> GenerationService:
        # GenerationService ya depende de IPrecioProvider (interfaz),
        # no de CommercialService directamente. Ciclo roto.
        commercial = self.create_commercial()
        return GenerationService(
            precio_provider=commercial,
            repo=self._repos.metrics_repo,
        )

    def create_commercial(self) -> CommercialService:
        return CommercialService(
            repo=self._repos.commercial_repo,
        )

# container/__init__.py
class ContainerFacade:
    def __init__(self):
        self._energy = EnergyServiceFactory(repos, external)

    @property
    def generation_service(self):
        return self._energy.create_generation()

    @property
    def commercial_service(self):
        return self._energy.create_commercial()

### 2.4 Patrón R2.5: Refactorización de God Services (con PDF textual diff)

REGLA: Un servicio >1000 líneas es tan peligroso como un god file.
PROHIBIDO: Refactorizar lógica de negocio sin diff de output textual.

PROTOCOLO PARA GOD SERVICES (ejemplo: report_service.py — 1.850 líneas):

PASO 0: DIAGNÓSTICO DEL OUTPUT
├── grep -n "return " domain/services/report_service.py | head -30
├── Clasificar tipos de salida: dict / PDF / JSON / DataFrame
├── Identificar output CANÓNICO (el que no puede romperse)
└── ¿Hay test de integración que valide output? → Sino: PROHIBIDO tocar lógica

PASO 1: EXTRAER FORMATEADORES (sin riesgo)
├── Extraer a domain/utils/formatting.py
├── Reemplazar en report_service.py con imports
└── Verificar con diff textual (ver abajo)

PASO 2: EXTRAER DATA ADAPTERS (bajo riesgo)
├── Extraer consultas a repositorio
├── Reemplazar en report_service.py
└── Verificar con diff textual

PASO 3: EXTRAER OUTPUT ADAPTERS (medio riesgo)
├── Extraer lógica de generación de PDF/JSON
├── report_service.py → orquestador puro
└── Verificar con diff textual

PASO 4: DIVIDIR LÓGICA (ALTO riesgo — solo con tests de integración)
├── Extraer sub-informes con tests de output
└── Verificar con diff textual

VERIFICACIÓN DE OUTPUT (CORREGIDA — diff textual, NO binario):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROHIBIDO: diff baseline.pdf refactor.pdf
RAZÓN: Los generadores de PDF inyectan metadatos no deterministas
(IDs de objeto, timestamps, font hinting). Un diff binario casi
siempre fallará, generando falsos positivos de regresión y
entrando el agente en bucle de pánico.

CORRECTO: Extraer texto del PDF antes de diffear.

  # Generar baseline ANTES del refactor
  pdftotext baseline.pdf /tmp/baseline_text.txt

  # ... hacer el refactor ...

  # Generar refactor
  pdftotext refactor.pdf /tmp/refactor_text.txt

  # Diff textual (no binario)
  diff /tmp/baseline_text.txt /tmp/refactor_text.txt

  # Si hay diferencias, inspeccionar si son significativas:
  diff -u /tmp/baseline_text.txt /tmp/refactor_text.txt | head -50

  # También verificar estructura (número de páginas, etc.):
  python3 -c "
  import fitz  # PyMuPDF
  b = fitz.open('baseline.pdf')
  r = fitz.open('refactor.pdf')
  print(f'Páginas: baseline={len(b)}, refactor={len(r)}')
  assert len(b) == len(r), 'Diferencia en número de páginas'
  "

NOTA: Si pdftotext no está instalado:
  sudo apt-get install poppler-utils

ALTERNATIVA si no hay pdftotext ni PyMuPDF:
  # Extraer texto con strings + filtrar (menos preciso pero funcional)
  strings baseline.pdf | grep -v "^$" | sort > /tmp/baseline_strings.txt
  strings refactor.pdf | grep -v "^$" | sort > /tmp/refactor_strings.txt
  diff /tmp/baseline_strings.txt /tmp/refactor_strings.txt

---

## SKILL 3: Estimación No-Lineal

ESFUERZO_REAL = ESFUERZO_NOMINAL × ∏(FACTORES) + VERIFICACIÓN + ENTROPÍA

⚠️ RECORDATORIO: Calcular el producto de los FACTORES usando `echo "..." | bc -l`.
No sumar los factores. No calcularlos mentalmente.

FACTORES (se MULTIPLICAN en bash):
├── Sin tests unitarios:        ×1.8
├── Sin tests de integración:   ×2.0
├── 0 FKs en tablas afectadas:  ×2.0
├── God file:                   ×2.2
├── God SERVICE (>1000 líneas): ×2.5
├── Ciclos (estáticos o lógicos): ×1.8
├── Multi-equipo:               ×1.4
├── ETL en Celery Beat:         ×3.0
├── Tabla >1GB:                 ×1.5
├── Producción activa:          ×1.3
└── Sin documentar:             ×1.4

VERIFICACIÓN (se SUMA al resultado de bc):
├── Código <3 archivos:   15 min
├── Código 3-10 archivos:  30 min
├── Código >10 archivos:   1 hora
├── DB (tabla <1GB):      45 min (checksums completos)
├── DB (tabla >1GB):      1.5 horas (stat proxies + ANALYZE gating)
├── ETL:                  1 hora (dry-run + comparación)
└── UI:                   30 min (verificación visual)

ENTROPÍA (se SUMA al resultado final):
├── Archivo resultado >500 líneas: +2 horas (dividir más)
├── Archivo resultado >300 líneas: +30 min
├── Componente con Nivo:          +1 hora
├── Componente con Leaflet:       +1 hora
├── Layout responsive:            +1.5 horas
├── Tabla sin FK + repo change:   +1 hora
├── ETL sin idempotencia:         +2 horas
└── Cambio .service:              +30 min

LÍMITE: Si el total > 8 horas → plan escrito + aprobación. >16 horas → subdividir.

---

## SKILL 4: Comunicación

### 4.1 Formato de Reporte de Estado (con datos)

```markdown
## Estado: [Nombre]

### Código
- Archivos: X modificados, +Y/-Z líneas
- Tests: [baseline] → [post] (sin regresión)

### Datos (si aplicó)
| Tabla | Tamaño | Método | Pre | Post | Match |
|---|---|---|---|---|---|
| [t] | [<1GB/>1GB] | [checksum/proxy] | [val] | [val] | ✅/❌ |

### Verificación de output (si aplicó — PDF/dict)
- Método: pdftotext diff / dict comparison
- Resultado: 0 diferencias textuales ✅
```

### 4.2 Formato de Petición de Aprobación

```markdown
## 🚨 Aprobación: [Acción]

### Qué
[Descripción]

### Riesgo calculado (vía `bc`)
P = echo "[factores]" | bc -l = [resultado real] → [NIVEL]

### Mitigaciones
| Riesgo | Mitigación |
|---|---|
| [R] | [M] |

### Rollback
[pasos]

### Archivo de diagnóstico
/tmp/diag_[tarea].md — contiene baseline completo
```

### 4.3 Formato de Problema

```markdown
## 🐛 Problema: [Título]

### Ubicación
`archivo:línea`

### Evidencia (Nivel 1)
```bash
[comando + output]
```

### Hipótesis
[nivel de confianza 0.0-1.0]: [qué creo que pasa]

### Fix propuesto
```[lang]
[código]
```

### ¿Procedo?
```

---

## SKILL 5: Incertidumbre

```
NIVEL          PESO      ACCIÓN
≥0.8 VERIF.    2+ N1/N2  EJECUTAR
0.5-0.79 PROB. 1 N1/N2   EJECUTAR + VERIFY EXTRA
0.3-0.49 PLAU. solo N3/4 INVESTIGAR
0.1-0.29 HIP.  ninguno   NO TOCAR, documentar
<0.1 IGNOR.    ninguno   PEDIR CONTEXTO
```

---

## SKILL 6: Meta-Habilidades

### 6.1 Detección de Modo Equivocado

```
Si leo graph.json directamente (no report ni query) → Usar tools correctas
Si grep da 0 pero Graphify dice que hay conexión → Graphify mintiendo (INFERRED)
Si toco código sin COUNT/checksum de tabla → Cirugía sin radiografía
Si creo archivo >500 líneas → No estoy dividiendo suficiente
Si mi cálculo mental de riesgo difiere de lo que daría `bc` → USAR BC
Si no leí /tmp/diag_*.md antes de verificar → Comparando contra nada
Si voy a crear un .md → ¿Paso el test de necesidad? (Skill 11)
```

---

## SKILL 7: Checklist de Calidad

```
TÉCNICO (Nivel 1):
□ pytest pasa (mismo baseline)
□ curl health checks OK

DATOS (si tocó DB/ETL):
□ COUNT coincide con baseline (de /tmp/diag_*.md)
□ Método correcto usado para tamaño de tabla (<1GB: checksum, >1GB: proxy)
□ Si Método D usado: Se ejecutó ANALYZE (con permiso) antes de comparar post
□ No duplicados nuevos (COUNT - COUNT DISTINCT = 0)
□ Si ETL: idempotencia verificada (2 ejecuciones = mismo resultado)

CICLOS (si extrajo módulos):
□ No ciclos estáticos (python -c verifica)
□ No ciclos lógicos (grep amplio sin convenciones estrictas verifica)

ARTEFACTO:
□ Ningún archivo nuevo >500 líneas
□ Nombres descriptivos en dominio del negocio

COMPATIBILIDAD:
□ Firmas públicas intactas
□ Imports migrados completamente

DOCUMENTAL (Skill 11):
□ No se crearon .md innecesarios
□ .md existentes actualizados si el cambio es arquitectónico
□ .md obsoletos eliminados
```


---

## SKILL 8: Reglas Absolutas

```
PROHIBIDO:
├── 1. Modificar core/container.py directamente
├── 2. Agregar lógica a god services/components (>1000 líneas)
├── 3. Refactorizar lógica de servicio >1000 líneas sin diff textual de output
├── 4. SQL dinámico sin sql_validator.py
├── 5. Exponer secrets en variables de entorno públicas
├── 6. Eliminar archivos sin grep -r + git log
├── 7. Cambiar schema DB sin pg_dump previo
├── 8. Tocar .service sin systemctl status + cp backup
├── 9. Tocar ETL en Celery Beat sin tabla de prueba
├── 10. Crear archivo resultado >500 líneas
├── 11. string_agg en tabla >1GB (usar stat proxy o TABLESAMPLE)
├── 12. diff binario de PDF (usar pdftotext diff)
├── 13. Crear .md sin pasar el test de necesidad (Skill 11)
├── 14. Confiar en memoria de contexto para baseline (usar /tmp/diag_*.md)
├── 15. Ejecutar ANALYZE en tabla >10GB automáticamente sin permiso humano
└── 16. Calcular multiplicatorios de riesgo en la "cabeza" del LLM (usar `bc`)

CONDICIONADO:
├── Extraer del container → Solo si Skill 1.3 confirma 0 ciclos (estáticos Y lógicos)
├── Modificar repositorio → Solo si tengo snapshot de datos con método correcto
├── Cambiar formateo en god service → Solo con pdftotext diff = 0 diferencias
├── Consolidar ETL → Solo con dry-run en tabla de prueba + comparación de counts
└── Verificar stat proxy post-cambio → Si tabla >10GB, pedir permiso para ANALYZE
```

### 8.1 God Services (lista de vigilancia)

| Servicio | Líneas | Output Canónico | Restricción Especial |
|---|---|---|---|
| report_service.py | 1.850 | PDF | pdftotext diff obligatorio |
| executive_report_service.py | 1.618 | PDF ejecutivo | pdftotext diff obligatorio |
| cu_service.py | 1.010 | Datos XM | Mock de XM obligatorio |
| losses_nt_service.py | 1.199 | Cálculos regulatorios | Validación contra cálculo manual |
| simulation_service.py | 748 | Monte Carlo | Seed fijo en tests |
| predictions_service_extended.py | 698 | ML | Fixture de modelo |

---

## SKILL 9: Data State Verification (con física de hardware)

### 9.1 Protocolo de Snapshot — Método por Tamaño de Tabla

PASO 0: SIEMPRE — Obtener el tamaño de la tabla ANTES de elegir método

SELECT pg_size_pretty(pg_relation_size('nombre_tabla')) AS size,
       pg_relation_size('nombre_tabla') AS size_bytes
FROM (
  SELECT 'nombre_tabla' AS nombre_tabla
) t;

RESULTADO DETERMINA EL MÉTODO:
├── < 100 MB  → MÉTODO A: Checksum completo (máxima confianza)
├── 100MB-1GB → MÉTODO B: Checksum completo con precaución (puede tardar 10-30s)
├── 1GB-10GB  → MÉTODO C: Stat proxy + muestreo (NO usar string_agg)
└── > 10GB    → MÉTODO D: Stat proxy exclusivo (PROHIBIDO string_agg)

═══ MÉTODO A: Checksum Completo (< 100MB) ═══

SELECT COUNT(*) AS pre_count FROM tabla;

SELECT md5(string_agg(t::text, '' ORDER BY id)) AS pre_checksum
FROM tabla AS t;

SELECT COUNT(*) - COUNT(DISTINCT (col1, col2)) AS pre_dups FROM tabla;

═══ MÉTODO B: Checksum Completo con Precaución (100MB - 1GB) ═══

(Mismas queries que Método A, pero:
 - Avisar al usuario que puede tardar 10-30 segundos
 - Verificar que no hay otras queries pesadas corriendo:
   SELECT pid, query, state FROM pg_stat_activity WHERE state != 'idle';
 - Si hay >3 queries activas, esperar a que terminen)

═══ MÉTODO C: Stat Proxy + Muestreo (1GB - 10GB) ═══

-- PROXY 1: Conteo rápido (usa estadísticas del planner, NO escanea la tabla)
SELECT reltuples::bigint AS estimated_count
FROM pg_class WHERE relname = 'nombre_tabla';

-- PROXY 2: Suma proxy (usa pg_stats, NO lee la tabla)
SELECT
  SUM(n_distinct) AS proxy_distinct_values,
  SUM(null_frac) AS proxy_null_fraction
FROM pg_stats
WHERE tablename = 'nombre_tabla'
AND attname IN ('valor', 'fecha', 'metrica');

-- PROXY 3: Muestreo determinista (SINTAXIS POSTGRES NATIVA SEGURA)
-- NOTA: TABLESAMPLE debe ir inmediatamente después del nombre de la tabla.
-- El filtro WHERE se aplica DESPUÉS sobre las filas muestreadas.
SELECT md5(string_agg(t::text, '' ORDER BY id)) AS sample_checksum
FROM nombre_tabla TABLESAMPLE SYSTEM(1.0) AS t
WHERE t.fecha >= CURRENT_DATE - INTERVAL '30 days';

-- NOTA: El sample_checksum NO es comparable contra un checksum completo.
-- Solo es comparable contra OTRO sample_checksum con mismos parámetros.
-- Guardar SIEMPRE los parámetros de sampling en /tmp/diag_*.md.

-- PROXY 4: Min/Max de fecha (verificar que el rango temporal no cambió)
SELECT MIN(fecha) AS min_fecha, MAX(fecha) AS max_fecha
FROM nombre_tabla;

═══ MÉTODO D: Stat Proxy Exclusivo (> 10GB) ═══

-- PROHIBIDO: string_agg, TABLESAMPLE, COUNT(*) exacto
-- (COUNT(*) en 64M filas puede tomar 30-60 segundos y bloquear)

-- ÚNICO: Usar pg_stats (estadísticas del planner)
SELECT
  attname,
  n_distinct,
  null_frac,
  avg_width,
  correlation
FROM pg_stats
WHERE tablename = 'nombre_tabla'
ORDER BY attname;

-- Y rango temporal (query indexada, rápida si hay índice en fecha)
SELECT MIN(fecha) AS min_fecha, MAX(fecha) AS max_fecha
FROM nombre_tabla;

-- GUARDAR TODO en /tmp/diag_*.md para comparación post-cambio.

═══ VERIFICACIÓN POST-CAMBIO ═══

USAR EL MISMO MÉTODO que en el snapshot pre-cambio.

⚠️ TRAMPA DE AUTOVACUUM Y RIESGO OPERATIVO (APLICA A MÉTODOS C Y D):
pg_stats NO es tiempo real. Se actualiza tras un ANALYZE.
Si el cambio fue masivo, pg_stats seguirá mostrando el estado PREVIO.

REGLA DE EJECUCIÓN SEGÚN TAMAÑO:
→ Si tabla es < 10GB: Ejecutar `ANALYZE nombre_tabla;` automáticamente antes de leer pg_stats.
→ Si tabla es > 10GB: PROHIBIDO ejecutar ANALYZE automáticamente.
   PAUSAR y PEDIR al humano:
   "El cambio masivo requiere actualizar estadísticas (ANALYZE) en una tabla >10GB,
   lo cual puede causar un pico de CPU de 5-15s. ¿Ejecuto ANALYZE o prefiero verificar
   usando COUNT(*) indexado como alternativa?"

Leer /tmp/diag_*.md para obtener valores pre-cambio.
Comparar contra valores post-cambio.

Si hay discrepancia Y el método fue C o D:
  → No entrar en pánico. Los stat proxies tienen margen de error.
  → Investigar solo si la discrepancia es >10% en n_distinct o >5% en null_frac.
  → Confirmar con COUNT(*) si la tabla tiene índice en la columna relevante.

### 9.2 Protocolo para ETLs

1. IDENTIFICAR si corre en Celery Beat:
   grep -r "nombre_etl" /home/admonctrlxm/server/tasks/
   → Si aparece: RIESGO MÁXIMO

2. EJECUTAR EN TABLA DE PRUEBA:
   CREATE TABLE test_tabla AS SELECT * FROM tabla_real WITH NO DATA;
   [ejecutar ETL apuntando a test_tabla]

3. COMPARAR (con método correcto para tamaño):
   [Método A/B/C/D según pg_relation_size de test_tabla]

4. IDEMPOTENCIA:
   [Ejecutar ETL de nuevo sobre test_tabla]
   [Mismo resultado = idempotente]

5. RANGOS:
   SELECT MIN(valor), MAX(valor), AVG(valor) FROM test_tabla;
   [Comparar contra original — diff >5% en AVG → investigar]

6. LIMPIAR:
   DROP TABLE test_tabla;

7. APLICAR + MONITOREAR:
   [Ejecutar ETL real]
   [Esperar 5 min]
   [Si tabla >10GB: Solicitar permiso para ANALYZE o usar COUNT]
   [Verificar con método correcto]
   [Verificar logs: grep -i "error\|exception" logs/etl.log | tail -20]

### 9.3 Comandos de Data Verification

```bash
# Obtener tamaño de tabla (SIEMPRE primero)
get_table_size() {
  psql -d portal_energetico -c "
    SELECT pg_size_pretty(pg_relation_size('$1')) AS size,
           pg_relation_size('$1') AS bytes
    FROM (SELECT '$1' AS t) x;
  "
}

# Snapshot automático con método correcto
snapshot_tabla() {
  local tabla=$1
  local archivo="/tmp/snapshot_${tabla}_$(date +%Y%m%d_%H%M%S).md"
  # PARCH FÍSICO: tr -d '[:space:]' previene "integer expression expected" en bash
  local bytes=$(psql -d portal_energetico -t -A -c "SELECT pg_relation_size('$tabla')" | tr -d '[:space:]')

  echo "# Snapshot: $tabla" > "$archivo"
  echo "## Timestamp: $(date)" >> "$archivo"
  echo "## Size bytes: $bytes" >> "$archivo"

  if [ "$bytes" -lt 100000000 ]; then
    echo "## Method: A (full checksum)" >> "$archivo"
    psql -d portal_energetico -c "SELECT COUNT(*) AS count FROM $tabla;" >> "$archivo"
    psql -d portal_energetico -c "SELECT md5(string_agg(t::text, '' ORDER BY id)) AS checksum FROM $tabla AS t;" >> "$archivo"
  elif [ "$bytes" -lt 1000000000 ]; then
    echo "## Method: B (full checksum, slow)" >> "$archivo"
    psql -d portal_energetico -c "SELECT COUNT(*) AS count FROM $tabla;" >> "$archivo"
    psql -d portal_energetico -c "SELECT md5(string_agg(t::text, '' ORDER BY id)) AS checksum FROM $tabla AS t;" >> "$archivo"
  elif [ "$bytes" -lt 10000000000 ]; then
    echo "## Method: C (stat proxy + sampling)" >> "$archivo"
    psql -d portal_energetico -c "SELECT reltuples::bigint AS estimated_count FROM pg_class WHERE relname='$tabla';" >> "$archivo"
    psql -d portal_energetico -c "SELECT attname, n_distinct, null_frac, avg_width FROM pg_stats WHERE tablename='$tabla' ORDER BY attname;" >> "$archivo"
    # PARCH FÍSICO: Sintaxis Postgres nativa para TABLESAMPLE sin CTEs inválidas
    psql -d portal_energetico -c "SELECT md5(string_agg(t::text, '' ORDER BY id)) AS sample_checksum FROM $tabla TABLESAMPLE SYSTEM(1.0) AS t WHERE t.fecha >= CURRENT_DATE - INTERVAL '30 days';" >> "$archivo"
  else
    echo "## Method: D (stat proxy only)" >> "$archivo"
    psql -d portal_energetico -c "SELECT attname, n_distinct, null_frac, avg_width, correlation FROM pg_stats WHERE tablename='$tabla' ORDER BY attname;" >> "$archivo"
  fi

  echo "Guardado en: $archivo"
}

# Detección de duplicados
check_dups() {
  local tabla=$1
  local cols=$2
  psql -d portal_energetico -c "SELECT COUNT(*) - COUNT(DISTINCT ($cols)) AS dups FROM $tabla;"
}

# Detección de orphans (emulación de FK)
check_orphans() {
  local hija=$1
  local padre=$2
  local col_hija=$3
  local col_padre=$4
  psql -d portal_energetico -c "
    SELECT COUNT(*) AS orphans
    FROM $hija h
    WHERE $col_hija IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM $padre p WHERE p.$col_padre = h.$col_hija);
  "
}
```

---

## SKILL 10: Comandos de Referencia

```bash
# ═══ NIVEL 1: RUNTIME ═══

# Tests
cd /home/admonctrlxm/server && pytest tests/ -q --tb=no
cd /home/admonctrlxm/portal-direccion-mme && npm run build 2>&1 | tail -5

# Health
curl -s http://localhost:8000/health | head -1
curl -s http://localhost:3000/ | head -1

# Datos — tamaño primero
psql -d portal_energetico -c "SELECT pg_size_pretty(pg_relation_size('tabla')) FROM (SELECT 'tabla') t;"

# Datos — método según tamaño (usar snapshot_tabla)

# Servicios
pm2 status --no-color
systemctl status api-mme --no-pager | grep "Active"

# Logs
pm2 logs api-mme --lines 30 --nostream

# ═══ NIVEL 2: AST ═══

# Imports reales
grep -rn "from domain.services.X import" /home/admonctrlxm/server/ --include="*.py"

# Verificar import sin error circular
python3 -c "from domain.services.X import X; print('OK')"

# Sintaxis
python3 -m py_compile archivo.py

# ═══ NIVEL 3: INFERENCIA ═══

cat /home/admonctrlxm/server/graphify-out/GRAPH_REPORT.md | head -80

/home/admonctrlxm/.graphify-venv/bin/graphify query "dependencias de X" \
  --graph /home/admonctrlxm/server/graphify-out/graph.json --budget 3000

# ═══ CICLOS (Skill 1.3) ═══

# Estático
python3 -c "from A import A; from B import B; print('No static cycle')"

# Lógico — buscar inyección mutua en container
grep -n "ServiceA" core/container.py | grep -i "def\|self\.\|return"
grep -n "ServiceB" core/container.py | grep -i "def\|self\.\|return"

# ═══ PERSISTENCIA ═══

# Escribir diagnóstico
cat > /tmp/diag_[tarea].md << 'EOF'
[contenido del diagnóstico]
EOF

# Leer diagnóstico (en Fase 3)
cat /tmp/diag_[tarea].md

# ═══ BACKUP ═══

git add -A && git commit -m "chore: pre-refactor snapshot" && git push

sudo cp /etc/systemd/system/nombre.service /tmp/nombre.service.bak

pg_dump -d portal_energetico --schema-only > /tmp/schema_$(date +%Y%m%d).sql

# ═══ PDF DIFF (NO binario) ═══

pdftotext baseline.pdf /tmp/baseline.txt
pdftotext refactor.pdf /tmp/refactor.txt
diff /tmp/baseline.txt /tmp/refactor.txt
```

---

## SKILL 11: Higiene Documental (Anti-Garbage .md)

### 11.1 El Problema

```
Los agentes de IA tienden a crear archivos .md como mecanismo de descarga
cognitiva: cada sesión, cada investigación, cada hallazgo genera un .md.
Resultado: acumulación de archivos que:
- No dan información relevante del estado actual del proyecto
- Se vuelven obsoletos rápidamente
- Contienen información duplicada entre sí
- Generan ruido que dificulta encontrar documentación REAL
- Ocupan espacio en el repo y en la mente del desarrollador

ESTO ES BASURA DOCUMENTAL. DEBE DETENERSE.
```

### 11.2 Test de Necesidad de Creación de .md

```
ANTES de crear CUALQUIER archivo .md, el agente DEBE pasar este test:

PREGUNTA 1: ¿Existe ya un archivo que contenga esta información?
├── SÍ → NO crear. Actualizar el existente.
└── NO → Ir a Pregunta 2

PREGUNTA 2: ¿Esta información será relevante dentro de 1 semana?
├── NO → NO crear. Es basura temporal. Usar /tmp/ si necesitas persistir
│         durante la sesión actual (/tmp se limpia solo).
└── SÍ → Ir a Pregunta 3

PREGUNTA 3: ¿Esta información es del estado ACTUAL del proyecto?
├── NO (es histórico, análisis, opinión) → NO crear como .md permanente.
│   Usar commit messages o /tmp/.
└── SÍ → Ir a Pregunta 4

PREGUNTA 4: ¿Un desarrollador que no fue parte de esta sesión la necesitaría
           para hacer su trabajo?
├── NO → NO crear. Es contexto de sesión, no documentación de proyecto.
└── SÍ → Ir a Pregunta 5

PREGUNTA 5: ¿Qué categoría es?
├── ESTADO ACTUAL del proyecto → Crear/actualizar en ubicación canónica
├── PROCEDIMIENTO que otros deben seguir → Crear en docs/ o AGENTS.md
├── ARQUITECTURA o diseño → Crear/actualizar en docs/
├── PROPUESTA o plan futuro → Crear en docs/ con fecha de vencimiento
└── Otra cosa → NO crear. Es basura.

SI NO PASA LAS 5 PREGUNTAS → NO CREAR EL ARCHIVO.
SI PASA → Crear en la ubicación correcta (ver 11.3).
```

### 11.3 Ubicación Canónica de Documentación (NO inventar rutas)

```
/home/admonctrlxm/server/
├── README.md                    # Estado actual del backend (qué es, cómo levantarlo, stack)
├── AGENTS.md                    # Reglas para agentes (se actualiza con cada cambio arquitectónico)
├── SKILL_PACK_V4.1.md          # Este framework (NO editar a menos que sea actualización global)
├── docs/
│   ├── ARCHITECTURE.md          # Arquitectura actual (diagramas, capas, decisiones)
│   ├── API_CONTRACTS.md         # Contratos de API entre frontend y backend
│   ├── PROCEDURES.md            # Procedimientos operativos (deploy, backup, ETL manual)
│   └── ADRs/                    # Architecture Decision Records (una por decisión significativa)
│       ├── 001-extraccion-container.md
│       └── 002-consolidacion-etl.md
└── [NO otros .md fuera de estas ubicaciones]

/home/admonctrlxm/portal-direccion-mme/
├── README.md                    # Estado actual del frontend
├── AGENTS.md                    # Reglas para agentes
├── SKILL_PACK_V4.1.md          # Este framework (referencia compartida)
└── [NO otros .md fuera de estas ubicaciones]

/home/admonctrlxm/documentacion-tecnica/
├── PROPUESTA_MAESTRA.md         # Estado actual completo + roadmap (documento vivo)
├── SKILL_PACK_CLAUDE.md         # Este archivo
├── SKILL_PACK_KIMI.md           # Skill pack específico para Kimi
└── graph-global.json            # Grafo (dato, no documentación)

/tmp/                            # BASURA TEMPORAL (se limpia solo)
├── diag_[tarea].md              # Contexto de sesión (persistir por duración de la tarea)
├── snapshot_[tabla]_*.md        # Data snapshots (persistir por duración de la tarea)
└── [cualquier cosa temporal]     # NO va al repo
```

### 11.4 Reglas de Mantenimiento Documental

```
AL INICIO DE CADA SESIÓN DE TRABAJO:

1. ESCANEAR basura documental:
   find /home/admonctrlxm/server -name "*.md" -newer /home/admonctrlxm/server/AGENTS.md \
     ! -path "*/docs/*" ! -name "README.md" ! -name "AGENTS.md" ! -name "SKILL_PACK_V4.1.md"
   → Cualquier .md fuera de docs/ que no sea README, AGENTS ni SKILL_PACK es sospechoso
   → Leerlo. Si es basura: eliminar.
   → Si es relevante: mover a docs/ y actualizar.

2. VERIFICAR obsolescencia:
   Para cada .md en docs/:
   ├── ¿Menciona tecnologías que ya no se usan? → Actualizar o eliminar
   ├── ¿Tiene fecha y ya pasó? → Evaluar si el contenido sigue vigente
   ├── ¿Contiene datos que cambiaron (nombres de archivos, rutas)? → Actualizar
   └── ¿Se duplica con otro .md? → Consolidar en uno

AL FINAL DE CADA SESIÓN DE TRABAJO:

3. LIMPIAR /tmp/:
   rm -f /tmp/diag_*.md /tmp/snapshot_*.md /tmp/baseline_*.txt /tmp/refactor_*.txt
   → Solo conservar si la tarea falló y se necesita post-mortem

4. ACTUALIZAR si hubo cambio arquitectónico:
   ├── AGENTS.md del proyecto afectado
   ├── docs/ARCHITECTURE.md si cambió la estructura
   ├── PROPUESTA_MAESTRA.md si cambió el estado actual
   └── Commit con mensaje: "docs: update [qué] after [qué cambio]"

DURANTE CADA SESIÓN:

5. NUNCA crear .md como "notas" o "apuntes".
   Si necesitas tomar notas durante una investigación:
   → Usa comentarios en el código
   → Usa commit messages descriptivos
   → Usa /tmp/ si necesitas persistir durante la sesión
   → NO crees un .md

6. NUNCA crear .md de "hallazgos" o "análisis".
   Los hallazgos van a:
   → Commit messages (si son bugs o fixes)
   → AGENTS.md (si son reglas que otros deben seguir)
   → PROPUESTA_MAESTRA.md (si cambian el estado del proyecto)
   → NUNCA a un .md separado llamado "hallazgos_2026-05-01.md"
```

### 11.5 Formato de .md Canónico (si debes crear uno)

```markdown
# [Título Descriptivo]

> Última actualización: YYYY-MM-DD
> Responsable: [agente/humano]
> Caducidad: [fecha o "permanente" o "hasta que [condición]"]
> Relacionado: [enlaces a otros .md relevantes]

## Propósito
[UNA frase que explique por qué este archivo existe.
 Si no puedes escribir esta frase, el archivo no debería existir.]

## Contenido
[El contenido real]

## Cuándo actualizar
[Condiciones específicas que requieren actualizar este archivo.
 Ej: "Actualizar cuando se agregue un nuevo servicio a domain/services/"
 Ej: "Eliminar cuando la Fase 3 del roadmap se complete"]
```

### 11.6 Señales de Basura Documental (eliminar inmediatamente)

```
ELIMINAR SIN LEER COMPLETO si el archivo:
├── Se llama "notas_*.md", "apuntes_*.md", "hallazgos_*.md", "investigación_*.md"
├── Se llama "temp_*.md", "tmp_*.md", "draft_*.md" y está fuera de /tmp/
├── Tiene fecha en el nombre (ej: "2026-05-01_session.md")
├── No tiene sección de "Propósito" o "Última actualización"
├── Fue creado hace >2 semanas y no se ha modificado desde
├── Contiene principalmente output de comandos (grep, graphify, etc.)
├── Se duplica con otro archivo (diff muestra >80% similitud)
├── Menciona archivos o rutas que ya no existen
└── Un humano nunca lo ha leído (no hay git blame con correo humano)

LEER Y EVALUAR si:
├── Está en docs/ pero no tiene fecha de actualización
├── Está en docs/ pero el contenido parece desactualizado
└── Contiene información relevante pero mal organizada → Reestructurar, no eliminar
```

---

## ANEXO A: Plantilla de Plan de Refactorización

```markdown
# Plan: [Nombre]

## Metadatos
- **Fecha**: YYYY-MM-DD
- **Riesgo**: P = echo "[factores]" | bc -l = [resultado real del sistema] → [NIVEL]
- **Confianza**: [0.0-1.0] — Fuentes: [lista con pesos]
- **Esfuerzo**: [Xh] = nominal × riesgo (vía bc) + verificación [Xh] + entropía [Xh]
- **Aprobación**: [SÍ/NO]
- **Archivo diagnóstico**: /tmp/diag_[tarea].md

## Diagnóstico
### Enfermedad
[Ciclo estático / Ciclo lógico / God Service / Data Ghost / ETL Drift / DOM Entropy]

### Evidencia (Nivel 1)
```bash
[output real]
```

### Ciclos (si aplica)
| Tipo | Servicios | Dirección | Método de ruptura |
|---|---|---|---|
| [Estático/Lógico] | [A, B] | [A→B→A] | [Interfaz: IXxxProvider] |

## Tablas Afectadas
| Tabla | Size | Método | Valores Pre |
|---|---|---|---|
| [t] | [pretty/bytes] | [A/B/C/D] | [de /tmp/diag_*.md] |

## Pasos

### Fase 0: Diagnóstico
- [ ] Baseline ejecutado
- [ ] Ciclos detectados (estáticos + lógicos)
- [ ] Riesgo calculado (output de `bc` guardado)
- [ ] /tmp/diag_[tarea].md escrito

### Fase 0.5b: Ciclos (si aplica)
- [ ] Interfaz creada
- [ ] Servicio modificado
- [ ] Verificado: python -c + grep container.py
- [ ] Commit: [hash]
- [ ] /tmp/diag_*.md actualizado

### Fase 1: Preparación
- [ ] Git snapshot: [hash]
- [ ] Data snapshot: [método usado]
- [ ] Archivos nuevos: [lista, ninguno >500 líneas]

### Fase 2: Migración
- [ ] Consumidor 1 migrado → verificado → commit
- [ ] Consumidor 2 migrado → verificado → commit
- [ ] ...

### Fase 3: Limpieza
- [ ] LEER /tmp/diag_*.md para obtener baseline
- [ ] Tests pasan (vs baseline): SÍ/NO
- [ ] Datos coinciden (vs baseline): SÍ/NO
- [ ] Código viejo eliminado
- [ ] /tmp/diag_*.md limpiado (éxito) o conservado (fallo)

## Verificación Final
```bash
[comandos]
```

## Rollback
1. git revert [hash]
2. [otros pasos]
```

---

*Skill Pack V4.1 — "Field Medic Framework"*
*Portal Dirección MME Backend + Frontend Reference*
*Versión: 4.1 — Definitiva (Física validada, límites del LLM mitigados)*
*Generado: 2026-05-02*
