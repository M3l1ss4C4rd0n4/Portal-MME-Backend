# Configuración de Autenticación SharePoint — Microsoft Graph API

## Contexto

Los archivos Excel compartidos por el Ministerio están en **SharePoint** (`minenergiacol.sharepoint.com`)
y requieren autenticación para descargarse. El script `actualizar_desde_onedrive.py` usa la
**Microsoft Graph API** para acceder a estos archivos de forma programática.

Hay **dos opciones** de autenticación. Elige la que mejor aplique.

---

## Opción A — App Registration (Recomendado para automatización/cron)

Esta opción **no requiere interacción manual** y funciona en cron jobs. Necesita que un
administrador de Azure AD del Ministerio cree un App Registration.

### Paso 1: Crear App Registration en Azure AD

1. Ve a [Azure Portal → Azure Active Directory → App registrations](https://portal.azure.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/~/RegisteredApps)
   - Inicia sesión con una cuenta de **administrador** del tenant `minenergiacol.onmicrosoft.com`

2. Click **"New registration"**:
   - **Name**: `Portal Energético - ArcGIS SharePoint Reader` (o similar)
   - **Supported account types**: "Accounts in this organizational directory only"
   - **Redirect URI**: dejar vacío (no se usa en Client Credentials)

3. Click **"Register"**

### Paso 2: Agregar permisos de Graph API

1. En la página del App Registration, ve a **"API permissions"**
2. Click **"Add a permission"** → **"Microsoft Graph"** → **"Application permissions"**
3. Busca y agrega:
   - `Sites.Read.All` (leer contenido de SharePoint)
   - `Files.Read.All` (leer archivos de OneDrive/SharePoint)
4. Click **"Grant admin consent"** (botón azul arriba) — requiere admin

### Paso 3: Crear Client Secret

1. Ve a **"Certificates & secrets"**
2. Click **"New client secret"**
   - **Description**: `arcgis-integration`
   - **Expires**: 24 months (o según política del Ministerio)
3. **Copia el valor del secret** inmediatamente (no se muestra después)

### Paso 4: Obtener IDs

De la página principal del App Registration, copia:
- **Application (client) ID** → es el `MS_CLIENT_ID`
- **Directory (tenant) ID** → es el `MS_TENANT_ID`

### Paso 5: Configurar en el servidor

Edita `/home/admonctrlxm/server/tests/ARGIS/.env`:

```env
MS_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MS_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MS_CLIENT_SECRET=valor_del_secret_copiado
```

### Paso 6: Probar

```bash
cd /home/admonctrlxm/server
python3 tests/ARGIS/actualizar_desde_onedrive.py --dry-run
```

Si funciona, verás los archivos descargándose y convirtiéndose a CSV sin publicar en ArcGIS.

---

## Opción B — Device Code Flow (Sin admin de Azure AD)

Si no tienes acceso de admin al Azure AD del Ministerio, puedes usar **Device Code Flow**.
Solo necesita un App Registration con permisos **delegados** (no de aplicación).

### Paso 1: Crear App Registration

Igual que Opción A, Paso 1, pero con un cambio:
- En **"Authentication"** → **"Advanced settings"** → habilita **"Allow public client flows"** = Sí

### Paso 2: Agregar permisos delegados

1. **"API permissions"** → **"Add a permission"** → **"Microsoft Graph"** → **"Delegated permissions"**
2. Agrega:
   - `Files.Read.All`
   - `Sites.Read.All`
3. (Admin consent recomendado pero no obligatorio en este flujo)

### Paso 3: No se necesita Client Secret

El Device Code Flow es un flujo "público" — no requiere secret.

### Paso 4: Configurar .env

```env
MS_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MS_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MS_CLIENT_SECRET=
```

(Dejar `MS_CLIENT_SECRET` vacío)

### Paso 5: Autenticarse por primera vez

```bash
cd /home/admonctrlxm/server
python3 tests/ARGIS/actualizar_desde_onedrive.py --auth
```

Esto mostrará un código y un link. Abre el link en un navegador, ingresa el código, e
inicia sesión con tu cuenta del Ministerio (`usuario@minenergiacol.onmicrosoft.com`).

El **refresh token** se guarda en `.ms_token_cache.json` y se reutiliza automáticamente
en futuras ejecuciones.

### Paso 6: Ejecución automática

Después de la autenticación inicial, el script funciona sin interacción:

```bash
python3 tests/ARGIS/actualizar_desde_onedrive.py --dry-run
```

> **Nota**: El refresh token tiene una vigencia limitada (normalmente 90 días).
> Si expira, ejecuta `--auth` nuevamente.

---

## Encontrar el Tenant ID

Si no conoces el Tenant ID del Ministerio, puedes obtenerlo de varias formas:

1. **Azure Portal**: Azure AD → Overview → "Tenant ID"
2. **URL directa**: `https://login.microsoftonline.com/minenergiacol.onmicrosoft.com/.well-known/openid-configuration`
   - El campo `token_endpoint` contiene el tenant ID en la URL
3. **PowerShell** (si tienes acceso):
   ```powershell
   (Get-AzTenant).Id
   ```

---

## Troubleshooting

### Error 401 — Token rechazado
- Ejecuta `--auth` para re-autenticarse
- Verifica que MS_TENANT_ID sea correcto

### Error 403 — Acceso denegado
- La cuenta o app no tiene permisos en los sitios de SharePoint donde están los archivos
- Pide al administrador de SharePoint que comparta los archivos con la cuenta/app

### Error "No se pudo autenticar"
- Verifica que `.env` tenga MS_TENANT_ID y MS_CLIENT_ID configurados
- Para Client Credentials: también necesitas MS_CLIENT_SECRET
- Para Device Code: ejecuta `python3 actualizar_desde_onedrive.py --auth`

### El archivo descargado es HTML, no Excel
- La autenticación falló silenciosamente (SharePoint devuelve página de login)
- Re-autenticar con `--auth` o verificar permisos del App Registration

---

## Archivos de referencia

| Archivo | Descripción |
|---------|-------------|
| `.env` | Variables de configuración (credenciales ArcGIS + Microsoft) |
| `onedrive_archivos.json` | Lista de archivos SharePoint a procesar (links, hojas, etc.) |
| `.ms_token_cache.json` | Cache de tokens (se crea automáticamente, **NO compartir**) |
| `actualizar_desde_onedrive.py` | Script principal |
| `actualizar_capa_hospedada.py` | Script auxiliar de estrategia overwrite/append |
