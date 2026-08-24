"""
Grafo de relaciones de solo lectura — Fase 5 + Fase 7 (multi-hop, Palantir-IA).

Explora la red empresa → contratos/proyectos → geografía → otras empresas a partir
de la ontología ya construida (dim_empresa, dim_proyecto, dim_geografia + sus
tablas de alias). Dos saltos desde la empresa central:

  1er salto: empresa -> contratos (supervision, alta confianza vía NIT) y
             empresa -> proyectos (contratos_or, menor confianza vía nombre difuso).
  2do salto: contrato/proyecto -> geografía, y geografía -> otras empresas que
             también operan ahí (patrón de "concentración de contratistas").

100% exploración/auditoría — no expone ninguna acción de escritura, no cambia
el estado de ningún contrato.
"""

import logging
from typing import Any, Dict, List, Optional

from domain.interfaces.repositories import IEmpresaRepository

logger = logging.getLogger(__name__)


def _get_default_empresa_repo():
    from core.container import container
    return container.get_empresa_repository()


class GraphService:
    """Servicio de exploración de red — capa de solo lectura."""

    def __init__(self, empresa_repository: Optional[IEmpresaRepository] = None):
        self.empresa_repo = empresa_repository or _get_default_empresa_repo()

    def vecindario_empresa(
        self, empresa_id: int, limit_contratos: int = 50, limit_relacionadas: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Vecindario multi-hop de una empresa:
          - contratos (NIT, alta confianza) y proyectos (nombre difuso, revisar)
          - geografía donde esos contratos/proyectos están ubicados
          - otras empresas con contratos en esas mismas geografías (2do salto)

        Empresas muy conectadas (ej. GENSA: 315 contratos) se limitan a
        `limit_contratos` para que la respuesta/UI sigan siendo manejables —
        `total_contratos_verificados` en la respuesta indica el conteo real sin límite.
        """
        empresa = self.empresa_repo.obtener_por_id(empresa_id)
        if empresa is None:
            return None

        contratos_verificados: List[Dict[str, Any]] = []
        total_contratos = 0
        if empresa.get("nit_normalizado"):
            total_contratos = self.empresa_repo.contar_contratos_supervision_por_nit(
                empresa["nit_normalizado"]
            )
            contratos_verificados = self.empresa_repo.contratos_supervision_por_nit(
                empresa["nit_normalizado"], limit=limit_contratos
            )

        proyectos = self.empresa_repo.proyectos_de_empresa(empresa_id)

        alias_resueltos = self.empresa_repo.alias_resueltos_de_empresa(empresa_id)
        menciones_no_verificadas = [
            a for a in alias_resueltos if a["metodo"] == "match_nombre_fuzzy"
        ]

        # 2do salto: geografías donde opera (vía contratos verificados) -> otras
        # empresas ahí. Solo se calcula sobre conexiones de alta confianza (NIT)
        # para no propagar incertidumbre de un match difuso a un segundo salto.
        codigos_dpto = sorted({
            c["codigo_dane_departamento"] for c in contratos_verificados
            if c.get("codigo_dane_departamento")
        })
        empresas_relacionadas = self.empresa_repo.empresas_relacionadas_por_geografia(
            codigos_dpto, empresa_id, limit=limit_relacionadas
        ) if codigos_dpto else []

        # Arista contractual directa (Fase 23 Bloque 2) — a diferencia de
        # 'coincide_en_zona_con' (co-ubicación inferida, débil), esta viene de
        # un campo real del contrato (interventoria) resuelto contra dim_empresa.
        interventorias = (
            self.empresa_repo.interventorias_de_empresa(empresa["nit_normalizado"])
            if empresa.get("nit_normalizado") else []
        )

        geografias: Dict[Any, Dict[str, Any]] = {}
        for c in contratos_verificados:
            key = c.get("codigo_dane_departamento")
            if key and key not in geografias:
                geografias[key] = {
                    "codigo_dane_departamento": key,
                    "departamento": c.get("departamento"),
                }
        for p in proyectos:
            key = p.get("departamento")
            if key and key not in geografias:
                geografias[key] = {"codigo_dane_departamento": None, "departamento": key}

        nodos = [{"tipo": "empresa", "id": f"empresa-{empresa_id}", "datos": empresa}]
        nodos += [{"tipo": "contrato", "id": f"contrato-{c['id']}", "datos": c} for c in contratos_verificados]
        nodos += [
            {"tipo": "proyecto", "id": f"proyecto-{p['nombre_proyecto_id']}", "datos": p}
            for p in proyectos
        ]
        nodos += [
            {"tipo": "geografia", "id": f"geo-{k}", "datos": g}
            for k, g in geografias.items()
        ]
        nodos += [
            {"tipo": "empresa_relacionada", "id": f"empresa-{e['empresa_id']}", "datos": e}
            for e in empresas_relacionadas
        ]
        nodos += [
            {"tipo": "interventoria", "id": f"empresa-{i['empresa_id']}", "datos": i}
            for i in interventorias
        ]

        aristas = []
        for c in contratos_verificados:
            aristas.append({
                "origen": f"empresa-{empresa_id}", "destino": f"contrato-{c['id']}",
                "tipo": "ejecuta", "confianza": "alta",
            })
            if c.get("codigo_dane_departamento"):
                aristas.append({
                    "origen": f"contrato-{c['id']}", "destino": f"geo-{c['codigo_dane_departamento']}",
                    "tipo": "ubicado_en", "confianza": "alta",
                })
        for p in proyectos:
            aristas.append({
                "origen": f"empresa-{empresa_id}", "destino": f"proyecto-{p['nombre_proyecto_id']}",
                "tipo": "ejecuta_probable", "confianza": p.get("metodo_empresa"),
            })
            if p.get("departamento"):
                aristas.append({
                    "origen": f"proyecto-{p['nombre_proyecto_id']}", "destino": f"geo-{p['departamento']}",
                    "tipo": "ubicado_en", "confianza": "alta",
                })
        for e in empresas_relacionadas:
            aristas.append({
                "origen": f"empresa-{empresa_id}", "destino": f"empresa-{e['empresa_id']}",
                "tipo": "coincide_en_zona_con", "confianza": "alta",
            })
        for i in interventorias:
            aristas.append({
                "origen": f"empresa-{i['empresa_id']}", "destino": f"empresa-{empresa_id}",
                "tipo": "interventor_de",
                "confianza": "alta" if i.get("resuelto_por_nit") else "revisar",
            })

        return {
            "empresa": empresa,
            "nodos": nodos,
            "aristas": aristas,
            "contratos_verificados": len(contratos_verificados),
            "total_contratos_verificados": total_contratos,
            "proyectos_relacionados": proyectos,
            "empresas_en_misma_zona": empresas_relacionadas,
            "interventorias": interventorias,
            "menciones_no_verificadas": [
                {
                    "esquema": a["esquema_origen"], "tabla": a["tabla_origen"],
                    "valor_original": a["valor_original"],
                }
                for a in menciones_no_verificadas
            ],
            "nota": (
                "Contratos: match exacto por NIT (alta confianza). Proyectos: "
                "coincidencia de nombre por similitud de texto — requieren revisión "
                "humana antes de asumirse como el mismo ejecutor. Empresas en la "
                "misma zona: otras compañías con contratos verificados (NIT) en los "
                "mismos departamentos donde opera esta empresa. Interventorías: "
                "firmas que fiscalizan los contratos de esta empresa como ejecutora "
                "(campo real del contrato, no inferido — 'confianza: revisar' cuando "
                "el nombre de la interventoría se resolvió por similitud de texto, "
                "no por NIT)."
            ),
        }
