"""Test confidence integration with pipeline."""

import sys
sys.path.insert(0, "src")

from challenge_jusbrasil.confidence import calibrar_confianca_simplificado
from challenge_jusbrasil.busca.base import gravar
from challenge_jusbrasil.resolver.comum import Resolucao

def test_calibrar_simplificado():
    """Test simplified calibration."""
    print("Testing calibrar_confianca_simplificado...")
    
    # Test real jurisprudence with high context
    conf = calibrar_confianca_simplificado(
        classe="real",
        tipo_citacao="jurisprudencia",
        contexto_len=300
    )
    assert 0.90 < conf <= 1.0
    print(f"  [OK] Real jurisprudencia (ctx 300): {conf:.4f}")
    
    # Test real with medium context
    conf = calibrar_confianca_simplificado(
        classe="real",
        tipo_citacao="jurisprudencia",
        contexto_len=150
    )
    assert 0.90 < conf < 1.0
    print(f"  [OK] Real jurisprudencia (ctx 150): {conf:.4f}")
    
    # Test inventada
    conf = calibrar_confianca_simplificado(
        classe="inventada",
        tipo_citacao="lei",
        contexto_len=100
    )
    assert 0.05 < conf < 0.15
    print(f"  [OK] Inventada lei: {conf:.4f}")
    
    # Test incompleta
    conf = calibrar_confianca_simplificado(
        classe="incompleta",
        tipo_citacao="sumula",
        contexto_len=50
    )
    assert 0.1 < conf < 0.5
    print(f"  [OK] Incompleta sumula: {conf:.4f}")

def test_gravar():
    """Test gravar function with confidence."""
    print("\nTesting gravar with confidence...")
    
    # Test 1: Real with long context
    cit = {
        "inicio": 0,
        "fim": 20,
        "trecho": "RESP 1.234.567/SP",
        "tipo": None,
        "classificacao": "incompleta",
        "confianca": None,
        "resolucao": None,
    }
    
    resultado = Resolucao(classificacao="real", id_canonico="12345")
    # Long context to trigger "alta" quality
    contexto = "Conforme jurisprudência consolidada: RESP 1.234.567/SP 2020/0045678-9" + " " * 300
    
    gravar(cit, "jurisprudencia", resultado, contexto)
    
    assert cit["classificacao"] == "real"
    assert cit["confianca"] is not None
    assert 0.9 < cit["confianca"] <= 1.0
    assert cit["resolucao"]["id_canonico"] == "12345"
    print(f"  [OK] Real (long ctx): confianca={cit['confianca']:.4f}, classificacao={cit['classificacao']}")
    
    # Test 2: Inventada with no context
    cit2 = {
        "inicio": 0,
        "fim": 20,
        "trecho": "ARESP 9.999.999/XX",
        "tipo": None,
        "classificacao": "incompleta",
        "confianca": None,
        "resolucao": None,
    }
    resultado2 = Resolucao(classificacao="inventada")
    gravar(cit2, "jurisprudencia", resultado2, "")
    
    assert cit2["classificacao"] == "inventada"
    assert cit2["confianca"] is not None
    assert 0.05 < cit2["confianca"] < 0.15
    print(f"  [OK] Inventada (no ctx): confianca={cit2['confianca']:.4f}")
    
    # Test 3: Incompleta
    cit3 = {
        "inicio": 0,
        "fim": 30,
        "trecho": "jurisprudencia consolidada",
        "tipo": None,
        "classificacao": "incompleta",
        "confianca": None,
        "resolucao": None,
    }
    resultado3 = Resolucao(classificacao="incompleta")
    gravar(cit3, "jurisprudencia", resultado3, "contexto pequeno")
    
    assert cit3["classificacao"] == "incompleta"
    assert cit3["confianca"] is not None
    assert 0.2 < cit3["confianca"] < 0.5
    print(f"  [OK] Incompleta: confianca={cit3['confianca']:.4f}")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Confidence Integration")
    print("=" * 60)
    
    test_calibrar_simplificado()
    test_gravar()
    
    print("\n" + "=" * 60)
    print("SUCCESS: Integration tests passed!")
    print("=" * 60)
