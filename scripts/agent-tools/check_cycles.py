#!/usr/bin/env python3
"""
check_cycles.py — Detección de ciclos de dependencia (estáticos y lógicos)

Uso:
    python scripts/agent-tools/check_cycles.py MODULE_A MODULE_B
    python scripts/agent-tools/check_cycles.py domain.services.generation_service domain.services.commercial_service

Detecta:
  1. Ciclo ESTÁTICO: A importa B y B importa A → ImportError
  2. Ciclo LÓGICO: Container inyecta A→B y B→A (sin ImportError)

Salida: JSON o texto plano con veredicto y recomendación.

Autor: Agent Tools — Portal Dirección MME
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

SERVER_ROOT = Path("/home/admonctrlxm/server")
CONTAINER_PATH = SERVER_ROOT / "core" / "container.py"


def detect_static_cycle(module_a: str, module_b: str) -> dict:
    """
    Intenta importar A y luego B. Si hay ImportError, hay ciclo estático.
    También verifica imports cruzados parseando el AST.
    """
    result = {"type": "static", "has_cycle": False, "evidence": []}

    # Método 1: Import runtime
    code = f"""
import sys
sys.path.insert(0, '{SERVER_ROOT}')
try:
    import {module_a}
    import {module_b}
    print("OK")
except ImportError as e:
    print(f"IMPORT_ERROR: {{e}}")
"""
    try:
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=SERVER_ROOT,
        )
        if "IMPORT_ERROR" in out.stdout:
            result["has_cycle"] = True
            result["evidence"].append(f"Runtime ImportError: {out.stdout.strip()}")
    except Exception as e:
        result["evidence"].append(f"Runtime check failed: {e}")

    # Método 2: AST parse — buscar imports cruzados
    def get_imports(module_path: str) -> set:
        path = (SERVER_ROOT / module_path.replace(".", "/")).with_suffix(".py")
        if not path.exists():
            return set()
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            return set()
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
        return imports

    imports_a = get_imports(module_a)
    imports_b = get_imports(module_b)

    # Normalizar nombres
    def normalize(name: str) -> str:
        return name.replace("_", "").replace(".", "").lower()

    norm_a = normalize(module_a)
    norm_b = normalize(module_b)

    a_imports_b = any(norm_b in normalize(imp) for imp in imports_a)
    b_imports_a = any(norm_a in normalize(imp) for imp in imports_b)

    if a_imports_b:
        result["evidence"].append(f"{module_a} imports {module_b} (AST)")
    if b_imports_a:
        result["evidence"].append(f"{module_b} imports {module_a} (AST)")

    if a_imports_b and b_imports_a:
        result["has_cycle"] = True

    return result


def detect_logical_cycle(service_a: str, service_b: str) -> dict:
    """
    Busca inyección mutua en core/container.py.
    """
    result = {"type": "logical", "has_cycle": False, "evidence": []}

    if not CONTAINER_PATH.exists():
        result["evidence"].append("core/container.py no encontrado")
        return result

    container = CONTAINER_PATH.read_text()

    # Buscar métodos de factory que creen A y B
    # Heurística: buscar "def get_X" o "def create_X" que referencien al otro
    def find_injection(source: str, target: str) -> list:
        pattern = re.compile(
            rf"def\s+(?:get_|create_)(\w*{re.escape(source)}\w*).*?:(.*?)(?=\ndef\s|\Z)",
            re.DOTALL | re.IGNORECASE,
        )
        matches = []
        for m in pattern.finditer(container):
            body = m.group(2)
            if target.lower().replace("_", "") in body.lower().replace("_", ""):
                matches.append(m.group(0).split("\n")[0].strip())
        return matches

    a_injects_b = find_injection(service_a, service_b)
    b_injects_a = find_injection(service_b, service_a)

    if a_injects_b:
        result["evidence"].extend(a_injects_b)
    if b_injects_a:
        result["evidence"].extend(b_injects_a)

    if a_injects_b and b_injects_a:
        result["has_cycle"] = True

    return result


def main():
    parser = argparse.ArgumentParser(description="Detección de ciclos de dependencia")
    parser.add_argument("module_a", help="Módulo A (ej: domain.services.generation_service)")
    parser.add_argument("module_b", help="Módulo B (ej: domain.services.commercial_service)")
    parser.add_argument("--json", action="store_true", help="Salida en JSON")
    args = parser.parse_args()

    static = detect_static_cycle(args.module_a, args.module_b)

    # Extraer nombre corto del servicio para el ciclo lógico
    short_a = args.module_a.split(".")[-1].replace("_service", "")
    short_b = args.module_b.split(".")[-1].replace("_service", "")
    logical = detect_logical_cycle(short_a, short_b)

    if args.json:
        import json
        print(json.dumps({"static": static, "logical": logical}, indent=2))
        return

    print(f"═" * 60)
    print(f"  CHECK CYCLES: {args.module_a}  ⟷  {args.module_b}")
    print(f"═" * 60)
    print()

    print("═══ CICLO ESTÁTICO (Import Cycle) ═══")
    if static["has_cycle"]:
        print("🚨 CICLO ESTÁTICO DETECTADO")
        for ev in static["evidence"]:
            print(f"   • {ev}")
        print()
        print("Tratamiento: Extraer dependencia compartida a tercer módulo.")
    else:
        print("✅ Sin ciclo estático")
        if static["evidence"]:
            for ev in static["evidence"]:
                print(f"   ℹ {ev}")
    print()

    print("═══ CICLO LÓGICO (DI Cycle) ═══")
    if logical["has_cycle"]:
        print("🚨 CICLO LÓGICO DETECTADO")
        for ev in logical["evidence"]:
            print(f"   • {ev}")
        print()
        print("Tratamiento: Dependency Inversion en el lado más débil del ciclo.")
        print("  1. Crear interfaz minimal (ABC)")
        print("  2. Hacer que el servicio concreto implemente la interfaz")
        print("  3. Hacer que el otro servicio dependa de la interfaz")
        print("  4. Actualizar Container para inyectar implementación concreta")
    else:
        print("✅ Sin ciclo lógico")
        if logical["evidence"]:
            for ev in logical["evidence"]:
                print(f"   ℹ {ev}")
    print()

    # Veredicto final
    if static["has_cycle"] or logical["has_cycle"]:
        print("═" * 60)
        print("  VEREDICTO: ❌ NO extraer módulos hasta romper ciclos")
        print("═" * 60)
        sys.exit(1)
    else:
        print("═" * 60)
        print("  VEREDICTO: ✅ OK para extraer/refactorizar")
        print("═" * 60)


if __name__ == "__main__":
    main()
