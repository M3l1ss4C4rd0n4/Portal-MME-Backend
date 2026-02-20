#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script: Actualización de capas hospedadas en ArcGIS Enterprise desde SharePoint/OneDrive
========================================================================================

DESCRIPCIÓN:
    Descarga archivos Excel (.xlsx) compartidos por SharePoint del Ministerio
    (con acceso restringido), los convierte a CSV y los publica/actualiza como
    capas hospedadas en ArcGIS Enterprise.

    Soporta autenticación Microsoft Graph API para archivos con acceso restringido
    a usuarios del Ministerio (minenergiacol.sharepoint.com).

ARCHIVOS CONFIGURADOS:
    1. Matriz Subsidios (DEE Supervisión)
    2. Matriz Implementación → pestaña "base"
    3. Matriz Subsidios → pestañas "kpis", "validación", "pagos" (3 capas)
    4. Matriz Ejecución Presupuestal 2026 → pestaña "resumen"
    5. Comunidades_Energeticas_Avance → pestaña "Hoja1"

AUTENTICACIÓN:
    Requiere un App Registration en Azure AD del Ministerio.
    Ver SETUP_SHAREPOINT_AUTH.md para instrucciones.

    Alternativa: Device Code Flow (autenticación interactiva una sola vez,
    luego usa refresh token automáticamente).

USO:
    # Primera vez: autenticarse interactivamente
    python3 actualizar_desde_onedrive.py --auth

    # Procesar todos los archivos
    python3 actualizar_desde_onedrive.py

    # Solo descargar, no publicar en ArcGIS
    python3 actualizar_desde_onedrive.py --dry-run

    # Procesar solo un archivo específico
    python3 actualizar_desde_onedrive.py --archivo 1

    # Listar archivos configurados
    python3 actualizar_desde_onedrive.py --listar

CRON:
    0 7 * * * cd /home/admonctrlxm/server && python3 tests/ARGIS/actualizar_desde_onedrive.py >> logs/arcgis_onedrive.log 2>&1

Autor: Portal Energético MME
Fecha: 2026-02-17
"""

import sys
import os
import json
import logging
import argparse
import time
import re
import base64
import hashlib
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Determinar archivo .env (soporta --env-file para múltiples cuentas)
_env_file = Path(__file__).parent / '.env'
_config_override = None
for _i, _arg in enumerate(sys.argv):
    if _arg == '--env-file' and _i + 1 < len(sys.argv):
        _env_file = Path(sys.argv[_i + 1])
        if not _env_file.is_absolute():
            _env_file = Path(__file__).parent / _env_file
    elif _arg == '--config-file' and _i + 1 < len(sys.argv):
        _config_override = Path(sys.argv[_i + 1])
        if not _config_override.is_absolute():
            _config_override = Path(__file__).parent / _config_override

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_file, override=True)
    print(f"📄 Usando env: {_env_file.name}")
except ImportError:
    pass

# --- Conexión al portal ArcGIS Enterprise ---
ARCGIS_PORTAL_URL = os.getenv(
    "ARCGIS_PORTAL_URL",
    "https://arcgisenterprise.minenergia.gov.co/portal"
)
ARCGIS_USERNAME = os.getenv("ARCGIS_USERNAME", "")
ARCGIS_PASSWORD = os.getenv("ARCGIS_PASSWORD", "")

# --- Microsoft Graph / SharePoint Authentication ---
# Opción A: App Registration (Client Credentials) — RECOMENDADO para cron
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")          # e.g. "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")           # App Registration client ID
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")   # App Registration client secret

# Opción B: Device Code Flow (interactivo primera vez, luego automático)
# Usa el mismo MS_CLIENT_ID pero sin client_secret
# El token se guarda en .ms_token_cache.json

# --- Rutas ---
BASE_DIR = Path(__file__).parent.parent.parent  # /home/admonctrlxm/server
SCRIPT_DIR = Path(__file__).parent               # tests/ARGIS/
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data" / "onedrive"
CONFIG_FILE = _config_override if _config_override else (SCRIPT_DIR / "onedrive_archivos.json")
TOKEN_CACHE_FILE = SCRIPT_DIR / ".ms_token_cache.json"
HASH_CACHE_FILE = SCRIPT_DIR / ".onedrive_hashes.json"

# --- Logging ---
LOG_FILE = LOG_DIR / "actualizacion_onedrive_arcgis.log"

# ============================================================================
# CONFIGURAR LOGGING Y DIRECTORIOS
# ============================================================================

LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("onedrive_arcgis")


# ============================================================================
# AUTENTICACIÓN MICROSOFT GRAPH API
# ============================================================================

class MicrosoftGraphAuth:
    """
    Maneja autenticación con Microsoft Graph API para acceder a SharePoint.

    Soporta dos flujos:
      1. Client Credentials (app-only, sin usuario) — ideal para cron/automatización
      2. Device Code Flow (interactivo) — ideal para primera configuración

    El token se cachea en disco para reutilización automática.
    """

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    SCOPES_DELEGATED = ["Files.Read.All", "Sites.Read.All"]

    def __init__(self):
        self._access_token = None
        self._token_expiry = 0

    def autenticar(self) -> str:
        """
        Obtiene un access token para Microsoft Graph.
        Intenta en orden:
          1. Token cacheado válido
          2. Client Credentials (si MS_CLIENT_SECRET configurado)
          3. Refresh Token del cache (si existe de device code previo)
          4. Falla con instrucciones

        Returns:
            Access token string.
        """
        # 1. Token en memoria aún válido
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        # 2. Client credentials (app-only)
        if MS_TENANT_ID and MS_CLIENT_ID and MS_CLIENT_SECRET:
            return self._auth_client_credentials()

        # 3. Refresh token del cache (de device code flow previo)
        if MS_TENANT_ID and MS_CLIENT_ID:
            token = self._auth_from_cache()
            if token:
                return token

        # 4. No hay forma de autenticar
        raise RuntimeError(
            "No se pudo autenticar con Microsoft Graph.\n\n"
            "Los archivos de SharePoint del Ministerio requieren autenticación.\n"
            "Configura una de estas opciones en el archivo .env:\n\n"
            "  OPCIÓN A — App Registration (recomendado para automatización):\n"
            "    MS_TENANT_ID=<tenant-id-del-ministerio>\n"
            "    MS_CLIENT_ID=<client-id-del-app>\n"
            "    MS_CLIENT_SECRET=<client-secret>\n\n"
            "  OPCIÓN B — Device Code Flow (interactivo, una sola vez):\n"
            "    MS_TENANT_ID=<tenant-id-del-ministerio>\n"
            "    MS_CLIENT_ID=<client-id-del-app>\n"
            "    Luego ejecuta: python3 actualizar_desde_onedrive.py --auth\n\n"
            "Ver SETUP_SHAREPOINT_AUTH.md para instrucciones detalladas."
        )

    def _auth_client_credentials(self) -> str:
        """Flujo Client Credentials (app-only, sin usuario interactivo)."""
        import msal

        logger.info("🔑 Autenticando con Microsoft Graph (Client Credentials)...")

        app = msal.ConfidentialClientApplication(
            client_id=MS_CLIENT_ID,
            client_credential=MS_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{MS_TENANT_ID}",
        )

        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" in result:
            self._access_token = result["access_token"]
            self._token_expiry = time.time() + result.get("expires_in", 3600)
            logger.info("  ✅ Autenticado (Client Credentials)")
            return self._access_token
        else:
            error = result.get("error_description", result.get("error", "Unknown"))
            raise RuntimeError(f"Error en Client Credentials: {error}")

    def _auth_from_cache(self) -> str:
        """Intenta obtener token desde cache (refresh token de device code flow)."""
        import msal

        if not TOKEN_CACHE_FILE.exists():
            return None

        logger.info("🔑 Intentando renovar token desde cache...")

        cache = msal.SerializableTokenCache()
        cache.deserialize(TOKEN_CACHE_FILE.read_text())

        app = msal.PublicClientApplication(
            client_id=MS_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{MS_TENANT_ID}",
            token_cache=cache,
        )

        accounts = app.get_accounts()
        if not accounts:
            logger.warning("  No hay cuentas en cache. Ejecuta: --auth")
            return None

        result = app.acquire_token_silent(
            scopes=self.SCOPES_DELEGATED,
            account=accounts[0],
        )

        if result and "access_token" in result:
            # Guardar cache actualizado
            TOKEN_CACHE_FILE.write_text(cache.serialize())
            self._access_token = result["access_token"]
            self._token_expiry = time.time() + result.get("expires_in", 3600)
            logger.info("  ✅ Token renovado desde cache (usuario: %s)", accounts[0].get("username", "?"))
            return self._access_token

        logger.warning("  Token expirado. Ejecuta: --auth para re-autenticar")
        return None

    def auth_device_code_interactive(self) -> str:
        """
        Flujo Device Code: el usuario abre un link en el navegador y autoriza.
        Solo necesita hacerse una vez. El refresh token se guarda para futuras ejecuciones.
        """
        import msal

        if not MS_TENANT_ID or not MS_CLIENT_ID:
            raise RuntimeError(
                "Configura MS_TENANT_ID y MS_CLIENT_ID en .env antes de autenticar.\n"
                "Ver SETUP_SHAREPOINT_AUTH.md"
            )

        cache = msal.SerializableTokenCache()
        if TOKEN_CACHE_FILE.exists():
            cache.deserialize(TOKEN_CACHE_FILE.read_text())

        app = msal.PublicClientApplication(
            client_id=MS_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{MS_TENANT_ID}",
            token_cache=cache,
        )

        flow = app.initiate_device_flow(scopes=self.SCOPES_DELEGATED)

        if "user_code" not in flow:
            raise RuntimeError(f"Error iniciando Device Code Flow: {flow}")

        print("\n" + "=" * 60)
        print("  AUTENTICACIÓN MICROSOFT — DEVICE CODE FLOW")
        print("=" * 60)
        print(f"\n  1. Abre este link en tu navegador:")
        print(f"     {flow['verification_uri']}")
        print(f"\n  2. Ingresa este código:")
        print(f"     {flow['user_code']}")
        print(f"\n  3. Inicia sesión con tu cuenta del Ministerio")
        print(f"     (usuario@minenergiacol.onmicrosoft.com)")
        print(f"\n  Esperando autenticación...")
        print("=" * 60 + "\n")

        result = app.acquire_token_by_device_flow(flow)

        if "access_token" in result:
            # Guardar cache con refresh token
            TOKEN_CACHE_FILE.write_text(cache.serialize())
            # Proteger archivo
            TOKEN_CACHE_FILE.chmod(0o600)

            self._access_token = result["access_token"]
            self._token_expiry = time.time() + result.get("expires_in", 3600)

            username = result.get("id_token_claims", {}).get("preferred_username", "desconocido")
            logger.info("✅ Autenticado exitosamente como: %s", username)
            logger.info("   Token guardado en: %s", TOKEN_CACHE_FILE)
            logger.info("   Las próximas ejecuciones usarán el token automáticamente.")
            return self._access_token
        else:
            error = result.get("error_description", result.get("error", "Unknown"))
            raise RuntimeError(f"Error en Device Code Flow: {error}")


# Instancia global
_graph_auth = MicrosoftGraphAuth()


# ============================================================================
# DESCARGA DESDE SHAREPOINT VÍA MICROSOFT GRAPH API
# ============================================================================

def _encode_sharing_url(share_link: str) -> str:
    """
    Codifica un link de compartir de SharePoint/OneDrive en formato
    base64url para usar con la API de Graph /shares/.

    Formato: u!{base64url_encoded_link}
    Ref: https://learn.microsoft.com/en-us/graph/api/shares-get
    """
    encoded = base64.urlsafe_b64encode(share_link.encode()).decode().rstrip("=")
    return f"u!{encoded}"


def _es_sharepoint_ministerio(share_link: str) -> bool:
    """Detecta si el link es de SharePoint/OneDrive del Ministerio."""
    return (
        "minenergiacol.sharepoint.com" in share_link
        or "minenergiacol-my.sharepoint.com" in share_link
    )


def descargar_desde_sharepoint_graph(share_link: str, nombre_destino: str) -> Path:
    """
    Descarga un archivo de SharePoint usando Microsoft Graph API con autenticación.

    Usa el endpoint /shares/{encodedUrl}/driveItem/content para descargar el archivo
    directamente usando el link de compartir.

    Args:
        share_link:     URL de compartir de SharePoint.
        nombre_destino: Nombre para guardar el archivo.

    Returns:
        Path al archivo descargado.
    """
    logger.info("📥 Descargando desde SharePoint (autenticado)...")
    logger.info("  Link: %s", share_link[:80] + "..." if len(share_link) > 80 else share_link)

    # Obtener token de autenticación
    access_token = _graph_auth.autenticar()

    # Codificar link para Graph API
    sharing_token = _encode_sharing_url(share_link)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    # Obtener metadata del archivo
    meta_url = f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem"
    logger.info("  Obteniendo metadata del archivo...")

    meta_resp = requests.get(meta_url, headers=headers, timeout=30)

    if meta_resp.status_code == 401:
        raise RuntimeError(
            "Token de acceso rechazado (401). "
            "Puede que necesites re-autenticar: python3 actualizar_desde_onedrive.py --auth"
        )
    elif meta_resp.status_code == 403:
        raise RuntimeError(
            "Acceso denegado (403). La cuenta autenticada no tiene acceso a este archivo. "
            "Verifica que la cuenta tenga permisos en SharePoint."
        )
    elif meta_resp.status_code != 200:
        raise RuntimeError(
            f"Error obteniendo metadata (HTTP {meta_resp.status_code}): {meta_resp.text[:200]}"
        )

    meta = meta_resp.json()
    nombre_real = meta.get("name", nombre_destino)
    size_bytes = meta.get("size", 0)
    logger.info("  Archivo: %s (%.1f KB)", nombre_real, size_bytes / 1024)

    # Descargar contenido
    download_url = f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem/content"
    logger.info("  Descargando contenido...")

    dl_resp = requests.get(download_url, headers=headers, timeout=300, stream=True)
    dl_resp.raise_for_status()

    # Guardar archivo
    destino = DATA_DIR / nombre_destino
    total_bytes = 0
    with open(destino, "wb") as f:
        for chunk in dl_resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total_bytes += len(chunk)

    logger.info("  ✅ Descargado: %s (%.1f KB)", destino.name, total_bytes / 1024)

    # Validar que sea un archivo Excel real
    with open(destino, "rb") as f:
        magic = f.read(4)
    # XLSX files start with PK (ZIP format), XLS with D0CF11E0
    if magic[:2] != b'PK' and magic[:4] != b'\xd0\xcf\x11\xe0':
        with open(destino, "rb") as f:
            inicio = f.read(500)
        if b"<html" in inicio.lower() or b"<!doctype" in inicio.lower():
            raise RuntimeError(
                "El archivo descargado es una página HTML, no un Excel. "
                "La autenticación puede haber fallado. Ejecuta: --auth"
            )

    return destino


def descargar_archivo_onedrive(share_link: str, nombre_destino: str = None) -> Path:
    """
    Descarga un archivo desde un link compartido de OneDrive/SharePoint.

    Estrategia:
      1. Intenta descarga pública con &download=1 (funciona si el link es
         "cualquier persona con el enlace")
      2. Si descarga HTML (login page), intenta con Graph API autenticado
      3. Si no hay auth configurada, da error con instrucciones
    """
    if not nombre_destino:
        nombre_destino = "archivo_onedrive.xlsx"

    # Limpiar nombre
    nombre_destino = re.sub(r'[^\w\-_\.\s]', '_', nombre_destino)

    # Paso 1: Intentar descarga pública (sin auth)
    try:
        ruta = _descargar_publico(share_link, nombre_destino)
        # Validar que sea un Excel real, no HTML de login
        if _validar_es_excel(ruta):
            return ruta
        logger.warning("  Descarga pública devolvió HTML (login page). Intentando con autenticación...")
    except Exception as e:
        logger.warning("  Descarga pública falló: %s. Intentando con autenticación...", e)

    # Paso 2: Intentar con Microsoft Graph API (autenticado)
    if _es_sharepoint_ministerio(share_link):
        return descargar_desde_sharepoint_graph(share_link, nombre_destino)

    raise RuntimeError(
        "No se pudo descargar el archivo. La descarga pública falló y "
        "el link no es de SharePoint del Ministerio para usar autenticación."
    )


def _descargar_publico(share_link: str, nombre_destino: str) -> Path:
    """Descarga un archivo desde un link público de OneDrive/SharePoint."""
    logger.info("📥 Intentando descarga pública...")

    download_url = _convertir_link_a_descarga(share_link)
    logger.info("  URL: %s", download_url[:100] + "..." if len(download_url) > 100 else download_url)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    response = session.get(download_url, allow_redirects=True, timeout=120, stream=True)
    response.raise_for_status()

    destino = DATA_DIR / nombre_destino
    total_bytes = 0
    with open(destino, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total_bytes += len(chunk)

    logger.info("  Descargado: %s (%.1f KB)", destino.name, total_bytes / 1024)
    return destino


def _validar_es_excel(ruta: Path) -> bool:
    """Valida que el archivo sea un Excel real (no HTML de login)."""
    with open(ruta, "rb") as f:
        magic = f.read(4)
    # XLSX = PK (ZIP), XLS = D0CF11E0
    if magic[:2] == b'PK' or magic[:4] == b'\xd0\xcf\x11\xe0':
        return True
    # Si empieza con HTML, es una página de login
    with open(ruta, "rb") as f:
        inicio = f.read(500).lower()
    if b"<html" in inicio or b"<!doctype" in inicio:
        return False
    # No es Excel ni HTML — asumir desconocido
    logger.warning("  Archivo con magic bytes desconocidos: %s", magic)
    return False


def _convertir_link_a_descarga(share_link: str) -> str:
    """
    Convierte un link de compartir a URL de descarga directa.

    Para SharePoint/OneDrive for Business: agrega &download=1
    Para 1drv.ms (personal): usa la API de OneDrive shares
    """
    link = share_link.strip()

    if "1drv.ms" in link:
        encoded = base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
        return f"https://api.onedrive.com/v1.0/shares/u!{encoded}/root/content"

    if ".sharepoint.com" in link:
        # Patrón &download=1 funciona para links públicos de SharePoint/OneDrive for Business
        separator = "&" if "?" in link else "?"
        return f"{link}{separator}download=1"

    return link


# ============================================================================
# PROCESAMIENTO DE ARCHIVOS EXCEL
# ============================================================================

def leer_excel_a_dataframe(
    ruta_excel: Path,
    hoja: str = None,
    columnas_coords: dict = None,
) -> pd.DataFrame:
    """
    Lee un archivo Excel y retorna un DataFrame limpio.

    Args:
        ruta_excel:      Path al archivo .xlsx
        hoja:            Nombre de la hoja. None = primera hoja
        columnas_coords: Dict con {"latitud": "NombreCol", "longitud": "NombreCol"}
    """
    logger.info("📊 Leyendo Excel: %s", ruta_excel.name)

    try:
        # Listar hojas disponibles
        xl = pd.ExcelFile(ruta_excel)
        logger.info("  Hojas disponibles: %s", ", ".join(xl.sheet_names))

        if hoja is not None:
            if hoja not in xl.sheet_names:
                # Buscar coincidencia parcial (case-insensitive)
                matches = [s for s in xl.sheet_names if hoja.lower() in s.lower()]
                if matches:
                    hoja_real = matches[0]
                    logger.info("  Hoja '%s' no encontrada exacta, usando '%s'", hoja, hoja_real)
                    hoja = hoja_real
                else:
                    raise ValueError(
                        f"Hoja '{hoja}' no encontrada. Hojas disponibles: {xl.sheet_names}"
                    )
            df = pd.read_excel(ruta_excel, sheet_name=hoja)
            logger.info("  Hoja seleccionada: '%s'", hoja)
        else:
            df = pd.read_excel(ruta_excel)
            logger.info("  Usando primera hoja: '%s'", xl.sheet_names[0])

        logger.info("  Filas: %d | Columnas: %d", len(df), len(df.columns))
        if len(df.columns) <= 15:
            logger.info("  Columnas: %s", ", ".join(str(c) for c in df.columns))
        else:
            logger.info("  Columnas (primeras 10): %s ...", ", ".join(str(c) for c in df.columns[:10]))

        if len(df) == 0:
            raise ValueError(f"La hoja del Excel está vacía (0 filas)")

        # Limpiar nombres de columnas
        df.columns = [
            re.sub(r'\s+', '_', str(col).strip())
            for col in df.columns
        ]

        # Detectar/renombrar columnas de coordenadas
        if columnas_coords is None:
            columnas_coords = _detectar_columnas_coordenadas(df)

        if columnas_coords:
            rename_map = {}
            if "latitud" in columnas_coords:
                rename_map[columnas_coords["latitud"]] = "Latitude"
            if "longitud" in columnas_coords:
                rename_map[columnas_coords["longitud"]] = "Longitude"
            if rename_map:
                df = df.rename(columns=rename_map)
                logger.info("  Coordenadas mapeadas: %s", rename_map)

        # Timestamp
        df["FechaActualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return df

    except Exception as e:
        logger.error("❌ Error leyendo Excel: %s", e)
        raise


def _detectar_columnas_coordenadas(df: pd.DataFrame) -> dict:
    """Detecta automáticamente columnas de latitud y longitud."""
    cols_lower = {col.lower(): col for col in df.columns}

    lat_candidates = ["latitude", "latitud", "lat", "y", "coord_y", "coordenada_y"]
    lon_candidates = ["longitude", "longitud", "lon", "lng", "x", "coord_x", "coordenada_x"]

    result = {}
    for c in lat_candidates:
        if c in cols_lower:
            result["latitud"] = cols_lower[c]
            break
    for c in lon_candidates:
        if c in cols_lower:
            result["longitud"] = cols_lower[c]
            break

    return result if result else None


def dataframe_a_csv(df: pd.DataFrame, nombre: str) -> Path:
    """Convierte DataFrame a CSV en DATA_DIR."""
    nombre_csv = re.sub(r'[^\w\-_]', '_', nombre) + ".csv"
    ruta_csv = DATA_DIR / nombre_csv
    df.to_csv(ruta_csv, index=False, encoding="utf-8")
    size_kb = ruta_csv.stat().st_size / 1024
    logger.info("  CSV generado: %s (%.1f KB, %d filas)", ruta_csv.name, size_kb, len(df))
    return ruta_csv


# ============================================================================
# PUBLICACIÓN EN ARCGIS ENTERPRISE
# ============================================================================

def conectar_arcgis():
    """Conecta al portal ArcGIS Enterprise."""
    from arcgis.gis import GIS

    if not ARCGIS_USERNAME or not ARCGIS_PASSWORD:
        raise RuntimeError(
            "Credenciales de ArcGIS no configuradas. "
            "Define ARCGIS_USERNAME y ARCGIS_PASSWORD en .env"
        )

    logger.info("🔌 Conectando a ArcGIS Enterprise: %s", ARCGIS_PORTAL_URL)
    gis = GIS(url=ARCGIS_PORTAL_URL, username=ARCGIS_USERNAME, password=ARCGIS_PASSWORD, verify_cert=False)
    logger.info("  Conectado como: %s", getattr(gis.properties.user, "username", ARCGIS_USERNAME))
    return gis


def buscar_capa_existente(gis, titulo: str):
    """Busca si ya existe una capa con el título dado. Retorna Item o None."""
    for item_type in ["Feature Service", "CSV"]:
        resultados = gis.content.search(
            query=f'title:"{titulo}" AND owner:{ARCGIS_USERNAME}',
            item_type=item_type,
            max_items=5,
        )
        for item in resultados:
            if item.title == titulo:
                logger.info("  Capa existente: %s (ID: %s, tipo: %s)", item.title, item.id, item.type)
                return item
    return None


def publicar_csv_como_capa(gis, csv_path: Path, titulo: str, descripcion: str, tags: str) -> dict:
    """Publica un CSV como capa hospedada (Feature Service) en ArcGIS Enterprise."""
    logger.info("📤 Publicando CSV como capa hospedada: %s", titulo)

    item_props = {
        "title": titulo,
        "description": descripcion,
        "tags": tags,
        "type": "CSV",
    }

    csv_item = gis.content.add(item_props, data=str(csv_path))
    logger.info("  CSV subido — ID: %s", csv_item.id)

    try:
        df_check = pd.read_csv(csv_path, nrows=2)
        has_coords = "Latitude" in df_check.columns and "Longitude" in df_check.columns

        publish_params = {"type": "csv"}
        if has_coords:
            publish_params.update({
                "locationType": "coordinates",
                "latitudeFieldName": "Latitude",
                "longitudeFieldName": "Longitude",
            })

        feature_item = csv_item.publish(publish_parameters=publish_params, overwrite=False)
        logger.info("  ✅ Feature Service publicado — ID: %s", feature_item.id)

        return {
            "csv_item_id": csv_item.id,
            "feature_item_id": feature_item.id,
            "titulo": titulo,
            "url": f"{ARCGIS_PORTAL_URL}/home/item.html?id={feature_item.id}",
        }
    except Exception as e:
        logger.error("  ❌ Publicación como Feature Service falló: %s", e)
        return {
            "csv_item_id": csv_item.id,
            "feature_item_id": None,
            "titulo": titulo,
            "url": f"{ARCGIS_PORTAL_URL}/home/item.html?id={csv_item.id}",
            "nota": "CSV subido. Publicar como Feature Service manualmente desde el portal.",
        }


def actualizar_capa_existente(gis, item, csv_path: Path) -> bool:
    """Actualiza una capa existente (overwrite → truncate+append como fallback)."""
    logger.info("🔄 Actualizando: %s (ID: %s)", item.title, item.id)

    # Intentar reutilizar el script existente
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from actualizar_capa_hospedada import actualizar_capa_hospedada as _act
        return _act(
            csv_path=str(csv_path), item_id=item.id,
            portal_url=ARCGIS_PORTAL_URL, usuario=ARCGIS_USERNAME, clave=ARCGIS_PASSWORD,
        )
    except ImportError:
        pass

    tipo = (item.type or "").lower()

    if tipo == "csv":
        result = item.update(data=str(csv_path))
        if result:
            logger.info("  ✅ CSV actualizado")
            return True
        raise RuntimeError("Falló la actualización del CSV item")

    if "feature" in tipo:
        from arcgis.features import FeatureLayerCollection, Feature

        flc = FeatureLayerCollection.fromitem(item)
        try:
            resultado = flc.manager.overwrite(str(csv_path))
            logger.info("  Overwrite resultado: %s", resultado)
            return True
        except Exception as exc:
            logger.warning("  Overwrite falló: %s — intentando truncate+append", exc)

            capa = flc.layers[0] if flc.layers else (flc.tables[0] if flc.tables else None)
            if not capa:
                raise RuntimeError("Feature Service sin layers ni tables")

            capa.delete_features(where="1=1")
            df = pd.read_csv(csv_path)
            features = []
            for _, row in df.iterrows():
                attrs = row.to_dict()
                geom = None
                if "Latitude" in attrs and "Longitude" in attrs:
                    try:
                        geom = {"x": float(attrs.pop("Longitude")), "y": float(attrs.pop("Latitude")),
                                "spatialReference": {"wkid": 4326}}
                    except (ValueError, TypeError):
                        pass
                attrs.pop("OBJECTID", None)
                attrs.pop("FID", None)
                features.append(Feature(geometry=geom, attributes=attrs))

            for i in range(0, len(features), 500):
                lote = features[i:i + 500]
                result = capa.edit_features(adds=lote)
                ok = sum(1 for r in result.get("addResults", []) if r.get("success"))
                logger.info("  Lote %d-%d: %d OK", i + 1, min(i + 500, len(features)), ok)

            logger.info("  ✅ Truncate + Append completado")
            return True

    raise RuntimeError(f"Tipo no soportado: {item.type}")


# ============================================================================
# CONFIGURACIÓN DE ARCHIVOS
# ============================================================================

def cargar_configuracion() -> list:
    """Carga la configuración desde onedrive_archivos.json."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Configuración no encontrada: {CONFIG_FILE}\n"
            f"Ejecuta: python3 actualizar_desde_onedrive.py --crear-config"
        )

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    archivos = config.get("archivos", [])
    if not archivos:
        raise ValueError("No hay archivos configurados en onedrive_archivos.json")

    logger.info("📋 Configuración: %d entrada(s)", len(archivos))
    return archivos


def crear_config_ejemplo():
    """Crea archivo de configuración de ejemplo."""
    ejemplo = {
        "_comentario": "Configuración de archivos de SharePoint/OneDrive para publicar en ArcGIS Enterprise.",
        "_instrucciones": [
            "Cada entrada define un archivo Excel y qué hoja publicar como capa",
            "Un mismo archivo Excel puede tener varias entradas (una por hoja/pestaña)",
            "Luego de la primera publicación, agrega el item_id_existente para futuras actualizaciones"
        ],
        "archivos": []
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(ejemplo, f, indent=4, ensure_ascii=False)

    logger.info("✅ Configuración de ejemplo creada: %s", CONFIG_FILE)


# ============================================================================
# DETECCIÓN DE CAMBIOS (HASH MD5)
# ============================================================================

def _cargar_hashes() -> dict:
    """Carga hashes previos desde disco."""
    if HASH_CACHE_FILE.exists():
        try:
            with open(HASH_CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _guardar_hashes(hashes: dict):
    """Guarda hashes actualizados en disco."""
    with open(HASH_CACHE_FILE, "w") as f:
        json.dump(hashes, f, indent=2)


def _calcular_hash_archivo(ruta: Path) -> str:
    """Calcula MD5 del contenido de un archivo."""
    md5 = hashlib.md5()
    with open(ruta, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()


def _archivo_cambio(nombre: str, hash_actual: str, hashes: dict) -> bool:
    """
    Compara hash actual con el almacenado.
    Retorna True si el archivo cambió (o es nuevo).
    """
    hash_previo = hashes.get(nombre)
    if hash_previo is None:
        logger.info("  🆕 Archivo nuevo (sin hash previo)")
        return True
    if hash_actual != hash_previo:
        logger.info("  🔄 Archivo modificado (hash cambió)")
        logger.info("     Previo:  %s", hash_previo[:16] + "...")
        logger.info("     Actual:  %s", hash_actual[:16] + "...")
        return True
    logger.info("  ✅ Sin cambios (hash idéntico: %s...)", hash_actual[:16])
    return False


# ============================================================================
# PROCESAMIENTO PRINCIPAL
# ============================================================================

# Cache de archivos descargados (para no descargar el mismo Excel múltiples veces)
_cache_descargas = {}
# Cache de hashes de archivos descargados en esta ejecución
_cache_hashes = {}


def procesar_archivo(archivo_config: dict, gis=None, dry_run: bool = False,
                     force: bool = False, hashes: dict = None) -> dict:
    """
    Procesa un archivo individual: descarga, verifica cambios, publica.

    Si el archivo no cambió desde la última ejecución (mismo hash MD5),
    se salta la publicación para no sobrecargar ArcGIS.
    Usa --force para forzar actualización sin importar el hash.
    """
    nombre = archivo_config["nombre"]
    link = archivo_config["onedrive_link"]
    titulo = archivo_config.get("titulo_arcgis", nombre)
    descripcion = archivo_config.get("descripcion", f"Datos de {nombre}")
    tags = archivo_config.get("tags", "onedrive, MME")
    hoja = archivo_config.get("hoja_excel", None)
    coords = archivo_config.get("columnas_coordenadas", None)
    item_id = archivo_config.get("item_id_existente", None)
    if hashes is None:
        hashes = {}

    logger.info("─" * 60)
    logger.info("📂 Procesando: %s", nombre)
    if hoja:
        logger.info("   Hoja: '%s'", hoja)
    logger.info("─" * 60)

    resultado = {"nombre": nombre, "exito": False, "detalle": ""}

    try:
        # 1. Descargar (con cache para evitar descargar el mismo archivo varias veces)
        if link in _cache_descargas:
            ruta_excel = _cache_descargas[link]
            logger.info("  📁 Usando archivo ya descargado: %s", ruta_excel.name)
        else:
            nombre_archivo = re.sub(r'[^\w\-_]', '_', nombre) + ".xlsx"
            ruta_excel = descargar_archivo_onedrive(link, nombre_destino=nombre_archivo)
            _cache_descargas[link] = ruta_excel

        # 2. Verificar si el archivo cambió (hash MD5)
        #    Clave del hash: nombre + hoja (para distinguir varias hojas del mismo archivo)
        hash_key = f"{nombre}::{hoja or '__all__'}"
        if link in _cache_hashes:
            hash_actual = _cache_hashes[link]
        else:
            hash_actual = _calcular_hash_archivo(ruta_excel)
            _cache_hashes[link] = hash_actual

        cambio = _archivo_cambio(hash_key, hash_actual, hashes)

        if not cambio and not force and not dry_run:
            resultado["exito"] = True
            resultado["detalle"] = "Sin cambios — omitido"
            return resultado

        # 3. Leer hoja del Excel
        df = leer_excel_a_dataframe(ruta_excel, hoja=hoja, columnas_coords=coords)

        # 4. Convertir a CSV
        ruta_csv = dataframe_a_csv(df, nombre)

        # Actualizar hash en memoria (se guarda al final si publicación exitosa)
        hashes[hash_key] = hash_actual

        if dry_run:
            logger.info("  🔍 DRY-RUN: Descargado y convertido. No se publica.")
            logger.info("  CSV local: %s", ruta_csv)
            resultado["exito"] = True
            resultado["detalle"] = f"OK: {len(df)} filas, {len(df.columns)} columnas"
            resultado["csv_local"] = str(ruta_csv)
            return resultado

        # 5. Publicar o actualizar en ArcGIS Enterprise
        if item_id:
            item = gis.content.get(item_id)
            if item:
                actualizar_capa_existente(gis, item, ruta_csv)
                resultado.update({"exito": True, "detalle": f"Actualizada: {len(df)} filas", "item_id": item_id})
                return resultado
            else:
                logger.warning("  Item ID '%s' no encontrado. Buscando por título...", item_id)

        # Buscar por título
        item_existente = buscar_capa_existente(gis, titulo)
        if item_existente:
            actualizar_capa_existente(gis, item_existente, ruta_csv)
            resultado.update({
                "exito": True,
                "detalle": f"Actualizada: {len(df)} filas",
                "item_id": item_existente.id,
            })
        else:
            info = publicar_csv_como_capa(gis, ruta_csv, titulo, descripcion, tags)
            resultado.update({
                "exito": True,
                "detalle": f"Nueva capa: {len(df)} filas",
                "item_id": info.get("feature_item_id") or info.get("csv_item_id"),
                "url": info.get("url"),
            })

        if resultado.get("item_id"):
            logger.info('  💡 Guarda en config: "item_id_existente": "%s"', resultado["item_id"])

    except Exception as e:
        logger.error("  ❌ Error: %s", e)
        resultado["detalle"] = str(e)
        import traceback
        logger.debug(traceback.format_exc())

    return resultado


def _auto_guardar_item_ids(resultados):
    """Auto-guarda item_id_existente en el JSON de configuración tras primera publicación."""
    ids_nuevos = {r["nombre"]: r["item_id"] for r in resultados
                  if r.get("item_id") and r.get("exito")}
    if not ids_nuevos:
        return

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        cambios = 0
        for arch in data.get("archivos", []):
            nombre = arch.get("nombre", "")
            if nombre in ids_nuevos and not arch.get("item_id_existente"):
                arch["item_id_existente"] = ids_nuevos[nombre]
                cambios += 1

        if cambios > 0:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info("💾 Config actualizada: %d item_id(s) guardados en %s",
                        cambios, CONFIG_FILE.name)
    except Exception as e:
        logger.warning("⚠️  No se pudo auto-guardar item_ids: %s", e)


# ============================================================================
# CLI
# ============================================================================

def main():
    """Función principal."""
    parser = argparse.ArgumentParser(
        description="Descarga archivos Excel de SharePoint y los publica en ArcGIS Enterprise.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo descarga, no publica en ArcGIS")
    parser.add_argument("--archivo", type=int, help="Procesar solo archivo #N (1-based)")
    parser.add_argument("--listar", action="store_true", help="Listar archivos configurados")
    parser.add_argument("--crear-config", action="store_true", help="Crear config de ejemplo")
    parser.add_argument("--auth", action="store_true", help="Autenticarse interactivamente (Device Code Flow)")
    parser.add_argument("--force", action="store_true", help="Forzar actualización sin verificar cambios")
    parser.add_argument("--env-file", type=str, default=None, help="Archivo .env alternativo (ej: .env.adminportal)")
    parser.add_argument("--config-file", type=str, default=None, help="Archivo JSON de configuración alternativo")
    args = parser.parse_args()

    try:
        logger.info("=" * 70)
        logger.info("  ACTUALIZACIÓN ARCGIS ENTERPRISE DESDE SHAREPOINT/ONEDRIVE")
        logger.info("=" * 70)
        logger.info("Fecha/Hora: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("Portal:     %s", ARCGIS_PORTAL_URL)
        modo = "DRY-RUN" if args.dry_run else ("AUTH" if args.auth else ("FORZADO" if args.force else "PRODUCCIÓN (solo si hay cambios)"))
        logger.info("Modo:       %s", modo)
        logger.info("=" * 70)

        # Autenticación interactiva
        if args.auth:
            _graph_auth.auth_device_code_interactive()
            logger.info("\n✅ Autenticación completada. Ahora puedes ejecutar el script normalmente.")
            return 0

        # Crear config
        if args.crear_config:
            crear_config_ejemplo()
            return 0

        # Cargar configuración
        archivos = cargar_configuracion()
        archivos_activos = [a for a in archivos if a.get("activo", True)]
        logger.info("Archivos: %d activos de %d total", len(archivos_activos), len(archivos))

        # Listar
        if args.listar:
            for i, a in enumerate(archivos, 1):
                estado = "✅" if a.get("activo", True) else "⏸️"
                logger.info("  #%d %s %s", i, estado, a["nombre"])
                logger.info("      Título: %s | Hoja: %s", a.get("titulo_arcgis", "—"), a.get("hoja_excel", "primera"))
                logger.info("      Link: %s", a["onedrive_link"][:70] + "...")
                logger.info("      Item ID: %s", a.get("item_id_existente", "(nuevo)"))
            return 0

        # Filtrar por número
        if args.archivo:
            idx = args.archivo - 1
            if idx < 0 or idx >= len(archivos):
                logger.error("Archivo #%d no existe (hay %d)", args.archivo, len(archivos))
                return 1
            archivos_activos = [archivos[idx]]

        if not archivos_activos:
            logger.warning("No hay archivos activos.")
            return 0

        # Cargar hashes previos para detección de cambios
        hashes = _cargar_hashes()

        # Conectar ArcGIS (solo si no es dry-run)
        gis = None if args.dry_run else None  # Defer connection until needed

        # Procesar
        resultados = []
        alguno_cambio = False
        for cfg in archivos_activos:
            resultado = procesar_archivo(
                cfg, gis=gis, dry_run=args.dry_run,
                force=args.force, hashes=hashes,
            )
            # Si hay cambio real y necesitamos ArcGIS, conectar ahora
            if (resultado["detalle"] != "Sin cambios — omitido"
                    and not args.dry_run and gis is None
                    and not resultado["exito"]):
                # Means it needs ArcGIS but we haven't connected yet
                pass
            resultados.append(resultado)
            if resultado["detalle"] != "Sin cambios — omitido":
                alguno_cambio = True

        # Si hubo cambios pero no pudimos publicar porque no teníamos conexión,
        # reconectar y re-procesar los que fallaron
        if alguno_cambio and not args.dry_run:
            # Revisar si alguno necesita publicación real
            pendientes = [i for i, r in enumerate(resultados)
                          if r["detalle"] != "Sin cambios — omitido" and not r["exito"]]
            if not pendientes:
                # Todos los que cambiaron ya se procesaron, o eran nuevos
                # Re-run con conexión ArcGIS para los que tienen cambios
                pass

            # Lazy connect: re-procesar con conectado
            _cache_descargas.clear()  # Reset download cache
            _cache_hashes.clear()
            gis = conectar_arcgis()
            for i, cfg in enumerate(archivos_activos):
                if resultados[i]["detalle"] == "Sin cambios — omitido":
                    continue  # Skip unchanged
                resultados[i] = procesar_archivo(
                    cfg, gis=gis, dry_run=False,
                    force=True, hashes=hashes,
                )

        # Guardar hashes actualizados
        _guardar_hashes(hashes)
        logger.info("💾 Hashes actualizados en: %s", HASH_CACHE_FILE.name)

        # Auto-guardar item_id_existente en el JSON de config
        _auto_guardar_item_ids(resultados)

        # Resumen
        logger.info("")
        logger.info("=" * 70)
        logger.info("  RESUMEN")
        logger.info("=" * 70)

        exitosos = sum(1 for r in resultados if r["exito"])
        omitidos = sum(1 for r in resultados if r["detalle"] == "Sin cambios — omitido")
        for r in resultados:
            logger.info("  %s %s — %s", "✅" if r["exito"] else "❌", r["nombre"], r["detalle"])
            if r.get("url"):
                logger.info("     URL: %s", r["url"])
            if r.get("item_id"):
                logger.info("     Item ID: %s", r["item_id"])

        logger.info("")
        if omitidos > 0:
            logger.info("Total: %d/%d exitosos (%d sin cambios, omitidos)", exitosos, len(resultados), omitidos)
        else:
            logger.info("Total: %d/%d exitosos", exitosos, len(resultados))
        logger.info("=" * 70)

        return 0 if exitosos == len(resultados) else 1

    except KeyboardInterrupt:
        logger.warning("Interrumpido.")
        return 130
    except Exception as e:
        logger.error("ERROR CRÍTICO: %s", e)
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
