"""
Testes para o sistema de confiança.
"""

import pytest
from challenge_jusbrasil.confidence import (
    CalibradorConfianca,
    MetadadosResolucao,
    calibrar_confianca,
    estimar_caminho_resolucao,
    estimar_qualidade_contexto,
)


class TestEstimarCaminhoResolucao:
    """Testa estimação de caminho de resolução."""
    
    def test_nenhum_candidato(self):
        """Nenhum candidato = não encontrado."""
        assert estimar_caminho_resolucao(0) == "nao_encontrado"
    
    def test_um_candidato(self):
        """Um candidato = exato."""
        assert estimar_caminho_resolucao(1) == "exato"
    
    def test_multiplos_candidatos_com_desempate(self):
        """Múltiplos candidatos mas conseguiu desempatar = fuzzy."""
        assert estimar_caminho_resolucao(3, relator_matches=True) == "fuzzy"
        assert estimar_caminho_resolucao(2, cabecalho_matches=True) == "fuzzy"
        assert estimar_caminho_resolucao(2, mesmo_feito=True) == "fuzzy"
    
    def test_multiplos_candidatos_sem_desempate(self):
        """Múltiplos candidatos e não conseguiu desempatar = ambíguo."""
        assert estimar_caminho_resolucao(2) == "ambiguo"
        assert estimar_caminho_resolucao(5) == "ambiguo"


class TestEstimarQualidadeContexto:
    """Testa estimação de qualidade de contexto."""
    
    def test_contexto_vazio(self):
        """Sem contexto e sem matches = baixa."""
        assert estimar_qualidade_contexto(False, False, 0) == "baixa"
    
    def test_contexto_grande(self):
        """Contexto grande mas sem matches = media."""
        assert estimar_qualidade_contexto(False, False, 300) == "media"
    
    def test_relator_match(self):
        """Encontrou relator = media/alta."""
        assert estimar_qualidade_contexto(True, False, 0) == "media"
        assert estimar_qualidade_contexto(True, False, 300) == "alta"
    
    def test_cabecalho_match(self):
        """Encontrou cabecalho = media/alta."""
        assert estimar_qualidade_contexto(False, True, 0) == "media"
        assert estimar_qualidade_contexto(False, True, 300) == "alta"
    
    def test_ambos_matches_grande(self):
        """Relator e cabecalho com contexto grande = alta."""
        assert estimar_qualidade_contexto(True, True, 600) == "alta"


class TestCalibradorConfianca:
    """Testa o calibrador de confiança."""
    
    def setup_method(self):
        """Setup para cada teste."""
        self.calibrador = CalibradorConfianca()
    
    def test_sem_metadata(self):
        """Sem metadata, retorna None."""
        result = self.calibrador.calibrar("real", None)
        assert result is None
    
    def test_jurisprudencia_exato_real(self):
        """Jurisprudência encontrada exatamente = confiança alta."""
        metadata = MetadadosResolucao(
            tipo="jurisprudencia",
            caminho="exato",
            num_candidatos=1,
            contexto_qualidade="media"
        )
        conf = self.calibrador.calibrar("real", metadata)
        assert 0.90 < conf < 1.0
        assert conf == 0.96  # valor base, sem multiplicador
    
    def test_jurisprudencia_inventada(self):
        """Jurisprudência não encontrada = confiança baixa."""
        metadata = MetadadosResolucao(
            tipo="jurisprudencia",
            caminho="nao_encontrado",
            num_candidatos=0,
        )
        conf = self.calibrador.calibrar("inventada", metadata)
        assert 0.05 < conf < 0.15
        assert conf == 0.08
    
    def test_lei_exato_real(self):
        """Lei encontrada exatamente = confiança muito alta."""
        metadata = MetadadosResolucao(
            tipo="lei",
            caminho="exato",
            num_candidatos=1,
            contexto_qualidade="media"
        )
        conf = self.calibrador.calibrar("real", metadata)
        assert 0.95 < conf <= 1.0
        assert conf == 0.98
    
    def test_sumula_exato_real(self):
        """Súmula encontrada = confiança muito alta."""
        metadata = MetadadosResolucao(
            tipo="sumula",
            caminho="exato",
            num_candidatos=1,
            contexto_qualidade="media"
        )
        conf = self.calibrador.calibrar("real", metadata)
        assert conf == 0.99
    
    def test_ambiguo(self):
        """Citação ambígua = confiança baixa."""
        metadata = MetadadosResolucao(
            tipo="jurisprudencia",
            caminho="ambiguo",
            num_candidatos=2,
            contexto_qualidade="media"
        )
        conf = self.calibrador.calibrar("incompleta", metadata)
        assert 0.25 < conf < 0.50
        assert conf == 0.35
    
    def test_contexto_qualidade_alta(self):
        """Contexto de alta qualidade = confiança aumenta."""
        metadata = MetadadosResolucao(
            tipo="jurisprudencia",
            caminho="exato",
            num_candidatos=1,
            contexto_qualidade="alta"
        )
        conf_alta = self.calibrador.calibrar("real", metadata)
        
        metadata.contexto_qualidade = "media"
        conf_media = self.calibrador.calibrar("real", metadata)
        
        assert conf_alta > conf_media
        assert conf_alta == pytest.approx(0.96 * 1.08, rel=0.01)
        assert conf_media == 0.96
    
    def test_contexto_qualidade_baixa(self):
        """Contexto de baixa qualidade = confiança diminui."""
        metadata = MetadadosResolucao(
            tipo="jurisprudencia",
            caminho="exato",
            num_candidatos=1,
            contexto_qualidade="baixa"
        )
        conf_baixa = self.calibrador.calibrar("real", metadata)
        
        metadata.contexto_qualidade = "media"
        conf_media = self.calibrador.calibrar("real", metadata)
        
        assert conf_baixa < conf_media
        assert conf_baixa == pytest.approx(0.96 * 0.92, rel=0.01)
        assert conf_media == 0.96
    
    def test_vaga_incompleta(self):
        """Citação vaga sempre tem confiança baixa."""
        metadata = MetadadosResolucao(
            tipo="jurisprudencia",
            caminho="vaga",
            num_candidatos=0,
            contexto_qualidade="media"
        )
        conf = self.calibrador.calibrar("incompleta", metadata)
        assert 0.10 < conf < 0.25
        assert conf == 0.15


class TestCalibradorConvenience:
    """Testa função conveniente calibrar_confianca()."""
    
    def test_jurisprudencia_encontrada(self):
        """Jurisprudência encontrada com relator."""
        conf = calibrar_confianca(
            classe="real",
            tipo_citacao="jurisprudencia",
            num_candidatos=1,
            relator_matches=True,
            contexto_len=300
        )
        # 0.96 (exato) * 1.08 (qualidade alta) = 1.0368 → clamped to 1.0
        assert 0.95 < conf <= 1.0
    
    def test_lei_nao_encontrada(self):
        """Lei não encontrada."""
        conf = calibrar_confianca(
            classe="inventada",
            tipo_citacao="lei",
            num_candidatos=0,
        )
        assert 0.05 < conf < 0.15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
