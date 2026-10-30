"""Serializa el informe a JSON y lo vuelve a leer.

Existe por una razón concreta: la tarea que genera (viernes 07:00) y la que
envía (viernes 08:00) son distintas a propósito, y la que envía necesita los
mismos números que quedaron impresos en el PDF para armar el cuerpo del correo.

Las alternativas eran peores. Volver a llamar a los endpoints al enviar dejaría
el correo y su PDF adjunto con cifras distintas si un tablero se movió en esa
hora — y un informe que se contradice a sí mismo es peor que uno viejo. Leer
los números del snapshot perdería etiquetas, secciones y gráficas.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from domain.services.informe_de_modelo import Informe, Kpi, Punto, Seccion, Serie


def a_json(informe: Informe) -> str:
    return json.dumps(asdict(informe), ensure_ascii=False, indent=1)


def desde_json(texto: str) -> Informe:
    crudo = json.loads(texto)
    return Informe(
        fecha=crudo["fecha"],
        generado_en=crudo["generado_en"],
        secciones=tuple(_seccion(s) for s in crudo["secciones"]),
    )


def _seccion(crudo: dict) -> Seccion:
    # Se arma campo a campo en vez de con **crudo: así un JSON de una versión
    # anterior, sin un campo que se añadió después, se lee igual en vez de
    # reventar con TypeError justo en la tarea que manda los correos.
    return Seccion(
        clave=crudo["clave"],
        titulo=crudo["titulo"],
        subtitulo=crudo.get("subtitulo", ""),
        corte=crudo.get("corte", ""),
        kpis=tuple(Kpi(**k) for k in crudo.get("kpis", ())),
        titulo_corto=crudo.get("titulo_corto", ""),
        series=tuple(_serie(s) for s in crudo.get("series", ())),
        lectura=crudo.get("lectura", ""),
        tableros=tuple(crudo.get("tableros", ())),
        error=crudo.get("error", ""),
    )


def _serie(crudo: dict) -> Serie:
    return Serie(
        clave=crudo["clave"],
        titulo=crudo["titulo"],
        tipo=crudo["tipo"],
        puntos=tuple(Punto(**p) for p in crudo.get("puntos", ())),
        rampa=crudo.get("rampa", "azul"),
        nota=crudo.get("nota", ""),
    )


def escribir(ruta: Path, informe: Informe) -> None:
    ruta.write_text(a_json(informe), encoding="utf-8")


def leer(ruta: Path) -> Informe:
    return desde_json(ruta.read_text(encoding="utf-8"))
