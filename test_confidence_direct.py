"""Test confidence module directly."""

import sys
sys.path.insert(0, "src")

from challenge_jusbrasil.confidence import (
    CalibradorConfianca,
    MetadadosResolucao,
    calibrar_confianca,
    estimar_caminho_resolucao,
    estimar_qualidade_contexto,
)

def test_estimar_caminho():
    """Test resolution path estimation."""
    print("Testing estimar_caminho_resolucao...")
    assert estimar_caminho_resolucao(0) == "nao_encontrado"
    assert estimar_caminho_resolucao(1) == "exato"
    assert estimar_caminho_resolucao(3, relator_matches=True) == "fuzzy"
    assert estimar_caminho_resolucao(2) == "ambiguo"
    print("[OK] Caminho de resolucao")

def test_estimar_qualidade():
    """Test context quality estimation."""
    print("Testing estimar_qualidade_contexto...")
    assert estimar_qualidade_contexto(False, False, 0) == "baixa"
    assert estimar_qualidade_contexto(False, False, 300) == "media"
    assert estimar_qualidade_contexto(True, False, 0) == "media"
    assert estimar_qualidade_contexto(True, True, 600) == "alta"
    print("[OK] Qualidade de contexto")

def test_calibrador():
    """Test confidence calibrator."""
    print("Testing CalibradorConfianca...")
    calibrador = CalibradorConfianca()
    
    # Test jurisprudencia exato
    metadata = MetadadosResolucao(
        tipo="jurisprudencia",
        caminho="exato",
        num_candidatos=1,
        contexto_qualidade="media"
    )
    conf = calibrador.calibrar("real", metadata)
    assert 0.90 < conf <= 1.0
    assert conf == 0.96
    print(f"  [OK] Jurisprudencia exato: {conf:.2f}")
    
    # Test jurisprudencia inventada
    metadata = MetadadosResolucao(
        tipo="jurisprudencia",
        caminho="nao_encontrado",
        num_candidatos=0,
    )
    conf = calibrador.calibrar("inventada", metadata)
    assert 0.05 < conf < 0.15
    assert conf == 0.08
    print(f"  [OK] Jurisprudencia inventada: {conf:.2f}")
    
    # Test lei exato
    metadata = MetadadosResolucao(
        tipo="lei",
        caminho="exato",
        num_candidatos=1,
        contexto_qualidade="media"
    )
    conf = calibrador.calibrar("real", metadata)
    assert conf == 0.98
    print(f"  [OK] Lei exato: {conf:.2f}")
    
    # Test contexto qualidade
    metadata = MetadadosResolucao(
        tipo="jurisprudencia",
        caminho="exato",
        num_candidatos=1,
        contexto_qualidade="alta"
    )
    conf_alta = calibrador.calibrar("real", metadata)
    metadata.contexto_qualidade = "media"
    conf_media = calibrador.calibrar("real", metadata)
    assert conf_alta > conf_media
    print(f"  [OK] Qualidade alta: {conf_alta:.4f} > media: {conf_media:.2f}")

def test_convenience():
    """Test convenience function."""
    print("Testing calibrar_confianca...")
    conf = calibrar_confianca(
        classe="real",
        tipo_citacao="jurisprudencia",
        num_candidatos=1,
        relator_matches=True,
        contexto_len=300
    )
    assert 0.95 < conf <= 1.0
    print(f"  [OK] Jurisprudencia com relator: {conf:.4f}")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Confidence System")
    print("=" * 60)
    
    test_estimar_caminho()
    test_estimar_qualidade()
    test_calibrador()
    test_convenience()
    
    print("\n" + "=" * 60)
    print("SUCCESS: All tests passed!")
    print("=" * 60)
