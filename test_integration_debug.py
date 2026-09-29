import sys
sys.path.insert(0, "src")

from challenge_jusbrasil.confidence import calibrar_confianca_simplificado
from challenge_jusbrasil.busca.base import gravar
from challenge_jusbrasil.resolver.comum import Resolucao

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
contexto = "Conforme jurisprudência consolidada: RESP 1.234.567/SP 2020/0045678-9"

print(f"Contexto length: {len(contexto)}")
print(f"Esperado: confianca alta (>0.9)")

gravar(cit, "jurisprudencia", resultado, contexto)

print(f"Confianca retornada: {cit['confianca']}")
print(f"Classificacao: {cit['classificacao']}")
