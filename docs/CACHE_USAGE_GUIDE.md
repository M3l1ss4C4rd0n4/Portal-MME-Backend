# 🚀 GUÍA DE USO DEL SISTEMA DE CACHÉ

Guía completa para implementar caché en el Portal Energético.

---

## 📋 Índice

1. [Configuración](#configuración)
2. [Decoradores de Caché](#decoradores-de-caché)
3. [Uso del Context Manager](#uso-del-context-manager)
4. [Invalidación de Caché](#invalidación-de-caché)
5. [Endpoints de Administración](#endpoints-de-administración)
6. [Mejores Prácticas](#mejores-prácticas)

---

## 🔧 Configuración

### Verificar Redis

```bash
# Verificar que Redis está corriendo
redis-cli ping
# Debe responder: PONG

# Ver estadísticas
redis-cli info
```

### Configuración en app_factory.py

El caché se inicializa automáticamente al crear la app:

```python
from core.cache_manager import init_cache, cache

# En create_app()
init_cache(app.server)
```

---

## 🎯 Decoradores de Caché

### 1. `@memoize` - Uso General

Cachea cualquier función:

```python
from core.cache_manager import memoize

@memoize(timeout=300, key_prefix="generacion")
def get_generacion_por_fecha(fecha_inicio, fecha_fin):
    """
    Obtiene datos de generación y los cachea por 5 minutos.
    
    La clave de caché se genera automáticamente basada en:
    - Nombre del módulo
    - Nombre de la función
    - Argumentos (fecha_inicio, fecha_fin)
    """
    return db.query(Generacion).filter(...).all()

# Uso
# Primera llamada: consulta a la base de datos
# Segunda llamada (dentro de 5 min): desde caché
datos = get_generacion_por_fecha('2024-01-01', '2024-01-31')
```

### 2. `@cache_dataframe` - Para DataFrames

Especializado para pandas DataFrames:

```python
from core.cache_manager import cache_dataframe
import pandas as pd

@cache_dataframe(timeout=600, key_prefix="df_generacion")
def get_generacion_dataframe(tipo_fuente, fecha_inicio, fecha_fin):
    """
    Cachea DataFrames de pandas (serialización optimizada).
    """
    query = """
        SELECT fecha, recurso, valor_gwh 
        FROM generacion 
        WHERE tipo = %s AND fecha BETWEEN %s AND %s
    """
    return pd.read_sql(query, engine, params=[tipo_fuente, fecha_inicio, fecha_fin])

# Uso
df = get_generacion_dataframe('HIDRAULICA', '2024-01-01', '2024-01-31')
```

### 3. `@cache_json` - Para Respuestas JSON

Para APIs y datos serializables:

```python
from core.cache_manager import cache_json
import requests

@cache_json(timeout=300, key_prefix="api_xm")
def get_datos_xm_api(endpoint):
    """
    Cachea respuestas de API como JSON.
    """
    response = requests.get(f"https://api.xm.com.co/{endpoint}")
    return response.json()

# Uso
datos = get_datos_xm_api("generacion/dia")
```

---

## 🧰 Uso del Context Manager

Para casos donde necesitas más control:

```python
from core.cache_manager import CacheContext

def procesar_datos_complejos(parametro):
    with CacheContext(timeout=300, prefix="proceso") as ctx:
        # Intenta obtener del caché
        resultado = ctx.get(f"resultado_{parametro}")
        
        if resultado is None:
            # Si no está en caché, computar
            resultado = computacion_pesada(parametro)
            
            # Guardar en caché
            ctx.set(f"resultado_{parametro}", resultado)
        
        return resultado

# O usar get_or_compute (más conciso)
def procesar_datos_simple(parametro):
    with CacheContext(timeout=300, prefix="proceso") as ctx:
        return ctx.get_or_compute(
            key=f"resultado_{parametro}",
            compute_func=lambda: computacion_pesada(parametro)
        )
```

---

## 🗑️ Invalidación de Caché

### Invalidar por Patrón

```python
from core.cache_manager import invalidate_cache_pattern

# Invalidar todas las claves de generación
invalidate_cache_pattern("generacion:*")

# Invalidar DataFrames específicos
invalidate_cache_pattern("df_generacion:*")

# Invalidar TODO el caché (¡usar con precaución!)
invalidate_cache_pattern("*")
```

### Invalidar desde un Decorador

```python
@memoize(timeout=300, key_prefix="datos_diarios")
def get_datos_diarios(fecha):
    return query_db(fecha)

# En algún lugar del código:
get_datos_diarios.invalidate()
# Esto invalida todas las claves con prefijo "datos_diarios:*"
```

### Función de Invalidación Condicional

```python
@memoize(
    timeout=300,
    key_prefix="reporte",
    unless=lambda: os.getenv('DISABLE_CACHE') == 'true'
)
def generar_reporte(fecha):
    """
    Si la variable de entorno DISABLE_CACHE es 'true',
    no usará caché.
    """
    return crear_reporte(fecha)
```

---

## 🔌 Endpoints de Administración

### Estadísticas de Caché

```bash
# Ver estadísticas
curl http://localhost:8050/api/cache/stats

# Respuesta:
{
  "used_memory_human": "1.2M",
  "total_keys": 150,
  "connected_clients": 5,
  "uptime_in_days": 12,
  "hit_rate": 0.85
}
```

### Limpiar Caché

```bash
# Limpiar todo
curl -X POST http://localhost:8050/api/cache/clear

# Limpiar por patrón
curl -X POST http://localhost:8050/api/cache/clear \
  -H "Content-Type: application/json" \
  -d '{"pattern": "generacion:*"}'

# Respuesta:
{
  "message": "Invalidadas 42 claves",
  "pattern": "generacion:*"
}
```

---

## 💡 Mejores Prácticas

### 1. Elegir el Timeout Correcto

```python
# Datos que cambian poco: tiempo largo
@memoize(timeout=3600)  # 1 hora
def get_catalogo_recursos():
    return db.query(Catalogo).all()

# Datos en tiempo real: tiempo corto
@memoize(timeout=60)  # 1 minuto
def get_generacion_ultima_hora():
    return db.query(Generacion).filter(fecha=hoy).all()

# Datos históricos: tiempo muy largo
@memoize(timeout=86400)  # 24 horas
def get_generacion_historica(anio):
    return db.query(Generacion).filter(anio=anio).all()
```

### 2. Estructurar Prefijos Jerárquicamente

```
# Buena práctica
generacion:diaria:*
generacion:mensual:*
generacion:anual:*

# Para DataFrames
df:generacion:*
df:transmision:*
df:perdidas:*

# Para APIs
api:xm:*
api:predicciones:*
```

### 3. Manejar Errores Graciosamente

```python
from core.cache_manager import memoize, check_redis_connection
import logging

logger = logging.getLogger(__name__)

@memoize(timeout=300, key_prefix="datos")
def get_datos_importantes():
    try:
        return query_expensiva()
    except Exception as e:
        logger.error(f"Error obteniendo datos: {e}")
        # Retornar valor por defecto o vacío
        return []

# Verificar salud del caché antes de operaciones críticas
def operacion_critica():
    if not check_redis_connection():
        logger.warning("Redis no disponible, ejecutando sin caché")
        return query_expensiva()
    
    return get_datos_importantes()
```

### 4. Invalidación Proactiva

```python
from core.cache_manager import invalidate_cache_pattern

def actualizar_datos_generacion():
    """
    Cuando se actualizan datos, invalidar caché relacionado.
    """
    try:
        # Actualizar base de datos
        db.execute(update_query)
        db.commit()
        
        # Invalidar caché afectado
        invalidate_cache_pattern("generacion:*")
        invalidate_cache_pattern("df_generacion:*")
        
        logger.info("Datos actualizados y caché invalidado")
        
    except Exception as e:
        logger.error(f"Error actualizando datos: {e}")
        db.rollback()
```

### 5. Monitorear Hit Rate

```python
from core.cache_manager import get_cache_stats

def log_cache_performance():
    stats = get_cache_stats()
    
    hit_rate = stats.get('hit_rate', 0)
    total_keys = stats.get('total_keys', 0)
    
    logger.info(f"Caché: {hit_rate:.1%} hit rate, {total_keys} claves")
    
    # Alertar si hit rate es muy bajo
    if hit_rate < 0.5:
        logger.warning("Hit rate de caché muy bajo, revisar configuración")
```

---

## 📊 Ejemplo Completo: Servicio de Generación

```python
from core.cache_manager import memoize, cache_dataframe, invalidate_cache_pattern
from infrastructure.logging.logger import get_logger
import pandas as pd

logger = get_logger(__name__)

class GeneracionService:
    """
    Servicio de generación con caché integrado.
    """
    
    @staticmethod
    @cache_dataframe(timeout=600, key_prefix="df_generacion_fuentes")
    def get_generacion_por_fuente(tipo_fuente, fecha_inicio, fecha_fin):
        """
        Obtiene generación por tipo de fuente.
        Cacheado por 10 minutos.
        """
        logger.info(f"Consultando generación {tipo_fuente}: {fecha_inicio} a {fecha_fin}")
        
        query = """
            SELECT fecha, recurso, valor_gwh, tipo
            FROM generacion_recurso 
            WHERE tipo = %s AND fecha BETWEEN %s AND %s
            ORDER BY fecha, recurso
        """
        
        return pd.read_sql(
            query, 
            engine, 
            params=[tipo_fuente, fecha_inicio, fecha_fin]
        )
    
    @staticmethod
    @memoize(timeout=300, key_prefix="generacion_total_diaria")
    def get_generacion_total_diaria(fecha):
        """
        Obtiene generación total de un día.
        Cacheado por 5 minutos.
        """
        result = db.execute(
            "SELECT SUM(valor_gwh) FROM generacion_sistema WHERE fecha = %s",
            [fecha]
        ).scalar()
        
        return float(result) if result else 0.0
    
    @staticmethod
    def refresh_cache(tipo_fuente=None):
        """
        Fuerza la actualización del caché.
        """
        if tipo_fuente:
            invalidate_cache_pattern(f"df_generacion_fuentes:*{tipo_fuente}*")
            logger.info(f"Caché invalidado para {tipo_fuente}")
        else:
            invalidate_cache_pattern("df_generacion:*")
            invalidate_cache_pattern("generacion_total:*")
            logger.info("Todo el caché de generación invalidado")


# Uso en un callback de Dash
from dash import callback, Output, Input

@callback(
    Output("tabla-generacion", "data"),
    Input("filtro-fuente", "value"),
    Input("filtro-fecha", "start_date"),
    Input("filtro-fecha", "end_date"),
)
def actualizar_tabla(tipo_fuente, fecha_inicio, fecha_fin):
    # Esta llamada está cacheada automáticamente
    df = GeneracionService.get_generacion_por_fuente(
        tipo_fuente, fecha_inicio, fecha_fin
    )
    return df.to_dict('records')
```

---

## 🔍 Troubleshooting

### Problema: "Redis no disponible"

```bash
# Verificar servicio
sudo systemctl status redis

# Reiniciar si es necesario
sudo systemctl restart redis

# Ver logs
sudo tail -f /var/log/redis/redis-server.log
```

### Problema: Caché no funciona

```python
# Verificar conexión
from core.cache_manager import check_redis_connection
print(check_redis_connection())  # Debe imprimir True

# Verificar configuración
import os
print(os.getenv('REDIS_URL'))  # Verificar variable de entorno
```

### Problema: Memoria llena

```bash
# Ver uso de memoria
redis-cli info memory

# Limpiar caché antiguo
redis-cli --eval scripts/limpiar_cache.lua

# O configurar política de expiración
redis-cli config set maxmemory-policy allkeys-lru
```

---

## 📈 Métricas Esperadas

Con caché implementado correctamente:

| Métrica | Sin Caché | Con Caché | Mejora |
|---------|-----------|-----------|--------|
| **Tiempo de respuesta** | 2-5s | 50-200ms | **90%** |
| **Consultas a BD** | 100% | 10-20% | **80%** |
| **Uso de CPU** | Alto | Bajo | **60%** |
| **Hit Rate** | - | 70-90% | - |

---

## 📞 Soporte

Para problemas con el caché:

1. Verificar logs: `tail -f logs/app.log | grep -i cache`
2. Verificar Redis: `redis-cli ping`
3. Estadísticas: `curl http://localhost:8050/api/cache/stats`
4. Limpiar caché: `curl -X POST http://localhost:8050/api/cache/clear`
