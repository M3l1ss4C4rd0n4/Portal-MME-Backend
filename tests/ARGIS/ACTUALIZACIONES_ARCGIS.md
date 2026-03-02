# Actualizaciones Automáticas a ArcGIS Enterprise — Portal Energético MME

## Descripción General

Esta carpeta contiene el sistema de **publicación y actualización automática** de datos
en **ArcGIS Enterprise** del Ministerio de Minas y Energía. Los datos se publican
simultáneamente en **dos cuentas** de ArcGIS para redundancia y acceso departamental.

**Portal ArcGIS:** `https://arcgisenterprise.minenergia.gov.co/portal/`

### Cuentas ArcGIS

| Cuenta | Rol | Archivo .env |
|--------|-----|-------------|
| **Vice_Energia** | org_admin | `.env` |
| **Adminportal** | org_admin | `.env.adminportal` |

---

## Arquitectura

```
                ┌─────────────┐     ┌──────────────────┐
  Cron :00 ───▶│  XM API     │────▶│ CSV local        │
                │ (pydataxm)  │     │ metricas_xm_     │
                └─────────────┘     │ arcgis.csv       │
                                    └────────┬─────────┘
                                             │
                           ┌─────────────────┼─────────────────┐
                           ▼                                   ▼
                  ┌─────────────────┐                ┌─────────────────┐
                  │  Vice_Energia   │                │  Adminportal    │
                  │  CSV Item       │                │  CSV Item       │
                  │  Feature Service│                │  Feature Service│
                  └─────────────────┘                └─────────────────┘

                ┌─────────────┐     ┌──────────────────┐
  Cron :30 ───▶│  SharePoint  │────▶│ Excel → CSV      │
                │  OneDrive    │     │ data/onedrive/   │
                └─────────────┘     └────────┬─────────┘
                                             │
                           ┌─────────────────┼─────────────────┐
                           ▼                                   ▼
                  ┌─────────────────┐                ┌─────────────────┐
                  │  Vice_Energia   │                │  Adminportal    │
                  │  Feature Service│                │  Feature Service│
                  └─────────────────┘                └─────────────────┘
```

---

## Scripts

### 1. `ejecutar_dual.sh` — Orquestador

Wrapper bash que ejecuta cada script secuencialmente para ambas cuentas.

```bash
./ejecutar_dual.sh xm          # Solo datos XM (ambas cuentas)
./ejecutar_dual.sh onedrive    # Solo datos OneDrive (ambas cuentas)
./ejecutar_dual.sh todo        # XM + OneDrive (ambas cuentas)
```

### 2. `actualizar_datos_xm_online.py` — Datos XM Colombia (801 líneas)

Extrae métricas diarias de **XM Colombia** (operador del mercado eléctrico) via API
y las publica en ArcGIS Enterprise.

**Métricas extraídas:**
- Generación real (GWh)
- Precio de bolsa (COP/kWh)
- Volumen útil de embalses (%)
- Capacidad efectiva neta

**Flujo:**
1. Consulta API XM (`servapibi.xm.com.co`) vía `pydataxm`
2. Combina métricas en un DataFrame con coordenadas geográficas (Bogotá)
3. Guarda CSV en `/home/admonctrlxm/server/data/metricas_xm_arcgis.csv`
4. Sube CSV al portal ArcGIS (Item tipo CSV)
5. Sobrescribe el Feature Service (capa hospedada) para que los dashboards se actualicen

**Detección inteligente de cambios:**
- Compara fecha más reciente en CSV vs. datos disponibles en XM
- Si XM no ha publicado datos nuevos → se salta la extracción
- **Hash per-cuenta:** cada cuenta guarda el MD5 del CSV en `.last_xm_hash_{usuario}.txt`.
  Si Vice_Energia actualiza el CSV, Adminportal detecta que no lo ha publicado y reutiliza
  el CSV existente sin llamar de nuevo a la API XM

**Opciones:**
```bash
python3 actualizar_datos_xm_online.py                          # Producción
python3 actualizar_datos_xm_online.py --dry-run                # Solo prueba
python3 actualizar_datos_xm_online.py --env-file .env.adminportal  # Otra cuenta
```

### 3. `actualizar_desde_onedrive.py` — Archivos SharePoint/OneDrive (1203 líneas)

Descarga archivos Excel compartidos por dependencias del Ministerio desde
SharePoint/OneDrive, los convierte a CSV y los publica como capas hospedadas.

**Archivos configurados (7):**

| # | Nombre | Hoja Excel | Origen |
|---|--------|-----------|--------|
| 1 | Matriz_Subsidios_DEE | (todas) | SharePoint DEE |
| 2 | Matriz_Implementacion_Base | base | SharePoint Teams |
| 3 | Matriz_Subsidios_KPIs | kpis | SharePoint Teams |
| 4 | Matriz_Subsidios_Validacion | validación | SharePoint Teams |
| 5 | Matriz_Subsidios_Pagos | pagos | SharePoint Teams |
| 6 | Matriz_Ejecucion_Presupuestal_2026 | resumen | SharePoint DEE |
| 7 | Comunidades_Energeticas_Avance | Hoja1 | OneDrive público |

> **Nota:** Los archivos 1-6 requieren autenticación Microsoft Graph (ver sección
> "Pendientes"). Solo el #7 funciona actualmente (link público con `&download=1`).

**Detección de cambios:**
- Hash MD5 per-cuenta del Excel descargado (`.onedrive_hashes_{usuario}.json`)
- Si el archivo no cambió desde la última ejecución → se omite

**Opciones:**
```bash
python3 actualizar_desde_onedrive.py                                    # Todos los archivos
python3 actualizar_desde_onedrive.py --archivo 7                        # Solo archivo #7
python3 actualizar_desde_onedrive.py --force                            # Forzar sin verificar hash
python3 actualizar_desde_onedrive.py --dry-run                          # Solo descarga, no publica
python3 actualizar_desde_onedrive.py --listar                           # Lista archivos configurados
python3 actualizar_desde_onedrive.py --env-file .env.adminportal --config-file onedrive_archivos_adminportal.json
```

### 4. `actualizar_capa_hospedada.py` — Overwrite de Feature Service (709 líneas)

Módulo auxiliar que sobrescribe el contenido de un Feature Service hospedado con datos
de un CSV. Lo llaman los otros scripts internamente.

**Estrategias:**
1. **Overwrite** (principal): `FeatureLayerCollection.manager.overwrite()` — reemplaza todo
2. **Truncate + Append** (respaldo automático): borra registros y agrega nuevos

> En ArcGIS Enterprise, el Feature Service está **desacoplado** del CSV.
> Actualizar el CSV en el portal NO actualiza los dashboards.
> Este script es el que realmente hace que los dashboards vean datos nuevos.

---

## Cron Jobs

Configurados en `crontab -e` del usuario `admonctrlxm`:

```cron
# Datos XM → ambas cuentas (cada hora en punto)
0 * * * * /home/admonctrlxm/server/tests/ARGIS/ejecutar_dual.sh xm >> /home/admonctrlxm/server/logs/arcgis_dual.log 2>&1

# Archivos OneDrive → ambas cuentas (cada hora a los :30)
30 * * * * /home/admonctrlxm/server/tests/ARGIS/ejecutar_dual.sh onedrive >> /home/admonctrlxm/server/logs/arcgis_dual.log 2>&1
```

---

## Items en ArcGIS Enterprise

### Datos XM (Métricas Energéticas)

| Cuenta | Tipo | Item ID | Nombre del Servicio |
|--------|------|---------|-------------------|
| Vice_Energia | CSV | `5677c0b08ddc49a88a2d4d1c1270c04f` | Metricas Energia XM Colombia |
| Vice_Energia | Feature Service | `6029bbfeb9874e99b5bb99edb1097ad6` | Metricas_Energia_XM_Colombia |
| Adminportal | CSV | `4805f301715a4a1381c173a8d9d07f0e` | Metricas Energia XM Colombia |
| Adminportal | Feature Service | `72dbcd67243745dfbac254cdf4f69436` | Metricas_Energia_XM_Colombia_Admin |

### Datos OneDrive (Comunidades Energéticas)

| Cuenta | Tipo | Item ID | Nombre |
|--------|------|---------|--------|
| Vice_Energia | Feature Service | `68e49bc23bb0493fa1de7778503d5b9d` | Comunidades Energéticas - Avance Proyectos |
| Adminportal | Feature Service | `c3bb4e3ed1374638b5ab8f8292552643` | CE_Avance Proyectos |

---

## Archivos de Configuración

| Archivo | Descripción |
|---------|-------------|
| `.env` | Credenciales Vice_Energia + IDs de items XM |
| `.env.adminportal` | Credenciales Adminportal + IDs de items XM |
| `.env.example` | Plantilla de referencia con todas las variables |
| `onedrive_archivos.json` | Config de archivos OneDrive para Vice_Energia |
| `onedrive_archivos_adminportal.json` | Config de archivos OneDrive para Adminportal |

### Variables de Entorno (.env)

```env
ARCGIS_PORTAL_URL=https://arcgisenterprise.minenergia.gov.co/portal/
ARCGIS_USERNAME=Vice_Energia
ARCGIS_PASSWORD=...
FEATURE_LAYER_ID=<id_csv_item>
HOSTED_LAYER_ITEM_ID=<id_feature_service>
ARCGIS_UPDATE_STRATEGY=overwrite
DIAS_ATRAS=7

# Para archivos SharePoint restringidos (pendiente de configurar):
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
```

---

## Archivos de Estado (generados automáticamente)

| Archivo | Propósito |
|---------|-----------|
| `.last_xm_hash_Vice_Energia.txt` | MD5 del CSV XM la última vez que Vice_Energia publicó |
| `.last_xm_hash_Adminportal.txt` | MD5 del CSV XM la última vez que Adminportal publicó |
| `.onedrive_hashes_Vice_Energia.json` | Hashes MD5 de archivos OneDrive para Vice_Energia |
| `.onedrive_hashes_Adminportal.json` | Hashes MD5 de archivos OneDrive para Adminportal |

Estos archivos permiten que cada cuenta detecte independientemente si necesita publicar,
incluso cuando comparten los mismos CSV locales.

---

## Logs

| Log | Contenido |
|-----|-----------|
| `logs/arcgis_dual.log` | Log general del wrapper `ejecutar_dual.sh` |
| `logs/actualizacion_xm_arcgis_vice_energia.log` | Detalle de XM → Vice_Energia |
| `logs/actualizacion_xm_arcgis_adminportal.log` | Detalle de XM → Adminportal |
| `logs/actualizacion_onedrive_arcgis_vice_energia.log` | Detalle de OneDrive → Vice_Energia |
| `logs/actualizacion_onedrive_arcgis_adminportal.log` | Detalle de OneDrive → Adminportal |

---

## Dependencias

```
pip install pydataxm arcgis pandas python-dotenv openpyxl requests msal
```

- **pydataxm** — Cliente Python para la API de XM Colombia
- **arcgis** — API de ArcGIS para Python (conexión al portal, overwrite)
- **pandas** — Procesamiento de datos
- **python-dotenv** — Carga de variables de entorno
- **openpyxl** — Lectura de archivos Excel (.xlsx)
- **requests** — Descarga de archivos desde OneDrive/SharePoint
- **msal** — Autenticación Microsoft (para archivos SharePoint restringidos)

---

## Ejecución Manual

```bash
cd /home/admonctrlxm/server/tests/ARGIS

# Ejecutar todo para ambas cuentas
./ejecutar_dual.sh todo

# Solo XM para Vice_Energia
python3 actualizar_datos_xm_online.py

# Solo XM para Adminportal
python3 actualizar_datos_xm_online.py --env-file .env.adminportal

# Solo OneDrive archivo #7 para Adminportal
python3 actualizar_desde_onedrive.py --env-file .env.adminportal \
    --config-file onedrive_archivos_adminportal.json --archivo 7

# Forzar actualización sin verificar hash
python3 actualizar_datos_xm_online.py --env-file .env.adminportal --force
python3 actualizar_desde_onedrive.py --force
```

---

## Notas Técnicas

### Problema del CSV compartido (resuelto)

Ambas cuentas ArcGIS comparten los mismos archivos CSV locales. Cuando Vice_Energia
(que corre primero en el wrapper) descarga datos nuevos y actualiza el CSV, Adminportal
(que corre segundo) veía "sin cambios" porque el CSV ya estaba actualizado.

**Solución implementada:** Tracking de hash MD5 por cuenta. Cada cuenta mantiene su propio
registro del último hash que publicó. Si el CSV cambió pero esta cuenta no lo ha publicado,
se detecta como "pendiente" y se reutiliza el CSV existente sin volver a llamar a la API
fuente.

### Timeouts del servidor de hosting

El hostname interno `serv-mme-arcgisenterprise.minminas.gov.co` (usado internamente por
ArcGIS para el `overwrite()`) experimenta timeouts intermitentes. Las operaciones de
overwrite pueden tardar entre 60 segundos y 15 minutos según la carga del servidor.
El script maneja esto con reintentos automáticos de la librería `urllib3`.

### Autenticación SharePoint (pendiente)

Los archivos 1-6 de OneDrive están en SharePoint del Ministerio con acceso restringido.
Para habilitarlos se necesita:

1. **Crear App Registration en Azure AD** del tenant `minenergiacol.onmicrosoft.com`
2. Asignar permisos `Sites.Read.All` y `Files.Read.All` (Application permissions)
3. Crear un Client Secret
4. Configurar en ambos `.env`:
   ```env
   MS_TENANT_ID=<tenant-id>
   MS_CLIENT_ID=<client-id>
   MS_CLIENT_SECRET=<client-secret>
   ```

Esto requiere un administrador de Azure AD del Ministerio.
