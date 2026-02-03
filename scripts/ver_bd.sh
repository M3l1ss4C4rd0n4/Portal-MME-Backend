#!/bin/bash
################################################################################
# ACCESO RÁPIDO A BASE DE DATOS PostgreSQL - Portal Energético MME
################################################################################
# Uso: bash scripts/ver_bd.sh
################################################################################

cd /home/admonctrlxm/server

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    BASE DE DATOS POSTGRESQL - Portal MME                    ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Explorador interactivo Python
python3 scripts/db_explorer.py
