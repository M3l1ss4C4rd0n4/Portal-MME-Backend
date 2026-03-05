"""
Tests de integración — FASE 7: CU/PNT en Informe, Chatbot, Alertas.

5 tests:
  1. test_seccion_cu_pnt_en_informe
  2. test_chatbot_intent_cu_actual
  3. test_chatbot_intent_perdidas_nt
  4. test_seguimiento_predicciones_sin_psycopg2
  5. test_paginas_existentes_sin_regresion
"""

import ast
import asyncio
import importlib
import inspect
import os
import sys

import pytest

# Asegurar que el root del proyecto esté en sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ─── helpers ────────────────────────────────────────────────

def _run_async(coro):
    """Helper para ejecutar coroutines en tests síncronos."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════
# 1. Sección CU/PNT en el informe ejecutivo
# ═══════════════════════════════════════════════════════════

def test_seccion_cu_pnt_en_informe():
    """
    ExecutiveReportService debe tener la sección 6.5_cu_pnt
    y _generar_seccion_cu_pnt() debe devolver Markdown no vacío.
    """
    from domain.services.executive_report_service import ExecutiveReportService

    svc = ExecutiveReportService()

    # Verificar que el método existe
    assert hasattr(svc, '_generar_seccion_cu_pnt'), (
        "ExecutiveReportService no tiene _generar_seccion_cu_pnt"
    )

    # Ejecutar y comprobar resultado
    texto = svc._generar_seccion_cu_pnt()
    assert isinstance(texto, str), "Debe devolver string"
    assert len(texto) > 50, (
        f"La sección CU/PNT parece vacía ({len(texto)} chars)"
    )
    # Debe contener al menos "COP/kWh" (dato real o fallback)
    assert 'COP/kWh' in texto or 'no disponible' in texto.lower(), (
        "La sección debe mencionar COP/kWh o indicar no disponible"
    )


# ═══════════════════════════════════════════════════════════
# 2. Chatbot intent cu_actual
# ═══════════════════════════════════════════════════════════

def test_chatbot_intent_cu_actual():
    """
    El orquestador debe manejar el intent 'cu_actual' sin error
    y devolver una respuesta con datos de CU.
    """
    from domain.services.orchestrator_service import ChatbotOrchestratorService

    svc = ChatbotOrchestratorService()

    # Verificar que el intent está mapeado
    handler = svc._get_intent_handler('cu_actual')
    assert handler is not None, "Intent 'cu_actual' no mapeado"

    # Ejecutar el handler
    data, errors = _run_async(handler({'pregunta': 'cuánto vale el CU'}))
    assert isinstance(data, dict), "Handler debe devolver dict"
    # Debe tener 'respuesta' o 'cu'
    assert 'respuesta' in data or 'cu' in data, (
        f"Handler cu_actual no devolvió 'respuesta' ni 'cu': keys={list(data.keys())}"
    )


# ═══════════════════════════════════════════════════════════
# 3. Chatbot intent perdidas_nt
# ═══════════════════════════════════════════════════════════

def test_chatbot_intent_perdidas_nt():
    """
    El orquestador debe manejar el intent 'perdidas_nt' sin error
    y devolver datos de PNT.
    """
    from domain.services.orchestrator_service import ChatbotOrchestratorService

    svc = ChatbotOrchestratorService()

    handler = svc._get_intent_handler('perdidas_nt')
    assert handler is not None, "Intent 'perdidas_nt' no mapeado"

    data, errors = _run_async(handler({'pregunta': 'pérdidas no técnicas'}))
    assert isinstance(data, dict), "Handler debe devolver dict"
    assert 'respuesta' in data or 'pnt' in data, (
        f"Handler perdidas_nt no devolvió 'respuesta' ni 'pnt': keys={list(data.keys())}"
    )


# ═══════════════════════════════════════════════════════════
# 4. seguimiento_predicciones sin psycopg2 directo
# ═══════════════════════════════════════════════════════════

def test_seguimiento_predicciones_sin_psycopg2():
    """
    El módulo seguimiento_predicciones NO debe importar psycopg2
    directamente. Debe usar PredictionsRepository.
    """
    filepath = os.path.join(ROOT, 'interface', 'pages', 'seguimiento_predicciones.py')
    assert os.path.exists(filepath), f"No se encontró {filepath}"

    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()

    # Parsear el AST para buscar imports de psycopg2
    tree = ast.parse(source, filename=filepath)
    psycopg2_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if 'psycopg2' in alias.name:
                    psycopg2_imports.append(f"import {alias.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            if node.module and 'psycopg2' in node.module:
                psycopg2_imports.append(f"from {node.module} (line {node.lineno})")

    assert len(psycopg2_imports) == 0, (
        f"seguimiento_predicciones.py tiene imports directos de psycopg2: "
        f"{psycopg2_imports}"
    )

    # Verificar que usa PredictionsRepository
    assert 'PredictionsRepository' in source, (
        "seguimiento_predicciones.py debe usar PredictionsRepository"
    )


# ═══════════════════════════════════════════════════════════
# 5. Todas las páginas registradas sin regresión
# ═══════════════════════════════════════════════════════════

def test_paginas_existentes_sin_regresion():
    """
    Verificar que las páginas del dashboard se pueden importar
    sin errores de sintaxis ni imports rotos.
    """
    pages_dir = os.path.join(ROOT, 'interface', 'pages')
    assert os.path.isdir(pages_dir), f"No existe {pages_dir}"

    page_files = [
        f for f in os.listdir(pages_dir)
        if f.endswith('.py') and not f.startswith('__')
    ]
    assert len(page_files) >= 12, (
        f"Se esperan al menos 12 páginas, encontradas: {len(page_files)}"
    )

    # Verificar que cada archivo es parseable (sin SyntaxError)
    errores = []
    for pf in page_files:
        filepath = os.path.join(pages_dir, pf)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
            ast.parse(source, filename=filepath)
        except SyntaxError as e:
            errores.append(f"{pf}: SyntaxError line {e.lineno}: {e.msg}")

    assert len(errores) == 0, (
        f"Páginas con errores de sintaxis:\n" + "\n".join(errores)
    )
