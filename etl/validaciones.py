"""
╔══════════════════════════════════════════════════════════════╗
║           VALIDACIONES CENTRALIZADAS - ETL XM                ║
║                                                              ║
║  Validador de datos para garantizar calidad y consistencia  ║
║  Creado: 2025-11-20 (después del incidente de datos inventados)
╚══════════════════════════════════════════════════════════════╝
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class ValidadorDatos:
    """Validador centralizado para datos del ETL"""
    
    # Umbrales de validación por métrica
    UMBRALES = {
        'DemaCome': {
            'min': 0,
            'max': 100,  # GWh - demanda máxima esperada
            'required': True
        },
        'Gene': {
            'min': 0,
            'max': 500,  # GWh - generación máxima histórica
            'required': True
        },
        'AporEner': {
            'min': 0,
            'max': 1000,  # GWh - aportes máximos en temporada de lluvias
            'required': True
        },
        'VoluUtilDiarEner': {
            'min': 0,
            'max': 20000,  # GWh - capacidad máxima del SIN
            'required': True
        },
        'CapaUtilDiarEner': {
            'min': 0,
            'max': 100,  # % - capacidad útil
            'required': True
        },
        'PreciEscaComer': {
            'min': 0,
            'max': 2000,  # COP/kWh - precio máximo histórico
            'required': False
        }
    }
    
    # Recursos válidos conocidos
    RECURSOS_VALIDOS = {
        '_SISTEMA_',  # Sistema eléctrico nacional
        'Sistema',    # Variante (será normalizada)
        'SISTEMA'     # Variante (será normalizada)
    }
    
    def __init__(self):
        self.errores = []
        self.advertencias = []
        self.estadisticas = {
            'registros_validados': 0,
            'errores_criticos': 0,
            'advertencias': 0,
            'normalizaciones': 0
        }
    
    def validar_fecha(self, fecha: datetime, metrica: str) -> Tuple[bool, Optional[str]]:
        """
        Valida que una fecha sea razonable
        
        Returns:
            (es_valida, mensaje_error)
        """
        hoy = datetime.now()
        
        # No permitir fechas futuras (máximo mañana)
        if fecha > hoy + timedelta(days=1):
            return False, f"❌ Fecha futura detectada: {fecha.date()} (métrica: {metrica})"
        
        # No permitir fechas muy antiguas (antes de 2015)
        if fecha < datetime(2015, 1, 1):
            return False, f"❌ Fecha demasiado antigua: {fecha.date()} (métrica: {metrica})"
        
        return True, None
    
    def validar_valor(self, valor: float, metrica: str, recurso: str = None) -> Tuple[bool, Optional[str]]:
        """
        Valida que un valor numérico esté dentro de rangos esperados
        
        Returns:
            (es_valido, mensaje_error)
        """
        # Verificar que no sea NaN o infinito
        if pd.isna(valor) or valor == float('inf') or valor == float('-inf'):
            return False, f"❌ Valor inválido: {valor} (métrica: {metrica}, recurso: {recurso})"
        
        # Buscar umbral para esta métrica
        umbral = None
        for metrica_key, config in self.UMBRALES.items():
            if metrica_key in metrica:
                umbral = config
                break
        
        if not umbral:
            # Si no hay umbral definido, solo verificar que sea positivo
            if valor < 0:
                return False, f"❌ Valor negativo no esperado: {valor} (métrica: {metrica})"
            return True, None
        
        # Validar contra umbrales
        if valor < umbral['min']:
            return False, f"❌ Valor {valor} < mínimo {umbral['min']} (métrica: {metrica}, recurso: {recurso})"
        
        if valor > umbral['max']:
            self.advertencias.append(
                f"⚠️ Valor {valor} > máximo {umbral['max']} (métrica: {metrica}, recurso: {recurso}) - revisar si es anómalo"
            )
            self.estadisticas['advertencias'] += 1
        
        return True, None
    
    def normalizar_recurso(self, recurso: str) -> str:
        """
        Normaliza el campo 'recurso' para evitar duplicados
        
        Todas las variantes de 'Sistema' se normalizan a 'Sistema'
        """
        if not recurso:
            return recurso
        
        recurso_limpio = recurso.strip()
        
        # Normalizar 'sistema', '_SISTEMA_' y variantes → 'Sistema'
        if recurso_limpio.lower() in ('sistema', '_sistema_'):
            self.estadisticas['normalizaciones'] += 1
            return 'Sistema'
        
        return recurso_limpio
    
    def validar_registro(
        self, 
        fecha: datetime, 
        metrica: str, 
        recurso: str, 
        valor: float
    ) -> Tuple[bool, List[str]]:
        """
        Valida un registro completo
        
        Returns:
            (es_valido, lista_de_errores)
        """
        self.estadisticas['registros_validados'] += 1
        errores = []
        
        # Validar fecha
        fecha_valida, error_fecha = self.validar_fecha(fecha, metrica)
        if not fecha_valida:
            errores.append(error_fecha)
            self.estadisticas['errores_criticos'] += 1
        
        # Validar valor
        valor_valido, error_valor = self.validar_valor(valor, metrica, recurso)
        if not valor_valido:
            errores.append(error_valor)
            self.estadisticas['errores_criticos'] += 1
        
        return len(errores) == 0, errores
    
    def validar_dataframe(self, df: pd.DataFrame, metrica: str) -> Tuple[pd.DataFrame, List[str]]:
        """
        Valida y limpia un DataFrame completo
        
        Returns:
            (df_limpio, lista_de_errores)
        """
        errores_criticos = []
        df_limpio = df.copy()
        
        # Normalizar recurso si existe la columna
        if 'recurso' in df_limpio.columns:
            df_limpio['recurso'] = df_limpio['recurso'].apply(self.normalizar_recurso)
        
        # Validar cada registro
        indices_invalidos = []
        for idx, row in df_limpio.iterrows():
            fecha = row.get('fecha')
            valor = row.get('valor_gwh') or row.get('valor')
            recurso = row.get('recurso', 'N/A')
            
            if fecha and valor is not None:
                es_valido, errores = self.validar_registro(fecha, metrica, recurso, valor)
                if not es_valido:
                    errores_criticos.extend(errores)
                    indices_invalidos.append(idx)
        
        # Eliminar registros inválidos
        if indices_invalidos:
            logger.warning(f"❌ Eliminando {len(indices_invalidos)} registros inválidos de {metrica}")
            df_limpio = df_limpio.drop(indices_invalidos)
        
        return df_limpio, errores_criticos
    
    def obtener_reporte(self) -> str:
        """Genera un reporte de validación"""
        reporte = [
            "\n" + "="*60,
            "📊 REPORTE DE VALIDACIÓN",
            "="*60,
            f"✅ Registros validados: {self.estadisticas['registros_validados']}",
            f"❌ Errores críticos: {self.estadisticas['errores_criticos']}",
            f"⚠️  Advertencias: {self.estadisticas['advertencias']}",
            f"🔄 Normalizaciones: {self.estadisticas['normalizaciones']}",
        ]
        
        if self.errores:
            reporte.append("\n🔴 ERRORES CRÍTICOS:")
            for error in self.errores[:10]:  # Mostrar máximo 10
                reporte.append(f"  - {error}")
            if len(self.errores) > 10:
                reporte.append(f"  ... y {len(self.errores) - 10} más")
        
        if self.advertencias:
            reporte.append("\n🟡 ADVERTENCIAS:")
            for adv in self.advertencias[:10]:  # Mostrar máximo 10
                reporte.append(f"  - {adv}")
            if len(self.advertencias) > 10:
                reporte.append(f"  ... y {len(self.advertencias) - 10} más")
        
        reporte.append("="*60)
        return "\n".join(reporte)


# Funciones de utilidad para uso directo
def validar_fecha_futura(fecha: datetime, max_dias_futuros: int = 1) -> bool:
    """Verifica que una fecha no sea futura (con margen de 1 día)"""
    return fecha <= datetime.now() + timedelta(days=max_dias_futuros)


def validar_rango_valores(df: pd.DataFrame, columna: str, min_val: float, max_val: float) -> pd.DataFrame:
    """Filtra un DataFrame para mantener solo valores dentro de rango"""
    return df[(df[columna] >= min_val) & (df[columna] <= max_val)]


def detectar_duplicados(df: pd.DataFrame, columnas_clave: List[str]) -> pd.DataFrame:
    """
    Detecta duplicados basados en columnas clave
    
    Returns:
        DataFrame con solo los registros duplicados
    """
    return df[df.duplicated(subset=columnas_clave, keep=False)]


def eliminar_duplicados(df: pd.DataFrame, columnas_clave: List[str], estrategia: str = 'last') -> pd.DataFrame:
    """
    Elimina duplicados manteniendo según estrategia
    
    Args:
        estrategia: 'first' (mantener primero), 'last' (mantener último), 'max' (mantener valor máximo)
    """
    if estrategia in ['first', 'last']:
        return df.drop_duplicates(subset=columnas_clave, keep=estrategia)
    elif estrategia == 'max':
        # Mantener el registro con valor máximo
        return df.loc[df.groupby(columnas_clave)['valor_gwh'].idxmax()]
    else:
        raise ValueError(f"Estrategia desconocida: {estrategia}")
