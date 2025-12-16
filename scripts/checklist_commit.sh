#!/bin/bash
# Checklist interactivo para commits seguros

cat << 'EOF'
╔══════════════════════════════════════════════════════════════════════╗
║              ✅ CHECKLIST DE COMMIT SEGURO - Dashboard MME            ║
╚══════════════════════════════════════════════════════════════════════╝

EOF

# Función para preguntar sí/no
ask() {
    while true; do
        read -p "$1 (s/n): " yn
        case $yn in
            [Ss]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Por favor responde s o n.";;
        esac
    done
}

echo "🔍 VALIDACIONES ANTES DEL COMMIT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Tests
if ask "¿Ejecutaste los tests? (python3 tests/test_metricas.py)"; then
    echo "  ✅ Tests ejecutados"
else
    echo "  ❌ EJECUTAR: python3 tests/test_metricas.py"
    exit 1
fi

# 2. Validación
if ask "¿Ejecutaste el script de validación? (./scripts/validate_deployment.sh)"; then
    echo "  ✅ Validación ejecutada"
else
    echo "  ❌ EJECUTAR: ./scripts/validate_deployment.sh"
    exit 1
fi

# 3. Revisión de conversiones
if ask "¿Verificaste que NO agregaste conversiones duplicadas en AporEner?"; then
    echo "  ✅ Sin conversiones duplicadas"
else
    echo "  ⚠️ REVISAR: grep -rn 'AporEner.*/ 1_000_000' pages/"
    exit 1
fi

# 4. Agregaciones
if ask "¿Usaste .sum() para totales y .mean() para promedios correctamente?"; then
    echo "  ✅ Agregaciones correctas"
else
    echo "  ⚠️ Revisar uso de .sum() vs .mean()"
    exit 1
fi

# 5. Fechas
if ask "¿Verificaste que buscas la última fecha con datos (no asumes 'ayer')?"; then
    echo "  ✅ Búsqueda de fechas correcta"
else
    echo "  ⚠️ Usar: buscar_ultima_fecha_disponible()"
    exit 1
fi

# 6. Logging
if ask "¿Agregaste logging con log_metricas_debug() para nuevos cálculos?"; then
    echo "  ✅ Logging agregado"
else
    echo "  ⚠️ Agregar: from utils.unit_validator import log_metricas_debug"
fi

# 7. Validación de unidades
if ask "¿Validaste las unidades con validar_unidades_energia()?"; then
    echo "  ✅ Validación de unidades"
else
    echo "  ⚠️ Agregar: validar_unidades_energia(metric_name, data)"
fi

# 8. Comparación con XM
if ask "¿Comparaste los resultados con XM para verificar corrección?"; then
    echo "  ✅ Comparado con XM"
else
    echo "  ⚠️ Verificar valores contra XM antes de commit"
    exit 1
fi

# 9. Backup
if ask "¿Creaste backup de los archivos modificados?"; then
    echo "  ✅ Backup creado"
else
    echo "  ⚠️ Crear backup con: cp archivo.py archivo.py.backup_\$(date +%Y%m%d)"
fi

# 10. Documentación
if ask "¿Actualizaste la documentación si agregaste nuevas funciones?"; then
    echo "  ✅ Documentación actualizada"
else
    echo "  ⚠️ Actualizar: PREVENCION_ERRORES.md o README_PREVENCION.md"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ CHECKLIST COMPLETO - Listo para commit"
echo ""
echo "Comandos sugeridos:"
echo "  git add ."
echo "  git commit -m \"Tu mensaje descriptivo\""
echo "  git push"
echo ""
echo "Después del push:"
echo "  ./scripts/validate_deployment.sh && sudo systemctl restart dashboard-mme.service"
echo ""
