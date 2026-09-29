"""
Calibração de confiança para resoluções de citações.

Sistema baseado em heurísticas que mapeia:
- Tipo de citação (jurisprudência, lei, súmula)
- Qualidade do match (exato, fuzzy, ambíguo, não encontrado)
→ Confiança (float em [0, 1])
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MetadadosResolucao:
    """Metadados adicionais sobre uma resolução."""
    tipo: str  # "jurisprudencia", "lei", "sumula"
    caminho: str  # "exato", "fuzzy", "ambiguo", "nao_encontrado"
    num_candidatos: int = 0  # quantos candidatos encontrou
    relator_matches: bool = False  # se encontrou relator no contexto
    cabecalho_matches: bool = False  # se encontrou match no cabeçalho
    mesmo_feito: bool = False  # se mesma origem/tribunal
    contexto_qualidade: str = "baixa"  # baixa, media, alta


class CalibradorConfianca:
    """Calibra confiança de resoluções baseada em metadados."""
    
    def __init__(self):
        # Configuração padrão de confiança por (tipo, caminho)
        self.tabela_base = {
            # Jurisprudência - Acórdãos
            ("jurisprudencia", "exato"): 0.96,
            ("jurisprudencia", "fuzzy"): 0.78,
            ("jurisprudencia", "ambiguo"): 0.35,
            ("jurisprudencia", "nao_encontrado"): 0.08,
            
            # Leis e Artigos
            ("lei", "exato"): 0.98,
            ("lei", "fuzzy"): 0.85,
            ("lei", "ambiguo"): 0.40,
            ("lei", "nao_encontrado"): 0.10,
            
            # Súmulas
            ("sumula", "exato"): 0.99,
            ("sumula", "fuzzy"): 0.80,
            ("sumula", "ambiguo"): 0.45,
            ("sumula", "nao_encontrado"): 0.08,
            
            # Incompleta (vaga, sem ID específico)
            ("incompleta", "vaga"): 0.15,
        }
        
        # Multiplicadores baseado em qualidade de contexto
        self.multiplicadores = {
            "alta": 1.08,    # melhora confiança (encontrou relator, etc)
            "media": 1.00,   # sem ajuste
            "baixa": 0.92,   # reduz confiança (contexto ambíguo)
        }
    
    def calibrar(
        self,
        classe: str,
        metadata: Optional[MetadadosResolucao] = None,
    ) -> Optional[float]:
        """
        Calibra confiança para uma resolução.
        
        Args:
            classe: "real", "inventada", "incompleta"
            metadata: Informações adicionais sobre a resolução
        
        Returns:
            Confiança (float em [0, 1]) ou None se não calculável
        """
        if metadata is None:
            return None
        
        if classe == "inventada":
            # Citação não encontrada no banco
            chave = (metadata.tipo, "nao_encontrado")
            return self.tabela_base.get(chave, 0.10)
        
        if classe == "incompleta":
            # Citação ambígua ou vaga
            if metadata.num_candidatos > 1:
                # Ambígua: múltiplos candidatos
                chave = (metadata.tipo, "ambiguo")
            else:
                # Vaga: sem ID específico
                chave = (metadata.tipo, "vaga")
            return self.tabela_base.get(chave, 0.25)
        
        if classe == "real":
            # Citação encontrada e resolvida
            chave = (metadata.tipo, metadata.caminho)
            conf_base = self.tabela_base.get(chave, 0.70)
            
            # Aplica multiplicador de qualidade de contexto
            mult = self.multiplicadores.get(metadata.contexto_qualidade, 1.00)
            conf_ajustada = conf_base * mult
            
            # Garante que fica em [0, 1]
            return min(1.0, max(0.0, conf_ajustada))
        
        return None


def estimar_caminho_resolucao(
    num_candidatos: int,
    relator_matches: bool = False,
    cabecalho_matches: bool = False,
    mesmo_feito: bool = False,
) -> str:
    """
    Estima o caminho de resolução baseado em heurísticas.
    
    Returns:
        "exato", "fuzzy", "ambiguo", ou "nao_encontrado"
    """
    if num_candidatos == 0:
        return "nao_encontrado"
    
    if num_candidatos == 1:
        return "exato"
    
    if num_candidatos > 1:
        # Múltiplos candidatos: usar heurísticas de desempate
        if mesmo_feito or relator_matches or cabecalho_matches:
            # Conseguiu desempatar
            return "fuzzy"
        else:
            # Não conseguiu desempatar
            return "ambiguo"
    
    return "fuzzy"


def estimar_qualidade_contexto(
    relator_matches: bool,
    cabecalho_matches: bool,
    contexto_len: int,
) -> str:
    """
    Estima qualidade do contexto para refinamento de confiança.
    
    Returns:
        "alta", "media", ou "baixa"
    """
    pontos = 0
    
    if contexto_len > 200:
        pontos += 1
    if contexto_len > 500:
        pontos += 1
    if relator_matches:
        pontos += 2
    if cabecalho_matches:
        pontos += 1
    
    if pontos >= 3:
        return "alta"
    elif pontos >= 1:
        return "media"
    else:
        return "baixa"


# Instância global (singleton pattern)
_calibrador_global = None


def get_calibrador() -> CalibradorConfianca:
    """Obtém instância global do calibrador."""
    global _calibrador_global
    if _calibrador_global is None:
        _calibrador_global = CalibradorConfianca()
    return _calibrador_global


def calibrar_confianca(
    classe: str,
    tipo_citacao: str,
    num_candidatos: int = 0,
    relator_matches: bool = False,
    cabecalho_matches: bool = False,
    mesmo_feito: bool = False,
    contexto_len: int = 0,
) -> Optional[float]:
    """
    Função conveniente para calibrar confiança em uma única chamada.
    
    Args:
        classe: "real", "inventada", "incompleta"
        tipo_citacao: "jurisprudencia", "lei", "sumula"
        num_candidatos: Quantos registros foram encontrados
        relator_matches: Se encontrou relator no contexto
        cabecalho_matches: Se encontrou match no cabeçalho
        mesmo_feito: Se determinou ser o mesmo processo/feito
        contexto_len: Tamanho do contexto em caracteres
    
    Returns:
        Confiança (float em [0, 1]) ou None
    """
    caminho = estimar_caminho_resolucao(
        num_candidatos, relator_matches, cabecalho_matches, mesmo_feito
    )
    qualidade = estimar_qualidade_contexto(
        relator_matches, cabecalho_matches, contexto_len
    )
    
    metadata = MetadadosResolucao(
        tipo=tipo_citacao,
        caminho=caminho,
        num_candidatos=num_candidatos,
        relator_matches=relator_matches,
        cabecalho_matches=cabecalho_matches,
        mesmo_feito=mesmo_feito,
        contexto_qualidade=qualidade,
    )
    
    calibrador = get_calibrador()
    return calibrador.calibrar(classe, metadata)


def calibrar_confianca_simplificado(
    classe: str,
    tipo_citacao: str,
    contexto_len: int = 0,
) -> Optional[float]:
    """
    Versão simplificada que usa apenas informações já disponíveis.
    
    Não precisa de resolvers, funciona com (classe, tipo) base.
    Útil para integração rápida no pipeline.
    
    Args:
        classe: "real", "inventada", "incompleta"
        tipo_citacao: "jurisprudencia", "lei", "sumula"
        contexto_len: tamanho do contexto em chars
    
    Returns:
        Confiança (float em [0, 1]) ou None
    """
    calibrador = get_calibrador()
    
    # Estimar qualidade de contexto (simples)
    qualidade = "alta" if contexto_len > 250 else "media" if contexto_len > 100 else "baixa"
    
    # Criar metadata mínima
    metadata = MetadadosResolucao(
        tipo=tipo_citacao,
        caminho="nao_encontrado" if classe == "inventada" else ("ambiguo" if classe == "incompleta" else "exato"),
        num_candidatos=0 if classe == "inventada" else (2 if classe == "incompleta" else 1),
        contexto_qualidade=qualidade,
    )
    
    return calibrador.calibrar(classe, metadata)
