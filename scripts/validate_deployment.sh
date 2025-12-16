#!/bin/bash
# Script de validación pre-deployment
# Ejecutar antes de reiniciar el dashboard en producción

echo "======================================================================"
echo "🔍 VALIDACIÓN PRE-DEPLOYMENT - Dashboard MME"
echo "======================================================================"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Contador de errores
ERRORS=0

# 1. Verificar sintaxis Python
echo -e "\n${YELLOW}[1/5]${NC} Verificando sintaxis Python..."
python3 -m py_compile pages/generacion.py 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Sintaxis correcta en generacion.py${NC}"
else
    echo -e "${RED}❌ Error de sintaxis en generacion.py${NC}"
    ERRORS=$((ERRORS + 1))
fi

python3 -m py_compile pages/generacion_hidraulica_hidrologia.py 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Sintaxis correcta en generacion_hidraulica_hidrologia.py${NC}"
else
    echo -e "${RED}❌ Error de sintaxis en generacion_hidraulica_hidrologia.py${NC}"
    ERRORS=$((ERRORS + 1))
fi

# 2. Ejecutar tests automatizados
echo -e "\n${YELLOW}[2/5]${NC} Ejecutando tests automatizados..."
python3 tests/test_metricas.py > /tmp/test_results.txt 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Todos los tests pasaron${NC}"
    grep "RESULTADOS:" /tmp/test_results.txt
else
    echo -e "${RED}❌ Algunos tests fallaron${NC}"
    cat /tmp/test_results.txt | tail -20
    ERRORS=$((ERRORS + 1))
fi

# 3. Verificar que no haya conversiones duplicadas en métricas críticas
echo -e "\n${YELLOW}[3/5]${NC} Buscando conversiones duplicadas en métricas críticas..."
# Solo verificar AporEner y AporEnerMediHist que YA vienen convertidos
DUPLICADAS=$(grep -rn "AporEner.*/ 1_000_000\|AporEner.*/ 1e6" pages/generacion*.py | grep -v "#" | wc -l)
if [ $DUPLICADAS -eq 0 ]; then
    echo -e "${GREEN}✅ No se encontraron conversiones duplicadas en AporEner${NC}"
else
    echo -e "${RED}❌ Se encontraron $DUPLICADAS conversiones duplicadas en AporEner:${NC}"
    grep -rn "AporEner.*/ 1_000_000\|AporEner.*/ 1e6" pages/generacion*.py | grep -v "#"
    ERRORS=$((ERRORS + 1))
fi

# 4. Verificar uso de .mean() vs .sum() en contextos críticos
echo -e "\n${YELLOW}[4/5]${NC} Verificando uso correcto de agregaciones..."
# Buscar patrones sospechosos: "total" con .mean() o "promedio" con .sum()
SUSPICIOUS=$(grep -rn "total.*\.mean()\|promedio.*\.sum()" pages/*.py | grep -v "#" | wc -l)
if [ $SUSPICIOUS -eq 0 ]; then
    echo -e "${GREEN}✅ No se encontraron agregaciones sospechosas${NC}"
else
    echo -e "${YELLOW}⚠️ Se encontraron $SUSPICIOUS posibles agregaciones incorrectas:${NC}"
    grep -rn "total.*\.mean()\|promedio.*\.sum()" pages/*.py | grep -v "#"
    echo -e "${YELLOW}   Revisar manualmente si son correctas${NC}"
fi

# 5. Verificar que existan backups
echo -e "\n${YELLOW}[5/5]${NC} Verificando backups..."
if [ -f "pages/generacion.py.backup" ] || [ -f "pages/generacion_hidraulica_hidrologia.py.backup" ]; then
    echo -e "${GREEN}✅ Backups encontrados${NC}"
else
    echo -e "${YELLOW}⚠️ No se encontraron backups recientes${NC}"
    echo -e "${YELLOW}   Creando backups...${NC}"
    cp pages/generacion.py pages/generacion.py.backup_$(date +%Y%m%d_%H%M%S)
    cp pages/generacion_hidraulica_hidrologia.py pages/generacion_hidraulica_hidrologia.py.backup_$(date +%Y%m%d_%H%M%S)
fi

# Resumen
echo -e "\n======================================================================"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ VALIDACIÓN EXITOSA - Listo para deployment${NC}"
    echo -e "======================================================================"
    exit 0
else
    echo -e "${RED}❌ VALIDACIÓN FALLIDA - $ERRORS errores encontrados${NC}"
    echo -e "${RED}   NO PROCEDER CON DEPLOYMENT${NC}"
    echo -e "======================================================================"
    exit 1
fi
