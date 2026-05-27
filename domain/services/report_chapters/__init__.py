"""Builders HTML por capítulo para el informe PDF multi-capítulo."""

from domain.services.report_chapters.chapter_comunidades import (
    build_chapter_colombia_solar,
    build_chapter_comunidades,
    build_chapter_contratos_or,
    build_chapter_fenoge,
)
from domain.services.report_chapters.chapter_gestion import build_chapter_gestion_riesgos
from domain.services.report_chapters.chapter_noticias import build_chapter_noticias
from domain.services.report_chapters.chapter_presupuesto import build_chapter_presupuesto
from domain.services.report_chapters.chapter_subsidios import build_chapter_subsidios
from domain.services.report_chapters.chapter_supervision import build_chapter_supervision

__all__ = [
    "build_chapter_gestion_riesgos",
    "build_chapter_comunidades",
    "build_chapter_contratos_or",
    "build_chapter_fenoge",
    "build_chapter_colombia_solar",
    "build_chapter_subsidios",
    "build_chapter_supervision",
    "build_chapter_presupuesto",
    "build_chapter_noticias",
]
