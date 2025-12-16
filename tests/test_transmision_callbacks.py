#!/usr/bin/env python3
"""
Test simple para verificar que los callbacks de transmisión funcionan
"""
import requests
import json

BASE_URL = "http://localhost:8050"

print("=" * 60)
print("TEST DE CALLBACKS DE TRANSMISIÓN")
print("=" * 60)

# Test 1: Verificar que el servidor responde
print("\n1. Probando servidor...")
response = requests.get(BASE_URL)
print(f"   Status: {response.status_code}")
assert response.status_code == 200, "Servidor no responde"
print("   ✓ Servidor OK")

# Test 2: Verificar página de transmisión
print("\n2. Probando página de transmisión...")
response = requests.get(f"{BASE_URL}/transmision")
print(f"   Status: {response.status_code}")
assert response.status_code == 200, "Página transmisión no responde"
assert "react-entry-point" in response.text, "React no se está cargando"
print("   ✓ Página carga OK")

# Test 3: Callback de recursos
print("\n3. Probando callback de recursos...")
payload = {
    "output": "recurso-dropdown.options",
    "outputs": {"id": "recurso-dropdown", "property": "options"},
    "inputs": [{"id": "tipo-disponibilidad-dropdown", "property": "value", "value": "DispoDeclarada"}],
    "changedPropIds": ["tipo-disponibilidad-dropdown.value"],
    "state": []
}
response = requests.post(
    f"{BASE_URL}/_dash-update-component",
    json=payload,
    headers={"Content-Type": "application/json"}
)
print(f"   Status: {response.status_code}")
assert response.status_code == 200, f"Callback falló: {response.text}"
data = response.json()
recursos = data['response']['recurso-dropdown']['options']
print(f"   ✓ {len(recursos)} recursos devueltos")
print(f"   Primeros 5: {[r['label'] for r in recursos[:5]]}")

# Test 4: Callback de KPIs
print("\n4. Probando callback de KPIs...")
payload = {
    "output": "kpis-transmision.children",
    "outputs": {"id": "kpis-transmision", "property": "children"},
    "inputs": [
        {"id": "tipo-disponibilidad-dropdown", "property": "value", "value": "DispoDeclarada"},
        {"id": "periodo-dropdown", "property": "value", "value": 30}
    ],
    "changedPropIds": [],
    "state": []
}
response = requests.post(
    f"{BASE_URL}/_dash-update-component",
    json=payload,
    headers={"Content-Type": "application/json"}
)
print(f"   Status: {response.status_code}")
assert response.status_code == 200, f"Callback falló: {response.text}"
print("   ✓ KPIs se generan correctamente")

# Test 5: Callback de gráfico tendencia
print("\n5. Probando callback de gráfico tendencia...")
payload = {
    "output": "grafico-tendencia.figure",
    "outputs": {"id": "grafico-tendencia", "property": "figure"},
    "inputs": [
        {"id": "tipo-disponibilidad-dropdown", "property": "value", "value": "DispoReal"},
        {"id": "periodo-dropdown", "property": "value", "value": 7}
    ],
    "changedPropIds": [],
    "state": []
}
response = requests.post(
    f"{BASE_URL}/_dash-update-component",
    json=payload,
    headers={"Content-Type": "application/json"}
)
print(f"   Status: {response.status_code}")
assert response.status_code == 200, f"Callback falló: {response.text}"
figure = response.json()['response']['grafico-tendencia']['figure']
print(f"   ✓ Gráfico generado con {len(figure.get('data', []))} trazas")

print("\n" + "=" * 60)
print("✓✓✓ TODOS LOS TESTS PASARON ✓✓✓")
print("=" * 60)
print("\nSi ves este mensaje, el backend funciona correctamente.")
print("El problema puede ser:")
print("  1. Caché del navegador (presiona Ctrl+Shift+R)")
print("  2. Extensiones del navegador bloqueando JavaScript")
print("  3. Consola del navegador tiene errores (F12 -> Console)")
