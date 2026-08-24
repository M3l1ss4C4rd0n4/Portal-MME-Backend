#!/usr/bin/env python3
"""
Corre el golden dataset del Asistente IA (golden_dataset.py) y reporta un
resumen legible para revisión humana. Sin infraestructura de CI, sin exit
code de aprobación/rechazo — es una foto de referencia para detectar
regresiones futuras al ojo, no una barra de aprobación automática.

Reusa _get_llm_client()/_resolver_tool_calls()/SYSTEM_PROMPT de
asistente_ia_service.py — las mismas funciones internas que ya usa
responder_completo(), no reimplementa el loop de tool-calling.

Uso (correr manualmente antes de cambios de prompt/modelo):
    venv/bin/python3 scripts/asistente/run_golden_dataset.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from domain.services.asistente_ia_service import (  # noqa: E402
    SYSTEM_PROMPT,
    _get_llm_client,
    _proveedores_disponibles,
    _resolver_tool_calls,
)
from scripts.asistente.golden_dataset import PREGUNTAS  # noqa: E402


async def _ejecutar_pregunta(client, modelo: str, pregunta: str) -> tuple[str, list[str]]:
    mensajes = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": pregunta},
    ]
    tools_usadas: list[str] = []
    async for nombre_tool, _ in _resolver_tool_calls(client, mensajes, turno_id=f"golden-{int(time.time())}", modelo=modelo):
        tools_usadas.append(nombre_tool)
    resp = await client.chat.completions.create(
        model=modelo, messages=mensajes, temperature=0.3,
    )
    texto = resp.choices[0].message.content or ""
    return texto, tools_usadas


PAUSA_ENTRE_PREGUNTAS_S = 12  # Gemini free tier: 15 RPM; cada pregunta puede
# costar 2-4 llamadas (decisión de tool + posible reintento + síntesis) —
# sin pausa, el propio runner se autosatura el rate-limit (reproducido:
# corrida sin pausa falló con 429 desde la pregunta 7/13).


async def main() -> None:
    nombre_proveedor, base_url, api_key, modelo = _proveedores_disponibles()[0]
    print(f"Proveedor: {nombre_proveedor} ({modelo})\n")
    client = _get_llm_client(base_url, api_key)
    ok = 0
    for i, caso in enumerate(PREGUNTAS, start=1):
        if i > 1:
            await asyncio.sleep(PAUSA_ENTRE_PREGUNTAS_S)
        pregunta = caso["pregunta"]
        tool_esperada = caso["tool_esperada"]
        palabras_clave = caso["palabras_clave_esperadas"]

        t0 = time.perf_counter()
        try:
            texto, tools_usadas = await _ejecutar_pregunta(client, modelo, pregunta)
        except Exception as e:
            print(f"[{i}] ❌ ERROR: {pregunta}\n    excepción: {e}\n")
            continue
        duracion_s = round(time.perf_counter() - t0, 1)

        tool_ok = tool_esperada is None or tool_esperada in tools_usadas
        texto_lower = texto.lower()
        keywords_ok = all(kw.lower() in texto_lower for kw in palabras_clave)
        marca = "✅" if (tool_ok and keywords_ok) else "⚠️"
        ok += 1 if (tool_ok and keywords_ok) else 0

        print(f"[{i}] {marca} ({duracion_s}s) {pregunta}")
        print(f"    tools_usadas: {tools_usadas} (esperada: {tool_esperada})")
        if not keywords_ok:
            faltantes = [kw for kw in palabras_clave if kw.lower() not in texto_lower]
            print(f"    palabras clave faltantes: {faltantes}")
        print(f"    respuesta: {texto[:220].strip()}...")
        print()

    print(f"Resumen: {ok}/{len(PREGUNTAS)} preguntas con tool esperada + palabras clave presentes.")
    print("Nota: esto es una línea base de referencia, no una barra de aprobación — revisar manualmente los ⚠️.")


if __name__ == "__main__":
    asyncio.run(main())
