"""
Validadores de rangos para métricas energéticas de Colombia
Asegura que los valores mostrados en el dashboard sean técnicamente razonables
"""
import logging

logger = logging.getLogger(__name__)


class MetricValidators:
    """
    Rangos razonables para métricas del sector eléctrico colombiano.
    
    Basado en valores históricos y características del sistema:
    - Colombia: ~70% hidráulica, 30% térmica
    - Demanda pico: ~10-11 GW
    - Capacidad instalada: ~18 GW
    """
    
    RANGES = {
        # ========================================
        # PRECIOS ($/kWh)
        # ========================================
        'PrecBolsNaci': (50, 400),      # Precio Bolsa Nacional
        'PrecEsca': (200, 900),          # Precio Escasez (aumenta en Fenómeno del Niño)
        'PrecEscaSup': (200, 900),       # Precio Escasez Superior
        'PrecEscaInf': (200, 900),       # Precio Escasez Inferior
        'PrecEscaAct': (200, 900),       # Precio Escasez Activación
        
        # ========================================
        # HIDROLOGÍA (%)
        # ========================================
        'AportesHidricos': (20, 250),    # % vs media histórica (20% en Niño extremo, 250% en Niña fuerte)
        'ReservasHidricas': (30, 100),   # % de capacidad útil de embalses
        
        # ========================================
        # GENERACIÓN/DEMANDA (GWh/día)
        # ========================================
        'GeneracionSIN': (150, 300),     # Generación total del SIN
        'DemandaNacional': (150, 250),   # Demanda comercial de energía
        'DNA': (150, 250),               # Demanda No Atendida (sinónimo de DemandaNacional)
        
        # ========================================
        # RESTRICCIONES (millones COP)
        # ========================================
        'Restricciones': (0, 15000),     # Costo total de restricciones operativas
        'RestAliv': (0, 10000),          # Restricciones aliviadas
        'RestSinAliv': (0, 10000),       # Restricciones no aliviadas
        
        # ========================================
        # TRANSMISIÓN (GWh)
        # ========================================
        'PerdidasTransmision': (0, 50),  # Pérdidas en transmisión
        
        # ========================================
        # COMERCIALIZACIÓN
        # ========================================
        'MercadoRegulado': (0, 100),     # Energía mercado regulado (GWh)
        'MercadoNoRegulado': (0, 100),   # Energía mercado no regulado (GWh)
    }
    
    @classmethod
    def validate(cls, metric_name: str, value: float, log_warning: bool = True) -> bool:
        """
        Valida si un valor está dentro de un rango razonable.
        
        Args:
            metric_name: Nombre de la métrica (ej: 'AportesHidricos')
            value: Valor numérico a validar
            log_warning: Si True, registra advertencia cuando está fuera de rango
            
        Returns:
            True si el valor está en rango razonable, False en caso contrario
            
        Example:
            >>> MetricValidators.validate('AportesHidricos', 65.5)
            True
            >>> MetricValidators.validate('AportesHidricos', 200)
            ⚠️ AportesHidricos=200.00 FUERA DE RANGO [30, 150]
            False
        """
        if metric_name not in cls.RANGES:
            # Sin validación definida, aceptar cualquier valor
            return True
        
        min_val, max_val = cls.RANGES[metric_name]
        is_valid = min_val <= value <= max_val
        
        if not is_valid and log_warning:
            logger.warning(
                f"⚠️ {metric_name}={value:.2f} FUERA DE RANGO [{min_val}, {max_val}]. "
                f"Verifique datos fuente o lógica de cálculo."
            )
        
        return is_valid
    
    @classmethod
    def validate_or_none(cls, metric_name: str, value: float) -> float:
        """
        Valida un valor y lo retorna si es válido, o None si está fuera de rango.
        
        Útil para rechazar datos claramente incorrectos en cálculos críticos.
        
        Args:
            metric_name: Nombre de la métrica
            value: Valor a validar
            
        Returns:
            El valor original si es válido, None si está fuera de rango
            
        Example:
            >>> aportes = MetricValidators.validate_or_none('AportesHidricos', 65.5)
            >>> print(aportes)  # 65.5
            
            >>> aportes = MetricValidators.validate_or_none('AportesHidricos', 300)
            >>> print(aportes)  # None
        """
        is_valid = cls.validate(metric_name, value, log_warning=True)
        return value if is_valid else None
    
    @classmethod
    def get_range(cls, metric_name: str) -> tuple:
        """
        Obtiene el rango válido para una métrica.
        
        Args:
            metric_name: Nombre de la métrica
            
        Returns:
            Tupla (min, max) o None si no hay rango definido
        """
        return cls.RANGES.get(metric_name)
    
    @classmethod
    def validate_percentage(cls, value: float, allow_zero: bool = False) -> bool:
        """
        Validación específica para porcentajes (0-100%).
        
        Args:
            value: Porcentaje a validar
            allow_zero: Si permite exactamente 0%
            
        Returns:
            True si está en rango [0, 100] o [>0, 100] según allow_zero
        """
        min_val = 0 if allow_zero else 0.01
        is_valid = min_val <= value <= 100
        
        if not is_valid:
            logger.warning(f"⚠️ Porcentaje inválido: {value}%")
        
        return is_valid


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def safe_division(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    División segura que evita divisiones por cero.
    
    Args:
        numerator: Numerador
        denominator: Denominador
        default: Valor a retornar si denominator es 0
        
    Returns:
        numerator/denominator o default si denominator es 0
    """
    if denominator == 0 or denominator is None:
        logger.warning(f"⚠️ División por cero evitada (numerador={numerator})")
        return default
    
    return numerator / denominator


def validate_date_range(start_date: str, end_date: str) -> bool:
    """
    Valida que un rango de fechas sea lógico.
    
    Args:
        start_date: Fecha inicio (YYYY-MM-DD)
        end_date: Fecha fin (YYYY-MM-DD)
        
    Returns:
        True si end_date >= start_date
    """
    from datetime import datetime
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        if end < start:
            logger.error(f"❌ Rango de fechas inválido: {start_date} > {end_date}")
            return False
        
        return True
        
    except ValueError as e:
        logger.error(f"❌ Formato de fecha inválido: {e}")
        return False


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    # Configurar logging para pruebas
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(message)s'
    )
    
    print("=== PRUEBAS DE VALIDADORES ===\n")
    
    # Test 1: Aportes válidos
    print("1. Aportes hídricos válidos:")
    assert MetricValidators.validate('AportesHidricos', 65.5) == True
    print("   ✅ 65.5% aceptado\n")
    
    # Test 2: Aportes inválidos
    print("2. Aportes hídricos inválidos:")
    assert MetricValidators.validate('AportesHidricos', 200) == False
    print("   ✅ 200% rechazado correctamente\n")
    
    # Test 3: Precio válido
    print("3. Precio bolsa válido:")
    assert MetricValidators.validate('PrecBolsNaci', 180) == True
    print("   ✅ $180/kWh aceptado\n")
    
    # Test 4: Validate or none
    print("4. Validate or none:")
    valid = MetricValidators.validate_or_none('AportesHidricos', 70)
    invalid = MetricValidators.validate_or_none('AportesHidricos', 300)
    assert valid == 70 and invalid is None
    print("   ✅ Funcionando correctamente\n")
    
    # Test 5: División segura
    print("5. División segura:")
    result = safe_division(100, 0, default=0)
    assert result == 0
    print("   ✅ División por cero evitada\n")
    
    print("=== ✅ TODAS LAS PRUEBAS PASARON ===")
